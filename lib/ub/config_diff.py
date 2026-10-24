"""Bounded normalized-export adapter and value-free deterministic diff engine.

There is intentionally no guessed native .unifi/.unf parser.
"""
import hashlib
from pathlib import Path
import re

from core import Failure, SHA, digest, iso, load, metadata, regular, save_state
from verify import verify

CATEGORIES = {'networks', 'firewall', 'nat', 'port_forwarding', 'vpn', 'wifi', 'dhcp', 'dns', 'admins', 'security'}
VOLATILE = {'updated_at', 'last_seen', 'created_at', 'uptime', 'timestamp'}
SENSITIVE = re.compile(r'password|secret|token|key|credential|cert|auth|community|psk|user|email', re.I)


def extract(path, c):
    path = regular(path, private=True)
    if path.name.endswith('.config.json'):
        snapshot_path = path
    else:
        result = verify(path, c)
        if not result['success']:
            raise Failure('Diff source integrity verification failed', 74)
        snapshot_path = Path(str(path) + '.config.json')
        if not snapshot_path.exists():
            raise Failure('Unsupported native UniFi format: no hash-bound normalized configuration export', 69)
        regular(snapshot_path, private=True)
    data = load(snapshot_path, 16 * 1024 * 1024)
    if data.get('schema') != 'unifi-backup-config/v1' or not SHA.fullmatch(str(data.get('backup_sha256', ''))):
        raise Failure('Unsupported normalized configuration schema', 65)
    if snapshot_path != path and data['backup_sha256'] != digest(path):
        raise Failure('Normalized export is not bound to the selected artifact hash', 74)
    objects = data.get('categories')
    if not isinstance(objects, dict):
        raise Failure('Normalized export requires a categories object', 65)
    return data


def clean(value, depth=0):
    if depth > 32:
        raise Failure('Configuration nesting exceeds safety limit', 65)
    if isinstance(value, dict):
        return {k: clean(v, depth + 1) for k, v in sorted(value.items()) if k not in VOLATILE}
    if isinstance(value, list):
        return [clean(v, depth + 1) for v in value]
    return value


def compare(old, new, category=None, unchanged=False):
    if category and category not in CATEGORIES:
        raise Failure('Unsupported diff category', 64)
    changes, unsupported = [], []
    for name in sorted(set(old['categories']) | set(new['categories'])):
        if name not in CATEGORIES:
            unsupported.append('unknown_category')
            continue
        if category and name != category:
            continue
        indexed = []
        for data in (old, new):
            values = data['categories'].get(name, [])
            if not isinstance(values, list) or len(values) > 100000:
                raise Failure('Invalid normalized category', 65)
            mapping = {}
            for value in values:
                if not isinstance(value, dict) or not isinstance(value.get('id'), str) or not value['id'] or value['id'] in mapping:
                    raise Failure('Normalized objects require unique stable string IDs', 65)
                mapping[value['id']] = clean(value)
            indexed.append(mapping)
        before, after = indexed
        for identifier in sorted(set(before) | set(after)):
            a, b = before.get(identifier), after.get(identifier)
            kind = 'added' if a is None else 'removed' if b is None else 'unchanged' if a == b else 'modified'
            if kind == 'unchanged' and not unchanged:
                continue
            # IDs can themselves contain usernames or secrets. Output a stable
            # opaque handle and counts only, never arbitrary keys/values.
            changed_keys = [k for k in set(a or {}) | set(b or {}) if (a or {}).get(k) != (b or {}).get(k)]
            changes.append({'category': name, 'object_handle': hashlib.sha256(identifier.encode()).hexdigest()[:16],
                            'change': kind, 'changed_field_count': len(changed_keys),
                            'sensitive_or_unknown_values': '[REDACTED]'})
    summary = {kind: sum(item['change'] == kind for item in changes) for kind in ('added', 'removed', 'modified', 'unchanged')}
    return {'schema_version': 1, 'capability': 'normalized_export_only', 'summary': summary,
            'changes': changes, 'unsupported': sorted(set(unsupported)), 'values_redacted': True}


def diff(c, old_path, new_path, category=None, unchanged=False):
    report = compare(extract(old_path, c), extract(new_path, c), category, unchanged)
    report['evaluated_at'] = iso()
    save_state(c, 'config-diff.json', report)
    return report

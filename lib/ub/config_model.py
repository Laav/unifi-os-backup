"""In-memory configuration model, redacted review and centralized validation."""
from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import urllib.parse

from core import Failure
from config_files import Document, checked, fingerprint, load_document, read_bytes
from config_schema import SCOPES, defaults, validate_operations
from config_transaction import HEADER, Transaction, read_lock

TARGET_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}')
ALIASES = {'graph': 'GRAPH_CONFIG_FILE', 'storage': 'STORAGE_CONFIG_FILE', 'ntfy': 'NTFY_CONFIG_FILE', 'webhook': 'WEBHOOK_CONFIG_FILE'}
SERVICES = {'unifi-backup.service': 'unifi-backup', 'unifi-backup-monitor.service': 'unifi-backup-monitor',
            'unifi-backup-verify.service': 'unifi-backup-verify --all --scheduled',
            'unifi-backup-remote-verify.service': 'unifi-backup-remote-verify --latest --full --scheduled',
            'unifi-backup-retry.service': 'unifi-backup-retry --scheduled'}


@dataclass(frozen=True)
class Issue:
    category: str
    location: str
    message: str
    warning: bool = False


def https(value, kind):
    try:
        p = urllib.parse.urlsplit(value)
        port = p.port
        if p.scheme != 'https' or not p.hostname or p.username is not None or p.password is not None or p.fragment or any(ord(c) < 33 or ord(c) == 127 for c in value) or '\\' in value or (port is not None and port == 0):
            raise ValueError
        if kind != 'webhook_url' and p.query:
            raise ValueError
        if kind == 'origin' and p.path not in ('', '/'):
            raise ValueError
        if kind == 'container_url' and (not p.path.strip('/') or '/' in p.path.strip('/')):
            raise ValueError
    except ValueError:
        raise Failure('HTTPS URL has an invalid host/port, credentials, path, query or fragment', 78) from None


def write_directory(value):
    path = checked(value, directory=True)
    forbidden = ('/etc', '/usr', '/bin', '/sbin', '/lib', '/boot', '/dev', '/proc', '/sys', '/home', '/root', '/run/user', '/tmp', '/var/tmp')
    text = str(path).replace('\\', '/')
    if text in ('/', '/var', '/var/backups', '/var/lib', '/run', '/mnt', '/srv', '/opt') or any(text == p or text.startswith(p + '/') for p in forbidden):
        raise Failure('Choose a dedicated backup/state directory outside protected system/home/temporary paths', 78)
    if path.exists():
        checked(path, private=True, directory=True)
    return path


def read_access(value):
    path = checked(value)
    text = str(path).replace('\\', '/')
    if any(text == p or text.startswith(p + '/') for p in ('/home', '/root', '/run/user', '/tmp', '/var/tmp')):
        raise Failure('Configured read path is hidden by ProtectHome/PrivateTmp; choose a dedicated /etc or /srv path', 78)
    return path


def calendar(expression):
    if not expression or len(expression) > 256 or any(ord(c) < 32 for c in expression):
        raise Failure('Invalid systemd calendar expression', 78)
    if not shutil.which('systemd-analyze'):
        raise Failure('systemd-analyze is required to validate a changed schedule', 69)
    result = subprocess.run(['systemd-analyze', 'calendar', '--iterations=1', expression], stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=False)
    if result.returncode:
        raise Failure('systemd rejected the calendar expression', 78)


def public_recipients(data, check_age=True):
    try:
        text = data.decode('utf-8')
    except UnicodeError:
        raise Failure('Public recipient file must be UTF-8', 78) from None
    if re.search(r'AGE-SECRET-KEY|BEGIN\s+.*PRIVATE\s+KEY', text, re.I):
        raise Failure('Private recovery identities are forbidden in the public recipient file', 78)
    recipients = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('#')]
    if not recipients or len(recipients) > 128 or any(not re.fullmatch(r'(?:age1[023456789acdefghjklmnpqrstuvwxyz]{58}|ssh-(?:rsa|ed25519) [A-Za-z0-9+/=]+(?: [^\r\n]*)?)', r) for r in recipients):
        raise Failure('Provide valid age v1 or SSH public recipients only', 78)
    if check_age:
        if not shutil.which('age'):
            raise Failure('Install age before enabling encryption', 69)
        # Public values are not private keys, but keep even these out of argv.
        import tempfile
        import os
        fd, name = tempfile.mkstemp(prefix='.unifi-public-recipients.')
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
            result = subprocess.run(['age', '--encrypt', '--recipients-file', name], input=b'configuration-validation',
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15, check=False)
            if result.returncode:
                raise Failure('age rejected the public recipient file', 78)
        finally:
            Path(name).unlink(missing_ok=True)


def active_field(spec, values, main):
    dependency = spec.depends
    if dependency == 'always' or 'BACKUP_TARGETS' in dependency:
        return True
    if '!=' in dependency:
        key, wanted = dependency.split('!=', 1)
        return values.get(key, main.get(key, '')) != wanted
    if '=' in dependency:
        key, wanted = dependency.split('=', 1)
        return values.get(key, main.get(key, '')) == wanted
    return True


class Model:
    def __init__(self, config='/etc/unifi-backup/unifi-backup.env', units='/etc/systemd/system'):
        self.config, self.units = checked(config), checked(units, directory=True)
        self.documents, self.snapshots, self.paths, self.scopes, self.values, self.errors = {}, {}, {}, {}, {}, {}
        self.dirty = {}
        self.schedule = None
        self.recipients = None
        self.extra_snapshot = {}
        self.transaction = Transaction(self.config, self.units)
        with read_lock(self.config.parent / '.configure.lock'):
            self._load('main', self.config, 'main')
            if 'main' in self.errors:
                raise self.errors['main']
            self.refresh()
            self.original_main = dict(self.main)
            self.pending = self.transaction.pending_id()

    @property
    def main(self):
        return self.values['main']

    def _load(self, name, path, scope):
        path = Path(path)
        if name in self.paths and self.paths[name] == path:
            return
        self.paths[name], self.scopes[name] = path, scope
        try:
            before = fingerprint(path)
            doc = load_document(path)
            if fingerprint(path) != before:
                raise Failure('Configuration changed during loading; retry', 75)
            self.snapshots[name] = before
            self.documents[name] = doc
            self.values[name] = {**defaults(scope), **doc.values}
            if scope == 'target' and 'RESTORE_MAX_BYTES' not in doc.values:
                self.values[name]['RESTORE_MAX_BYTES'] = self.main['RESTORE_MAX_BYTES']
            if scope == 'target' and 'TARGET_LOCK_MODE' not in doc.values:
                self.values[name]['TARGET_LOCK_MODE'] = 'GOVERNANCE' if self.values[name]['TARGET_TYPE'] == 's3' else 'locked'
            self.dirty[name] = set()
            self.errors.pop(name, None)
        except Failure as exc:
            self.errors[name] = exc
            self.values[name] = defaults(scope)

    def target_ids(self):
        identifiers = self.main.get('BACKUP_TARGETS', '').split()
        if '\n' in self.main.get('BACKUP_TARGETS', '') or '\r' in self.main.get('BACKUP_TARGETS', '') or len(identifiers) > 32 or len(set(identifiers)) != len(identifiers) or any(not TARGET_ID.fullmatch(x) or x == 'main' for x in identifiers):
            raise Failure('Target IDs must be unique, safe, nonreserved names (maximum 32)', 78)
        return identifiers

    def refresh(self):
        self.target_error = None
        for name, key in ALIASES.items():
            self._load(name, self.main[key], name)
        try:
            directory = checked(self.main['BACKUP_TARGET_CONFIG_DIR'], private=True, directory=True)
            identifiers = self.target_ids()
        except Failure as exc:
            # A safe literal main file can still be edited to repair a bad
            # target path/list. Never traverse that path to populate targets.
            self.target_error = exc
            return
        if directory.exists():
            for path in directory.glob('*.env'):
                if TARGET_ID.fullmatch(path.stem) and path.stem != 'main':
                    self._load('target:' + path.stem, path, 'target')
        for identifier in identifiers:
            self._load('target:' + identifier, directory / (identifier + '.env'), 'target')
        for name, values in self.values.items():
            if name.startswith('target:') and name in self.documents and 'RESTORE_MAX_BYTES' not in self.documents[name].values and 'RESTORE_MAX_BYTES' not in self.dirty.get(name, set()):
                values['RESTORE_MAX_BYTES'] = self.main['RESTORE_MAX_BYTES']

    def set(self, name, key, value):
        if name in self.errors:
            raise Failure('This file cannot be safely edited; correct its permissions/literal syntax manually first', self.errors[name].code)
        specs = {s.name: s for s in SCOPES[self.scopes[name]]}
        if key not in specs:
            raise Failure('Unknown setting cannot be edited through the manager', 64)
        specs[key].validate({key: value})
        if specs[key].kind in ('path', 'private_path', 'directory', 'private_directory', 'certificate') and value:
            checked(value, directory=specs[key].kind in ('directory', 'private_directory'))
        if name == 'main' and key == 'BACKUP_TARGETS':
            identifiers = value.split()
            if '\n' in value or '\r' in value or len(identifiers) > 32 or len(set(identifiers)) != len(identifiers) or any(not TARGET_ID.fullmatch(x) or x == 'main' for x in identifiers):
                raise Failure('Invalid target ID list', 78)
            if bool(self.main['BACKUP_TARGETS'].strip()) != bool(value.strip()) and self.main['REMOTE_STORAGE_TYPE'] != 'none':
                raise Failure('Disable legacy storage explicitly before switching between local/legacy and multi-target modes', 78)
        self.values[name][key] = value
        self.dirty[name].add(key)
        if name.startswith('target:') and key == 'TARGET_TYPE' and 'TARGET_LOCK_MODE' not in self.documents[name].values and 'TARGET_LOCK_MODE' not in self.dirty[name]:
            self.values[name]['TARGET_LOCK_MODE'] = 'GOVERNANCE' if value == 's3' else 'locked'
        if name == 'main' and (key in ALIASES.values() or key in ('BACKUP_TARGET_CONFIG_DIR', 'BACKUP_TARGETS', 'RESTORE_MAX_BYTES')):
            self.refresh()

    def add_target(self, identifier, kind):
        if not TARGET_ID.fullmatch(identifier) or identifier == 'main':
            raise Failure('Invalid or reserved target ID', 78)
        name = 'target:' + identifier
        if name in self.paths:
            raise Failure('Target ID already exists; edit or enable it instead', 78)
        self._load(name, Path(self.main['BACKUP_TARGET_CONFIG_DIR']) / (identifier + '.env'), 'target')
        self.set(name, 'TARGET_TYPE', kind)
        if kind == 's3':
            self.set(name, 'TARGET_LOCK_MODE', 'GOVERNANCE')

    def activate(self, identifier, enabled=True):
        identifiers = self.target_ids()
        if 'target:' + identifier not in self.values:
            raise Failure('Unknown target', 78)
        if enabled and identifier not in identifiers:
            if not identifiers and self.main['REMOTE_STORAGE_TYPE'] != 'none':
                raise Failure('Explicitly disable legacy storage before enabling multi-target storage; credentials are not migrated automatically', 78)
            identifiers.append(identifier)
        elif not enabled:
            identifiers = [x for x in identifiers if x != identifier]
            if not identifiers and self.main['REMOTE_STORAGE_TYPE'] != 'none':
                raise Failure('Disable dormant legacy storage first; removing the last target must not reactivate it', 78)
        self.set('main', 'BACKUP_TARGETS', ' '.join(identifiers))

    def active_names(self):
        active = ['main']
        active += [name for name, flag in [('graph', 'ENABLE_EMAIL'), ('ntfy', 'ENABLE_NTFY'), ('webhook', 'ENABLE_WEBHOOK')] if self.main[flag] == 'true']
        ids = self.target_ids()
        if ids:
            active += ['target:' + x for x in ids]
        elif self.main['REMOTE_STORAGE_TYPE'] != 'none':
            active += ['storage']
        return active

    def scope_issues(self, name, filesystem=True):
        if name in self.errors:
            exc = self.errors[name]
            return [Issue('syntax' if exc.code == 65 else 'security', name, str(exc))]
        issues = []
        values, scope = self.values[name], self.scopes[name]
        visible = {**values, 'TARGET_TYPE': self.main['REMOTE_STORAGE_TYPE']} if scope == 'storage' else values
        for spec in SCOPES[scope]:
            if not active_field(spec, visible, self.main):
                continue
            value = values[spec.name]
            try:
                spec.validate(values)
                if spec.kind in ('origin', 'container_url', 'webhook_url'):
                    https(value, spec.kind)
                elif spec.kind in ('path', 'private_path', 'directory', 'private_directory') and value:
                    checked(value, directory=spec.kind in ('directory', 'private_directory'))
                elif spec.kind == 'certificate' and value and filesystem:
                    read_access(value)
                    ssl.create_default_context(cafile=value)
            except (Failure, OSError, ssl.SSLError, ValueError) as exc:
                category = 'security' if spec.kind in ('path', 'directory', 'private_path', 'private_directory', 'certificate') else 'configuration'
                issues.append(Issue(category, name + '.' + spec.name, str(exc) if isinstance(exc, Failure) else 'Invalid/unreadable CA or local path'))
        unknown = set(self.documents[name].values) - {s.name for s in SCOPES[scope]}
        if unknown:
            issues.append(Issue('compatibility', name, f'{len(unknown)} unknown literal setting(s) will be preserved, not interpreted.', True))
        return issues

    def provider_issues(self, identifier, values, filesystem=True):
        try:
            from storage import Store, prefix
            from policy import settings
            kind = values.get('TARGET_TYPE')
            if kind in ('s3', 'azure_blob') or filesystem:
                store = Store(identifier, values)  # No network I/O in constructor.
                settings(store)
            if kind in ('s3', 'azure_blob'):
                prefix(values.get('S3_PREFIX' if kind == 's3' else 'AZURE_BLOB_PREFIX', ''))
            if kind == 's3' and values.get('S3_SERVER_SIDE_ENCRYPTION') == 'aws:kms' and not values.get('S3_SSE_KMS_KEY_ID'):
                raise Failure('KMS encryption requires a KMS key ID', 78)
            if kind == 'filesystem' and filesystem:
                write_directory(values['FILESYSTEM_PATH'])
            for key in ('S3_ACCESS_KEY_ID', 'S3_SESSION_TOKEN', 'S3_SSE_KMS_KEY_ID'):
                if kind == 's3' and any(c in values.get(key, '') for c in '\r\n'):
                    raise Failure('Header credentials cannot contain line breaks', 78)
        except Failure as exc:
            return [Issue('dependency' if exc.code == 69 else 'security' if exc.code == 77 else 'configuration', 'target:' + identifier, str(exc))]
        return []

    def validate_target(self, identifier):
        name = 'target:' + identifier
        if name not in self.values:
            return [Issue('configuration', name, 'Unknown target')]
        return self.scope_issues(name) + self.provider_issues(identifier, self.values[name])

    def validate(self, filesystem=True):
        issues = []
        def problem(category, name, message, warning=False):
            issues.append(Issue(category, name, message, warning))
        try:
            active = self.active_names()
        except Failure as exc:
            return [Issue('configuration', 'main', str(exc))]
        if self.target_error:
            return [Issue('security' if self.target_error.code == 77 else 'configuration', 'destinations', str(self.target_error))]
        if self.pending:
            problem('security', 'transaction', 'An interrupted transaction requires recovery before backups or further changes.')
        for name in active:
            issues.extend(self.scope_issues(name, filesystem))
        c = self.main
        for name in self.errors:
            if name not in active:
                problem('compatibility', name, 'Inactive file cannot be safely edited; it is preserved. Fix literal syntax/permissions before enabling.', True)
        sections = {'main': c}
        for identifier in self.target_ids():
            sections[identifier] = self.values['target:' + identifier]
        if len(sections) == 1 and c['REMOTE_STORAGE_TYPE'] != 'none':
            sections['legacy'] = {**self.values['storage'], 'TARGET_TYPE': c['REMOTE_STORAGE_TYPE'], 'TARGET_REQUIRED': c['REMOTE_UPLOAD_REQUIRED']}
        try:
            validate_operations(sections)
        except Failure as exc:
            problem('configuration', 'operations', str(exc))
        required = [('main', ('UNIFI_URL', 'UNIFI_USERNAME', 'UNIFI_PASSWORD'))]
        if 'graph' in active:
            required.append(('graph', ('TENANT_ID', 'CLIENT_ID', 'CLIENT_SECRET', 'MAIL_FROM', 'MAIL_TO')))
        for name, keys in required:
            for key in keys:
                if not self.values[name][key] or self.values[name][key] == 'CHANGE_ME':
                    problem('configuration', name + '.' + key, 'Required value is missing or is a placeholder.')
        for left, right, message in [('CURL_MAX_TIME', 'CURL_CONNECT_TIMEOUT', 'Total timeout is below connection timeout'),
                                      ('STALE_CRITICAL_HOURS', 'STALE_WARNING_HOURS', 'Critical freshness threshold must exceed warning')]:
            if c[left].isdigit() and c[right].isdigit() and int(c[left]) < int(c[right]) + (left == 'STALE_CRITICAL_HOURS'):
                problem('configuration', left, message)
        if all(c[k].isdigit() for k in ('RETENTION_COUNT', 'RETENTION_MIN_COUNT')) and int(c['RETENTION_COUNT']) and int(c['RETENTION_COUNT']) < int(c['RETENTION_MIN_COUNT']):
            problem('configuration', 'retention', 'Maximum count must be zero or at least the minimum count.')
        if c['BACKUP_TARGETS'] and c['REMOTE_STORAGE_TYPE'] != 'none':
            problem('compatibility', 'destinations', 'Legacy storage is dormant: multi-target configuration takes precedence. No migration or duplicate upload occurs.', True)
        for name, values in sections.items():
            if name == 'main':
                continue
            issues.extend(self.provider_issues(name, values, filesystem))
        for name in ('storage', *['target:' + x for x in self.target_ids()], 'webhook'):
            if name not in active:
                continue
            values = self.values[name]
            prefix = 'WEBHOOK' if name == 'webhook' else 'STORAGE'
            lo, hi = values[prefix + '_CONNECT_TIMEOUT'], values[prefix + '_MAX_TIME']
            if lo.isdigit() and hi.isdigit() and int(lo) > int(hi):
                problem('configuration', name, 'Connection timeout exceeds total timeout.')
        if 'ntfy' in active:
            v = self.values['ntfy']
            if v['NTFY_BASE_URL'].endswith('/'):
                problem('configuration', 'ntfy.NTFY_BASE_URL', 'The existing ntfy client requires an origin without a trailing slash.')
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', v['NTFY_TOPIC']):
                problem('configuration', 'ntfy', 'A safe nonempty ntfy topic is required.')
            if v['NTFY_ALLOW_ANONYMOUS'] != 'true' and (not v['NTFY_ACCESS_TOKEN'] or v['NTFY_ACCESS_TOKEN'] == 'CHANGE_ME'):
                problem('configuration', 'ntfy', 'A token is required unless anonymous publishing is explicitly enabled.')
        if 'graph' in active:
            for key in ('TENANT_ID', 'CLIENT_ID'):
                if not re.fullmatch(r'[A-Za-z0-9.-]+', self.values['graph'][key]):
                    problem('configuration', 'graph.' + key, 'Identifier must be a safe tenant/client identifier.')
            for key in ('MAIL_FROM', 'MAIL_TO'):
                if not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+', self.values['graph'][key]):
                    problem('configuration', 'graph.' + key, 'Provide one mailbox address (no display name).')
        if 'storage' in active and c['REMOTE_STORAGE_TYPE'] == 's3' and self.values['storage']['S3_ENDPOINT'].endswith('/'):
            problem('configuration', 'storage.S3_ENDPOINT', 'The legacy uploader requires an origin without a trailing slash.')
        # Header credentials cannot contain line breaks, unlike login passwords.
        for name in active:
            for key in ('NTFY_ACCESS_TOKEN', 'WEBHOOK_BEARER_TOKEN', 'S3_SESSION_TOKEN', 'S3_ACCESS_KEY_ID', 'S3_SSE_KMS_KEY_ID'):
                if any(ch in self.values[name].get(key, '') for ch in '\r\n'):
                    problem('security', name + '.' + key, 'Header credentials cannot contain line breaks.')
        if filesystem:
            try:
                read_access(self.config)
                for name in active:
                    read_access(self.paths[name])
                for spec in SCOPES['main']:
                    if spec.name not in ALIASES.values() and active_field(spec, c, c) and spec.kind in ('private_path', 'certificate') and c[spec.name]:
                        read_access(c[spec.name])
                for name in active:
                    for spec in SCOPES[self.scopes[name]]:
                        if spec.kind == 'certificate' and self.values[name][spec.name]:
                            read_access(self.values[name][spec.name])
                for identifier in self.target_ids():
                    values = self.values['target:' + identifier]
                    if values['TARGET_TYPE'] == 'filesystem':
                        write_directory(values['FILESYSTEM_PATH'])
            except Failure as exc:
                problem('security', 'systemd access', str(exc))
            for command in ('bash', 'curl', 'python3', 'flock', 'sha256sum', 'stat', 'find'):
                if not shutil.which(command):
                    problem('dependency', command, 'Required backup dependency is missing.')
            try:
                write_directory(c['BACKUP_DIR'])
                write_directory(c['RESTORE_STAGING_DIR'])
                for key, basename in [('STATUS_FILE', 'status.json'), ('CATALOG_FILE', 'catalog.json')]:
                    path = Path(c[key])
                    if path.name != basename or str(path.parent) not in ('/var/lib/unifi-backup', c['BACKUP_DIR']):
                        raise Failure(key + ' must be directly under /var/lib/unifi-backup or BACKUP_DIR with its original basename', 78)
                p = Path(c['LOCK_FILE'])
                if str(p.parent) not in ('/run/unifi-backup', c['BACKUP_DIR']) or not re.fullmatch(r'[A-Za-z0-9._-]+\.lock', p.name):
                    raise Failure('LOCK_FILE must be directly under /run/unifi-backup or BACKUP_DIR', 78)
                if c['VERIFY_DECRYPT_CHECK'] == 'true':
                    if not c['VERIFY_IDENTITY_FILE']:
                        raise Failure('Existing protected VERIFY_IDENTITY_FILE required; the wizard will not create one', 78)
                    if not checked(c['VERIFY_IDENTITY_FILE'], private=True).is_file():
                        raise Failure('Verification identity is unavailable', 78)
                if c['ENCRYPTION_TYPE'] == 'age':
                    data = self.recipients if self.recipients is not None else read_bytes(c['AGE_RECIPIENTS_FILE'])
                    if data is None:
                        raise Failure('Public age recipient file is missing', 78)
                    public_recipients(data)
            except Failure as exc:
                problem('dependency' if exc.code == 69 else 'security', 'paths/encryption', str(exc))
        if self.schedule is not None:
            try:
                calendar(self.schedule)
            except Failure as exc:
                problem('dependency' if exc.code == 69 else 'configuration', 'schedule', str(exc))
        problem('systemd', 'overrides', 'Existing administrator drop-ins are retained. Review effective unit access/schedules; later overrides may take precedence.', True)
        return issues

    def systemd_files(self):
        result = {}
        def unit_quote(value):
            if any(ord(c) < 32 for c in value):
                raise Failure('Control characters are not permitted in systemd paths', 78)
            return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'
        if self.schedule is not None:
            result[self.units / 'unifi-backup.timer.d/90-unifi-backup-configure.conf'] = HEADER + '[Timer]\nOnCalendar=\nOnCalendar=' + self.schedule + '\n'
        directory = self.main['BACKUP_DIR']
        filesystem_targets = [self.values['target:' + t]['FILESYSTEM_PATH'] for t in self.target_ids() if self.values['target:' + t]['TARGET_TYPE'] == 'filesystem']
        custom_config = str(self.config) != '/etc/unifi-backup/unifi-backup.env'
        for service, command in SERVICES.items():
            owned = self.units / (service + '.d') / '90-unifi-backup-configure.conf'
            paths = []
            if service != 'unifi-backup-monitor.service' and directory != '/var/backups/unifi':
                paths.append(directory)
            if Path(self.main['STATUS_FILE']).parent == Path(directory):
                paths.append(directory)
            if service in ('unifi-backup.service', 'unifi-backup-retry.service'):
                paths += filesystem_targets
            if paths or custom_config or owned.exists():
                text = HEADER + '[Service]\n'
                if paths:
                    text += 'ReadWritePaths=' + ' '.join(unit_quote(x) for x in sorted(set(paths))) + '\n'
                if custom_config:
                    parts = command.split()
                    text += 'ExecStart=\nExecStart=/usr/local/sbin/' + parts[0] + ' --config ' + unit_quote(str(self.config)) + (' ' + ' '.join(parts[1:]) if parts[1:] else '') + '\n'
                result[owned] = text
        return result

    def current_schedule(self):
        """Best-effort read-only display; unknown overrides are never rewritten."""
        if self.schedule is not None:
            return self.schedule
        if shutil.which('systemctl'):
            try:
                result = subprocess.run(['systemctl', 'show', 'unifi-backup.timer', '--property=TimersCalendar', '--value'],
                                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5, check=False)
                if result.returncode == 0:
                    expressions = re.findall(r'OnCalendar=([^;}]+)', result.stdout.decode('utf-8', 'replace'))
                    if len(expressions) == 1:
                        return expressions[0].strip()
            except (OSError, subprocess.TimeoutExpired):
                pass
        owned = self.units / 'unifi-backup.timer.d/90-unifi-backup-configure.conf'
        data = read_bytes(owned, private=False)
        if data and data.startswith(HEADER.encode()):
            expressions = [line[11:] for line in data.decode().splitlines() if line.startswith('OnCalendar=') and len(line) > 11]
            if len(expressions) == 1:
                return expressions[0]
        return None

    def plan(self):
        self.refresh()
        plan, seen = [], set()
        for name, doc in self.documents.items():
            values = self.values[name]
            changed = {k: values[k] for k in self.dirty.get(name, set()) if k not in doc.values or doc.values[k] != values[k]}
            if name == 'main' and self.snapshots[name] is None:
                changed = {k: v for k, v in values.items() if k in defaults('main')}
            if not changed:
                continue
            path = self.paths[name]
            if path in seen:
                raise Failure('Two managed scopes refer to the same file; separate their paths first', 78)
            seen.add(path)
            plan.append({'path': path, 'mode': 0o600, 'before': self.snapshots[name], 'data': doc.render(changed), 'scope': name, 'keys': list(changed)})
        if self.recipients is not None:
            public_recipients(self.recipients, check_age=False)
            path = Path(self.main['AGE_RECIPIENTS_FILE'])
            before = self.extra_snapshot.setdefault(path, fingerprint(path))
            if read_bytes(path) != self.recipients:
                plan.append({'path': path, 'mode': 0o600, 'before': before, 'data': self.recipients, 'scope': 'recipients', 'keys': ['public recipients']})
        for path, text in self.systemd_files().items():
            data = text.encode()
            previous = read_bytes(path, private=False)
            before = self.extra_snapshot.setdefault(path, fingerprint(path, private=False))
            if previous is not None and not previous.startswith(HEADER.encode()):
                raise Failure('A custom file occupies the manager drop-in name; no override was overwritten', 78)
            if previous != data:
                plan.append({'path': path, 'mode': 0o644, 'before': before, 'data': data, 'scope': 'systemd', 'keys': ['schedule/write access/config path']})
        if len({item['path'] for item in plan}) != len(plan):
            raise Failure('Configuration/recipient/drop-in paths overlap; apply refused', 78)
        return plan

    def summary(self):
        rows = []
        for name in self.values:
            if name not in self.documents:
                continue
            old = self.documents[name].values
            specs = {s.name: s for s in SCOPES[self.scopes[name]]}
            for key, value in self.values[name].items():
                if key not in specs:
                    continue
                spec = specs[key]
                redact = lambda v: '[set; hidden]' if v else '[empty]'
                rows.append({'section': name, 'group': spec.group, 'setting': key,
                             'old': redact(old.get(key, '')) if spec.sensitive else old.get(key, '(default)'),
                             'new': redact(value) if spec.sensitive else value,
                             'changed': key in self.dirty.get(name, set()) and value != old.get(key, spec.default), 'sensitive': spec.sensitive})
        return rows

    def apply(self):
        issues = self.validate()
        if any(not x.warning for x in issues):
            raise Failure('Configuration failed validation; nothing was applied', 78)
        plan = self.plan()
        directories = [(Path(self.main['BACKUP_DIR']), 0o700)]
        observations = [(self.paths[name], before) for name, before in self.snapshots.items() if name not in self.errors]
        def preflight():
            if any(not issue.warning for issue in self.validate()):
                raise Failure('Configuration no longer passes validation; nothing was applied', 78)
        return self.transaction.apply(plan, [self.original_main['LOCK_FILE'], self.main['LOCK_FILE']], directories, observations, preflight)

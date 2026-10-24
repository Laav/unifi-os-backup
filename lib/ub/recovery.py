"""Find and prepare trusted artifacts; never calls a controller restore API."""
import json
import os
from pathlib import Path
import shutil
import tempfile

from core import Failure, NAME, atomic, digest, integer, local_files, metadata, private_dir, safe_path, state_dir
from storage import Store
from verify import decrypt, structure, verify


def inventory(c, store=None):
    entries = []
    if store:
        for name in reversed(store.listing()):
            if not name.endswith('.json'):
                continue
            old_max = store.maximum
            try:
                store.maximum = 65536
                with tempfile.TemporaryDirectory(prefix='.inventory.', dir=state_dir(c)) as directory:
                    sidecar = Path(directory) / name
                    store.download(name, sidecar)
                    raw = json.loads(sidecar.read_text(encoding='utf-8'))
                backup = raw.get('backup', {})
                if not isinstance(backup, dict) or name != str(backup.get('filename', '')) + '.json' or not NAME.fullmatch(backup.get('filename', '')):
                    continue
                if not isinstance(backup.get('id'), str) or not backup['id']:
                    continue
                entries.append({'backup': backup, 'origin': store.id})
            except (Failure, OSError, ValueError, TypeError):
                continue
            finally:
                store.maximum = old_max
    else:
        for path in local_files(c):
            try:
                entries.append({'backup': metadata(path)['backup'], 'origin': 'local'})
            except Failure:
                continue
    return sorted(entries, key=lambda x: x['backup']['filename'], reverse=True)


def display_entry(entry):
    allowed = ('id', 'filename', 'size_bytes', 'sha256', 'source', 'hostname', 'created_at', 'unifi_os_version')
    return {'backup': {key: entry['backup'].get(key) for key in allowed if key in entry['backup']}, 'origin': entry['origin']}


def restore(c, args, store=None):
    entries = inventory(c, store)
    if args.backup_id:
        entries = [e for e in entries if e['backup']['id'] == args.backup_id]
        if len(entries) > 1:
            raise Failure('Ambiguous backup ID', 65)
    if args.date:
        entries = [e for e in entries if e['backup']['created_at'].startswith(args.date)]
    if args.list:
        return {'backups': [display_entry(e) for e in entries]}
    if not entries:
        raise Failure('No eligible backups found', 66)
    if not (args.latest or args.backup_id or args.date):
        raise Failure('Choose --latest, --backup-id, --date or --list', 64)
    if args.dry_run:
        return {'dry_run': True, 'selected': display_entry(entries[0]), 'restore_tested': False, 'readiness': 'not_checked'}
    skipped = []
    for entry in entries if args.latest else entries[:1]:
        name = entry['backup']['filename']
        with tempfile.TemporaryDirectory(prefix='.recovery.', dir=state_dir(c)) as directory:
            staging = Path(directory)
            try:
                if store:
                    candidate = staging / name
                    store.download(name, candidate)
                    old_max = store.maximum
                    try:
                        store.maximum = 65536
                        store.download(name + '.json', Path(str(candidate) + '.json'))
                    finally:
                        store.maximum = old_max
                else:
                    candidate = safe_path(Path(c.get('BACKUP_DIR', '/var/backups/unifi')) / name)
                doc = metadata(candidate)
                if doc['backup'] != entry['backup']:
                    raise Failure('Backup discovery identity changed during retrieval')
                checked = verify(candidate, c, args.identity if args.identity else None)
                if not checked['success']:
                    raise Failure('Recovery verification failed: ' + checked.get('error', 'unknown'))
                report = {'schema_version': 1, 'backup_id': doc['backup']['id'], 'backup_date': doc['backup'].get('created_at'),
                          'origin': entry['origin'], 'controller': doc['backup'].get('source'),
                          'unifi_os_version': doc['backup'].get('unifi_os_version'), 'verification': checked,
                          'compatibility': ['Confirm controller model and UniFi OS/application versions manually before import'],
                          'restore_tested': False, 'readiness': 'verified_encrypted' if name.endswith('.age') and not args.identity else 'prepared',
                          'manual_steps': ['Use UniFi Control Plane Upload & Restore on an isolated or approved controller'], 'skipped_invalid': skipped}
                if args.verify_only:
                    return report
                destination = private_dir(args.output or c.get('RESTORE_STAGING_DIR', '/var/lib/unifi-backup/restore'))
                if os.name != 'nt' and destination.stat().st_mode & 0o077:
                    raise Failure('Restore directory must have mode 0700', 78)
                required = doc['backup']['size_bytes'] + int(doc.get('encryption', {}).get('plaintext_size_bytes', 0))
                if shutil.disk_usage(destination).free < required + 1048576:
                    raise Failure('Insufficient free space for restore preparation', 73)
                source = candidate
                if name.endswith('.age') and args.identity:
                    plaintext = staging / 'recovered.unifi'
                    decrypt(candidate, args.identity, plaintext, integer(c, 'RESTORE_MAX_BYTES', 10737418240, 1, 1099511627776))
                    structure(plaintext)
                    source = plaintext
                    name = doc['encryption']['original_filename']
                    if not NAME.fullmatch(name) or name.endswith('.age'):
                        raise Failure('Invalid original plaintext filename', 65)
                final = safe_path(destination / name)
                if final.exists() or Path(str(final) + '.restore.json').exists():
                    raise Failure('Restore output exists; choose a new private directory', 73)
                fd, temporary = tempfile.mkstemp(prefix='.restore.', dir=destination)
                try:
                    with os.fdopen(fd, 'wb') as dst, source.open('rb') as src:
                        shutil.copyfileobj(src, dst)
                        dst.flush()
                        os.fsync(dst.fileno())
                    os.link(temporary, final)
                finally:
                    Path(temporary).unlink(missing_ok=True)
                report['output_file'] = str(final)
                report['output_sha256'] = digest(final)
                atomic(str(final) + '.restore.json', report)
                return report
            except Failure as exc:
                skipped.append({'filename': name, 'error': str(exc)})
                if not args.latest or exc.code in (73, 78):
                    raise
    raise Failure('No backup passed recovery verification', 74)

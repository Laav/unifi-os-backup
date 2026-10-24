"""Safe metadata, path and state primitives shared by the Bash CLI tools."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import time
import sys

NAME = re.compile(r'^unifi_os_backup_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.unifi(?:\.age)?$')
OBJECT = re.compile(NAME.pattern[:-1] + r'(?:\.json)?$')
SHA = re.compile(r'^[a-f0-9]{64}$')
VERSION = '1.3.0'


def event(c, name, message, **fields):
    record = {'timestamp': iso(), 'program': 'unifi-backup-operations', 'level': 'info',
              'event': name, 'message': message, **fields}
    if c.get('LOG_FORMAT') == 'json':
        print(json.dumps(record, separators=(',', ':'), ensure_ascii=True), file=sys.stderr)
    else:
        details = ' '.join(f'{key}={value}' for key, value in fields.items())
        print(f'unifi-backup-operations: {message}' + (' ' + details if details else ''), file=sys.stderr)


class Failure(Exception):
    def __init__(self, message, code=74):
        super().__init__(message)
        self.code = code


def now():
    return int(time.time())


def iso(epoch=None):
    return dt.datetime.fromtimestamp(now() if epoch is None else epoch, dt.timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def safe_path(path):
    path = Path(path)
    if not path.is_absolute():
        raise Failure('An absolute path is required', 78)
    for part in [path, *path.parents]:
        if part.is_symlink():
            raise Failure('Symbolic links are not allowed', 78)
    return path


def private_dir(path):
    path = safe_path(path)
    if path == path.parent:
        raise Failure('Root directory is not a private destination', 78)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != 'nt':
        info = path.stat()
        if info.st_uid != os.geteuid() or info.st_mode & 0o022:
            raise Failure('Private directory has unsafe owner or write permissions', 78)
    return path


def regular(path, private=False):
    path = safe_path(path)
    if not path.is_file():
        raise Failure('Required regular file is missing', 66)
    if os.name != 'nt' and private:
        info = path.stat()
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise Failure('File must be owned by the operator with mode 0600', 78)
    return path


def load(path, limit=1048576):
    path = regular(path)
    if path.stat().st_size > limit:
        raise Failure('JSON file exceeds safety limit', 65)
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, UnicodeError):
        raise Failure('Invalid JSON metadata', 65) from None
    if not isinstance(value, dict):
        raise Failure('JSON object required', 65)
    return value


def atomic(path, value, mode=0o600):
    path = safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.atomic.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as out:
            if isinstance(value, str):
                out.write(value)
            else:
                json.dump(value, out, indent=2, ensure_ascii=True)
                out.write('\n')
            out.flush()
            os.fsync(out.fileno())
        os.chmod(temp, mode)
        for attempt in range(6):
            try:
                os.replace(temp, path)
                break
            except PermissionError:
                # Windows virus scanners briefly hold freshly read files.
                # Linux errors propagate immediately.
                if os.name != 'nt' or attempt == 5:
                    raise
                time.sleep(0.05)
        if os.name != 'nt':
            descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        Path(temp).unlink(missing_ok=True)


def digest(path):
    h = hashlib.sha256()
    with regular(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def integer(c, key, default, low=0, high=1000000):
    raw = str(c.get(key, default))
    if not re.fullmatch(r'[0-9]+', raw) or not low <= int(raw) <= high:
        raise Failure(f'{key} must be an integer between {low} and {high}', 78)
    return int(raw)


def boolean(c, key, default=False):
    raw = c.get(key, 'true' if default else 'false')
    if raw not in ('true', 'false'):
        raise Failure(f'{key} must be true or false', 78)
    return raw == 'true'


def state_dir(c):
    return private_dir(Path(c.get('STATUS_FILE', '/var/lib/unifi-backup/status.json')).parent)


def state(c, name, default=None):
    path = state_dir(c) / name
    if not path.exists():
        return {} if default is None else default
    return load(path, 64 * 1024 * 1024)


def save_state(c, name, value):
    atomic(state_dir(c) / name, value)


def local_files(c):
    directory = safe_path(c.get('BACKUP_DIR', '/var/backups/unifi'))
    if directory == directory.parent:
        raise Failure('BACKUP_DIR may not be a filesystem root', 78)
    if not directory.is_dir():
        return []
    return sorted((p for p in directory.iterdir() if NAME.fullmatch(p.name) and p.is_file() and not p.is_symlink()), key=lambda p: p.name, reverse=True)


def metadata(path):
    path = regular(path)
    if not NAME.fullmatch(path.name) or path.stat().st_size == 0:
        raise Failure('Not a complete managed backup filename', 65)
    try:
        dt.datetime.strptime(path.name[16:35], '%Y-%m-%d_%H-%M-%S')
    except ValueError:
        raise Failure('Managed filename contains an invalid calendar timestamp', 65) from None
    doc = load(str(path) + '.json', 65536)
    b = doc.get('backup', {})
    if doc.get('schema_version') not in (1, 2) or not isinstance(b, dict):
        raise Failure('Unsupported metadata schema', 65)
    if b.get('filename') != path.name or not isinstance(b.get('id'), str) or not b['id']:
        raise Failure('Metadata identity/filename mismatch', 65)
    if not SHA.fullmatch(str(b.get('sha256', ''))) or type(b.get('size_bytes')) is not int or b['size_bytes'] <= 0:
        raise Failure('Invalid metadata checksum or size', 65)
    return doc


def select(c, args):
    if getattr(args, 'file', None):
        return [regular(args.file)]
    items = local_files(c)
    bid = getattr(args, 'backup_id', None)
    if bid:
        catalog = Path(c.get('CATALOG_FILE', '/var/lib/unifi-backup/catalog.json'))
        candidates = []
        if catalog.exists():
            entries = load(catalog, 64 * 1024 * 1024).get('backups', [])
            names = [e.get('filename') for e in entries if isinstance(e, dict) and e.get('id') == bid]
            for name in names:
                if not isinstance(name, str) or not NAME.fullmatch(name):
                    raise Failure('Unsafe catalog object mapping', 65)
                candidate = Path(c.get('BACKUP_DIR', '/var/backups/unifi')) / name
                if candidate in items:
                    candidates.append(candidate)
        if not candidates:
            for path in items:
                try:
                    if metadata(path)['backup']['id'] == bid:
                        candidates.append(path)
                except Failure:
                    continue
        items = candidates
        if len(items) != 1:
            raise Failure('Backup ID is missing or ambiguous', 66)
    if getattr(args, 'latest', False):
        items = items[:1]
    if not items:
        raise Failure('No matching backups found', 66)
    return items


def metric(c, filename, values):
    atomic(state_dir(c) / filename, ''.join(f'# TYPE {k} {"counter" if k.endswith("_total") else "gauge"}\n{k} {v}\n' for k, v in values.items()), 0o644)

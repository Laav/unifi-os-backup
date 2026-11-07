"""Durable staged file transactions. Caller supplies a fully validated plan."""
from contextlib import ExitStack, contextmanager
import json
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
import uuid

from core import Failure, atomic
from config_files import checked, fingerprint, read_bytes

HEADER = '# Managed by unifi-backup-configure; edit through the manager.\n'


def mkdir(path, mode=0o700):
    path = checked(path, directory=True)
    missing, current = [], path
    while not current.exists():
        missing.append(current); current = current.parent
    for item in reversed(missing):
        item.mkdir(mode=mode)
        sync_parent(item)
    checked(path, private=mode == 0o700, directory=True)
    return path


def sync_parent(path):
    if os.name != 'nt':
        fd = os.open(Path(path).parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def write(path, data, mode):
    """atomic() accepts literal text, not bytes; never expose it in an argv."""
    checked(path, private=mode == 0o600)
    atomic(path, data.decode('utf-8'), mode)


def remove(path):
    checked(path).unlink(missing_ok=True)
    sync_parent(path)


@contextmanager
def read_lock(path):
    """Non-mutating shared snapshot lock; a missing inode is not created."""
    path = checked(path, private=True)
    if not path.exists():
        yield
        return
    if os.name == 'nt':
        # Windows is a test host only. Its lock API requires a writable handle.
        with lock(path):
            yield
        return
    import fcntl
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Failure('Configuration apply is in progress; retry inspection later', 75) from None
        yield
    finally:
        os.close(fd)


@contextmanager
def lock(path):
    path = checked(path, private=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        if os.name == 'nt':
            import msvcrt
            if os.fstat(fd).st_size == 0:
                os.write(fd, b'\0')
            os.lseek(fd, 0, 0)
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            except OSError:
                raise Failure('Another configuration or backup operation holds the lock', 75) from None
        else:
            import fcntl
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise Failure('Another configuration or backup operation holds the lock', 75) from None
        yield
    finally:
        os.close(fd)


def reload_units():
    try:
        result = subprocess.run(['systemctl', 'daemon-reload'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise Failure('systemd daemon-reload failed', 69) from None
    if result.returncode:
        raise Failure('systemd daemon-reload failed', 69)


class Transaction:
    def __init__(self, config_path, units_dir='/etc/systemd/system'):
        self.root = Path(config_path).parent
        self.units = Path(units_dir)
        self.pending = self.root / '.configure-pending'
        self.history = self.root / '.configure-transactions'

    def pending_id(self):
        data = read_bytes(self.pending)
        if data is None:
            return None
        value = data.decode('ascii').strip()
        if not re.fullmatch(r'[a-f0-9]{32}', value):
            raise Failure('Invalid pending transaction marker; administrator recovery required', 78)
        return value

    def journal(self, identifier):
        if not re.fullmatch(r'[a-f0-9]{32}', identifier):
            raise Failure('Invalid configuration transaction identifier', 64)
        folder = checked(self.history / identifier, private=True, directory=True)
        raw = read_bytes(folder / 'manifest.json')
        if raw is None:
            raise Failure('Configuration transaction journal is missing', 66)
        try:
            doc = json.loads(raw)
        except ValueError:
            raise Failure('Invalid transaction journal; manual recovery required', 65) from None
        if doc.get('schema_version') != 1 or doc.get('config_root') != str(self.root) or doc.get('units_root') != str(self.units):
            raise Failure('Transaction root/schema mismatch; recovery refused', 78)
        entries = doc.get('entries')
        if not isinstance(entries, list) or not 1 <= len(entries) <= 128:
            raise Failure('Invalid transaction entries', 65)
        for index, entry in enumerate(entries):
            if entry.get('index') != index or entry.get('mode') not in (0o600, 0o644):
                raise Failure('Invalid transaction entry', 65)
            checked(entry['path'])
        return folder, doc

    def recover_files(self, identifier):
        folder, doc = self.journal(identifier)
        # Preflight everything before rolling back even one file. Never accept
        # arbitrary changed current files as if they belonged to this transaction.
        for entry in doc['entries']:
            current = fingerprint(entry['path'], private=entry['mode'] == 0o600)
            if current not in (entry['before'], entry.get('after')):
                raise Failure('Configuration changed since the transaction; automatic rollback refused', 75)
            if entry['before'] is not None:
                prior = read_bytes(folder / f"{entry['index']}.before")
                if prior is None or hashlib.sha256(prior).hexdigest() != entry['before'][0]:
                    raise Failure('Rollback preimage missing or corrupt; manual recovery required', 66)
        for entry in reversed(doc['entries']):
            path = Path(entry['path'])
            if entry['before'] is None:
                remove(path)
            else:
                write(path, read_bytes(folder / f"{entry['index']}.before"), entry['before'][1])
        if any(e['mode'] == 0o644 for e in doc['entries']):
            reload_units()
        doc['state'] = 'rolled_back'
        atomic(folder / 'manifest.json', doc)
        remove(self.pending)

    def rollback(self, identifier=None, confirmed=False):
        if not confirmed:
            raise Failure('Rollback/recovery requires explicit confirmation (--yes)', 64)
        checked(self.root, private=True, directory=True)
        with lock(self.root / '.configure.lock'):
            pending = self.pending_id()
            identifier = identifier or pending
            if not identifier:
                raise Failure('No pending configuration transaction', 66)
            if pending and pending != identifier:
                raise Failure('Recover the pending transaction first', 75)
            folder, doc = self.journal(identifier)
            if doc['state'] == 'rolled_back':
                if pending:
                    remove(self.pending)
                return identifier
            with ExitStack() as stack:
                for path in doc['operation_locks']:
                    mkdir(Path(path).parent)
                    stack.enter_context(lock(path))
                if not pending:
                    write(self.pending, (identifier + '\n').encode(), 0o600)
                self.recover_files(identifier)
            return identifier

    def apply(self, plan, operation_locks, directories=(), observations=(), preflight=None):
        if not plan:
            return None
        if len(plan) > 128:
            raise Failure('Too many configuration changes in one transaction', 78)
        mkdir(self.root)
        with lock(self.root / '.configure.lock'):
            if self.pending_id():
                raise Failure('An interrupted configuration transaction requires --recover --yes', 75)
            with ExitStack() as stack:
                for path in sorted(set(operation_locks)):
                    mkdir(Path(path).parent)
                    stack.enter_context(lock(path))
                for path, mode in directories:
                    mkdir(path, mode)
                # Conflict checks happen after all locks and before staging.
                for path, before in observations:
                    if fingerprint(path) != before:
                        raise Failure('A configuration dependency changed while being edited; reload before applying', 75)
                for item in plan:
                    if fingerprint(item['path'], private=item['mode'] == 0o600) != item['before']:
                        raise Failure('Configuration changed while it was being edited; reload before applying', 75)
                if preflight:
                    preflight()
                mkdir(self.history)
                identifier = uuid.uuid4().hex
                folder = mkdir(self.history / identifier)
                entries = []
                for index, item in enumerate(plan):
                    path, mode = Path(item['path']), item['mode']
                    mkdir(path.parent, 0o700 if mode == 0o600 else 0o755)
                    prior = read_bytes(path, private=mode == 0o600)
                    if prior is not None:
                        write(folder / f'{index}.before', prior, 0o600)
                    write(folder / f'{index}.after', item['data'], 0o600)
                    entries.append({'index': index, 'path': str(path), 'mode': mode, 'before': item['before'], 'after': None})
                doc = {'schema_version': 1, 'config_root': str(self.root), 'units_root': str(self.units),
                       'state': 'staged', 'operation_locks': sorted(set(operation_locks)), 'entries': entries}
                atomic(folder / 'manifest.json', doc)
                write(self.pending, (identifier + '\n').encode(), 0o600)
                try:
                    # Record the expected postimage before replacement so power
                    # loss between replacement and journal flush is recoverable.
                    for entry in entries:
                        data = read_bytes(folder / f"{entry['index']}.after")
                        entry['after'] = [hashlib.sha256(data).hexdigest(), entry['mode'], os.geteuid() if os.name != 'nt' else 0,
                                          os.getegid() if os.name != 'nt' else 0]
                        if os.name == 'nt':
                            # Windows development tests have synthetic uid/gid
                            # and chmod semantics; derive the test postimage.
                            entry['after'][1:] = [stat.S_IMODE((folder / f"{entry['index']}.after").stat().st_mode), 0, 0]
                        atomic(folder / 'manifest.json', doc)
                        write(entry['path'], data, entry['mode'])
                    if any(e['mode'] == 0o644 for e in entries):
                        reload_units()
                    doc['state'] = 'complete'
                    atomic(folder / 'manifest.json', doc)
                    remove(self.pending)
                except BaseException as exc:
                    # SIGKILL/power loss cannot run this handler. The durable
                    # marker instead blocks readers until explicit recovery.
                    try:
                        self.recover_files(identifier)
                    except BaseException:
                        raise Failure('Apply interrupted and rollback incomplete; run --recover --yes before backups', 75) from None
                    if not isinstance(exc, Exception):
                        raise
                    raise Failure('Apply failed; all configuration files were rolled back', 73) from None
                return identifier

"""Byte integrity and explicit, limited format capability checks."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from core import Failure, digest, integer, iso, load, metadata, metric, now, regular, save_state, state, state_dir


def structure(path):
    with regular(path).open('rb') as stream:
        head = stream.read(4096).lstrip(b'\xef\xbb\xbf \t\r\n')
    if head.lower().startswith((b'<!doctype html', b'<html', b'<head', b'<body')) or head.startswith((b'{', b'[')):
        raise Failure('Unexpected HTML/JSON response instead of a UniFi system backup', 65)
    # Ubiquiti does not publish a stable .unifi container specification. Never
    # infer parseability from invented magic bytes or claim a restore test.
    return {'status': 'limited', 'error_page_check': 'passed', 'container': 'opaque_unifi', 'restore_tested': False}


def decrypt(path, identity, destination, maximum):
    identity = regular(identity, private=True)
    if not shutil.which('age'):
        raise Failure('age is required for decryption', 69)
    # Identity path is public process metadata; identity contents never are.
    env = os.environ.copy()
    env['AGE_NO_PLUGIN'] = '1'
    with destination.open('xb') as output:
        process = subprocess.Popen(['age', '--decrypt', '--identity', str(identity), str(path)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
        h, size = hashlib.sha256(), 0
        try:
            while True:
                block = process.stdout.read(1024 * 1024)
                if not block:
                    break
                size += len(block)
                if size > maximum:
                    raise Failure('Decrypted data exceeds configured size limit', 74)
                output.write(block)
                h.update(block)
            if process.wait(timeout=30) != 0 or size == 0:
                raise Failure('age decryption failed; identity mismatch or damaged ciphertext', 74)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            process.stdout.close()
    return size, h.hexdigest()


def verify(path, c, identity=None):
    result = {'filename': Path(path).name, 'checked_at': iso(), 'success': False,
              'hash_valid': False, 'metadata_valid': False, 'decryption': 'not_requested',
              'structure': {'status': 'not_checked'}, 'restore_tested': False}
    try:
        path = regular(path)
        doc = metadata(path)
        result['backup_id'] = doc['backup']['id']
        result['metadata_valid'] = True
        if path.stat().st_size != doc['backup']['size_bytes']:
            raise Failure('Backup size differs from original metadata')
        if digest(path) != doc['backup']['sha256']:
            raise Failure('Backup SHA256 differs from original metadata')
        result['hash_valid'] = True
        if path.name.endswith('.age'):
            with path.open('rb') as stream:
                if stream.read(22) != b'age-encryption.org/v1\n':
                    raise Failure('Expected an age v1 ciphertext header', 65)
            result['structure'] = {'status': 'encrypted_bytes_only'}
            if identity:
                with tempfile.TemporaryDirectory(prefix='.decrypt.', dir=state_dir(c)) as directory:
                    output = Path(directory) / 'plaintext.unifi'
                    size, checksum = decrypt(path, identity, output, integer(c, 'RESTORE_MAX_BYTES', 10737418240, 1, 1099511627776))
                    expected = doc.get('encryption', {})
                    if size != expected.get('plaintext_size_bytes') or checksum != expected.get('plaintext_sha256'):
                        raise Failure('Decrypted bytes differ from original plaintext metadata')
                    result['decryption'] = 'valid'
                    result['structure'] = structure(output)
        else:
            result['structure'] = structure(path)
        result['success'] = True
    except (Failure, OSError, ValueError, TypeError) as exc:
        result['error'] = str(exc) if isinstance(exc, Failure) else 'Backup or metadata cannot be read safely'
        if identity and Path(path).name.endswith('.age') and not result['success']:
            result['decryption'] = 'failed_or_not_reached'
    return result


def record(c, results):
    history = state(c, 'verification.json', {'schema_version': 1, 'backups': {}, 'failures_total': 0})
    for item in results:
        history['backups'][item['filename']] = item
        history['failures_total'] += int(not item['success'])
    history['last_checked_at'] = iso()
    save_state(c, 'verification.json', history)
    metric(c, 'unifi_verification.prom', {
        'unifi_backup_verification_success': int(all(r['success'] for r in results)),
        'unifi_backup_last_verification_timestamp_seconds': now(),
        'unifi_backup_verification_failures_total': history['failures_total'],
    })

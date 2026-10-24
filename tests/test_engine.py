"""Offline engine tests use only synthetic data and standard-library mocks."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib' / 'ub'))
from core import Failure, atomic
from verify import verify
from storage import Store
from replication import replicate


class EngineCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.backups = self.root / 'backups'
        self.backups.mkdir(mode=0o700)
        self.c = {'BACKUP_DIR': str(self.backups), 'STATUS_FILE': str(self.root / 'status.json')}

    def tearDown(self):
        self.temp.cleanup()

    def backup(self, day='01', body=None):
        body = body or b'opaque-synthetic-unifi-fixture\0' * 1024
        p = self.backups / f'unifi_os_backup_2026-10-{day}_03-00-00.unifi'
        p.write_bytes(body)
        p.chmod(0o600)
        m = {'schema_version': 1, 'backup': {'id': 'id-' + day, 'filename': p.name,
             'size_bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest(),
             'source': 'https://controller.example.invalid', 'created_at': f'2026-10-{day}T03:00:00Z'}}
        atomic(str(p) + '.json', m)
        return p

    def test_verify_and_corruption(self):
        p = self.backup()
        r = verify(p, self.c)
        self.assertTrue(r['success'])
        self.assertEqual(r['structure']['status'], 'limited')
        self.assertFalse(r['restore_tested'])
        p.write_bytes(b'x' * p.stat().st_size)
        self.assertFalse(verify(p, self.c)['success'])

    def test_missing_metadata_error_and_html(self):
        p = self.backup(body=b'<html>error</html>')
        self.assertFalse(verify(p, self.c)['success'])
        Path(str(p) + '.json').unlink()
        self.assertFalse(verify(p, self.c)['metadata_valid'])

    def test_symlinks_and_traversal(self):
        p = self.backup()
        try:
            q = self.backups / 'link'
            q.symlink_to(p)
        except OSError:
            self.skipTest('OS does not allow symlink creation')
        self.assertFalse(verify(q, self.c)['success'])

    def filesystem(self, identifier='disk'):
        target = self.root / identifier
        target.mkdir(mode=0o700)
        (target / '.unifi-backup-target').write_text(identifier)
        return {'TARGET_TYPE': 'filesystem', 'TARGET_VERIFY': 'full', 'TARGET_REQUIRED': 'true',
                'FILESYSTEM_PATH': str(target), 'FILESYSTEM_REQUIRE_MOUNT': 'false'}

    def test_multi_destination_and_idempotence(self):
        p = self.backup()
        sections = {'main': self.c, 'disk': self.filesystem(), 'other': self.filesystem('other')}
        report = replicate(p, sections)
        self.assertTrue(report['policy_satisfied'])
        self.assertEqual(report['successful_remote_count'], 2)
        # Frozen remote sidecar records earlier state; it is never overwritten.
        # Replaying an unchanged payload upload itself remains idempotent.
        store = Store('disk', sections['disk'])
        self.assertEqual(store.upload(p), 'already_present')
        with self.assertRaises(Failure):
            store.download('../escape', self.root / 'escaped')
        self.assertEqual(len(store.listing()), 2)

    def test_independent_failure(self):
        p = self.backup()
        sections = {'main': self.c, 'broken': {'TARGET_TYPE': 'filesystem', 'FILESYSTEM_PATH': '/nonexistent'}, 'disk': self.filesystem()}
        report = replicate(p, sections)
        self.assertEqual(report['replication'], 'partial')
        self.assertEqual(report['local_backup'], 'success')
        self.assertTrue(report['policy_satisfied'])


if __name__ == '__main__':
    unittest.main()

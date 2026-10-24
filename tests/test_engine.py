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
from replication import remote_check
from retry_queue import retry, pins
from core import state, save_state
from retention import apply as retain
from policy import settings, confirmation
from unittest.mock import patch
from argparse import Namespace
from recovery import restore
from anomaly import evaluate
from config_diff import compare, extract


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

    def test_persistent_retry_pins_and_recovery(self):
        p = self.backup()
        config = self.filesystem()
        marker = Path(config['FILESYSTEM_PATH']) / '.unifi-backup-target'
        marker.unlink()
        sections = {'main': self.c, 'disk': config}
        self.assertFalse(replicate(p, sections)['policy_satisfied'])
        self.assertIn(p.name, pins(self.c))
        self.assertEqual(len(state(self.c, 'retry-queue.json')['tasks']), 1)
        marker.write_text('disk')
        result = retry(sections, force=True)
        self.assertTrue(result[0]['policy_satisfied'])
        self.assertNotIn(p.name, pins(self.c))
        remote = Path(config['FILESYSTEM_PATH']) / p.name
        remote.write_bytes(b'corrupt')
        with self.assertRaises(Failure):
            remote_check(Store('disk', config), p, self.c, True)

    def test_dead_letter_unpins_at_attempt_limit(self):
        self.c['RETRY_MAX_ATTEMPTS'] = '1'
        p = self.backup()
        replicate(p, {'main': self.c, 'broken': {'TARGET_TYPE': 'filesystem', 'FILESYSTEM_PATH': '/does-not-exist', 'TARGET_REQUIRED': 'true'}})
        self.assertFalse(pins(self.c))
        self.assertEqual(next(iter(state(self.c, 'retry-queue.json')['tasks'].values()))['status'], 'dead')

    def test_retention_pins_and_gfs(self):
        older = self.backup('01')
        latest = self.backup('02')
        self.c.update({'RETENTION_COUNT': '1', 'RETENTION_DAYS': '0', 'RETENTION_MIN_COUNT': '1'})
        os.utime(older, (1, 1))
        replicate(older, {'main': self.c, 'broken': {'TARGET_TYPE': 'filesystem', 'FILESYSTEM_PATH': '/absent'}})
        report = retain(self.c)
        self.assertTrue(older.exists())
        self.assertIn('pending_retry', next(x for x in report['decisions'] if x['filename'] == older.name)['keep_reasons'])
        self.c.update({'RETENTION_MODE': 'gfs', 'GFS_DAILY': '1', 'GFS_WEEKLY': '0', 'GFS_MONTHLY': '0', 'GFS_YEARLY': '0'})
        report = retain(self.c, dry_run=True)
        self.assertTrue(latest.exists())
        self.assertIn('gfs_daily', next(x for x in report['decisions'] if x['filename'] == latest.name)['keep_reasons'])

    def test_immutability_is_explicit_and_confirmed(self):
        config = {'TARGET_TYPE': 's3', 'S3_ENDPOINT': 'https://s3.example.invalid', 'S3_BUCKET': 'backups',
                  'S3_REGION': 'eu-west-1', 'S3_ACCESS_KEY_ID': 'test', 'S3_SECRET_ACCESS_KEY': 'test',
                  'TARGET_IMMUTABILITY': 'request', 'TARGET_LOCK_MODE': 'COMPLIANCE'}
        store = Store('s3', config)
        with self.assertRaises(Failure):
            settings(store)
        config['TARGET_ALLOW_PERMANENT_LOCK'] = 'true'
        with patch.object(store, 'head', return_value={'headers': {'x-amz-object-lock-mode': 'COMPLIANCE',
             'x-amz-object-lock-retain-until-date': '2099-01-01T00:00:00Z'}}):
            self.assertTrue(confirmation(store, self.backup().name)['confirmed'])
        with patch.object(store, 'head', return_value={'headers': {}}):
            self.assertFalse(confirmation(store, 'ignored')['confirmed'])

    def restore_args(self, **values):
        return Namespace(backup_id=None, date=None, list=False, latest=True, dry_run=False,
                         identity=None, verify_only=False, output=str(self.root / 'restore'), **values)

    def test_local_and_remote_restore(self):
        p = self.backup()
        report = restore(self.c, self.restore_args())
        self.assertEqual(Path(report['output_file']).read_bytes(), p.read_bytes())
        self.assertFalse(report['restore_tested'])
        with self.assertRaises(Failure):
            restore(self.c, self.restore_args())
        config = self.filesystem()
        replicate(p, {'main': self.c, 'disk': config})
        args = self.restore_args()
        args.output = str(self.root / 'remote-restore')
        report = restore(self.c, args, Store('disk', config))
        self.assertEqual(report['origin'], 'disk')
        self.assertEqual(Path(report['output_file']).read_bytes(), p.read_bytes())

    def test_restore_dry_run_and_corrupt_rejection(self):
        p = self.backup()
        args = self.restore_args()
        args.dry_run = True
        self.assertTrue(restore(self.c, args)['dry_run'])
        self.assertFalse(Path(args.output).exists())
        args.dry_run = False
        p.write_bytes(b'corrupt')
        with self.assertRaises(Failure):
            restore(self.c, args)
        self.assertFalse(Path(args.output).exists())

    def test_anomaly_baseline_and_cold_start(self):
        rows = [{'id': str(i), 'controller': 'same', 'size': 10000, 'hash': 'a', 'timings': {}} for i in range(10)]
        self.assertEqual(evaluate(rows, self.c)['status'], 'normal')
        self.assertEqual(evaluate(rows[:2], self.c)['status'], 'cold_start')
        rows[-1]['size'] = 1000
        self.assertEqual(evaluate(rows, self.c)['severity'], 'WARNING')
        rows[-1]['controller'] = 'different'
        self.assertEqual(evaluate(rows, self.c)['status'], 'cold_start')

    def test_configuration_diff_redacts_every_value(self):
        old = {'categories': {'wifi': [{'id': 'private-user', 'password': 'old-secret', 'ssid': 'internal-name'}], 'firewall': [{'id': 'one', 'enabled': True}]}}
        new = {'categories': {'wifi': [{'id': 'private-user', 'password': 'new-secret', 'ssid': 'internal-name'}, {'id': 'another', 'password': 'secret'}]}}
        report = compare(old, new)
        self.assertEqual(report['summary'], {'added': 1, 'removed': 1, 'modified': 1, 'unchanged': 0})
        rendered = json.dumps(report)
        for secret in ('private-user', 'old-secret', 'new-secret', 'internal-name'):
            self.assertNotIn(secret, rendered)
        p = self.backup()
        with self.assertRaisesRegex(Failure, 'Unsupported native UniFi'):
            extract(p, self.c)


if __name__ == '__main__':
    unittest.main()

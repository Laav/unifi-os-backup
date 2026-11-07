"""Configuration management security/regression tests; synthetic data only."""
from contextlib import redirect_stdout
import io
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib' / 'ub'))
from core import Failure
from config_files import Document, checked, fingerprint, quote, load_document
from config_model import Model, calendar, public_recipients, write_directory, read_access
from config_schema import SCOPES, defaults, reference, validate_operations
from config_transaction import HEADER, Transaction, lock, write
from config_ui import Dialog, Wizard, screen_text
import configure

ROOT = Path(__file__).resolve().parents[1]


class FakeUI:
    def __init__(self, actions=()):
        self.actions, self.messages = list(actions), []

    def take(self, method):
        actual, result = self.actions.pop(0)
        assert actual == method, (actual, method)
        return result

    def menu(self, *args, **kwargs):
        return self.take('menu')

    def input(self, *args, **kwargs):
        return self.take('input')

    def confirm(self, *args, **kwargs):
        return self.take('confirm')

    def message(self, title, message):
        self.messages.append((title, message))


class ConfigurationCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        self.config = self.root / 'unifi-backup.env'
        self.units = self.root / 'units'
        self.backups = self.root / 'backups'
        self.backups.mkdir(mode=0o700)
        self.target_dir = self.root / 'targets.d'
        self.target_dir.mkdir(mode=0o700)
        values = {'UNIFI_URL': 'https://controller.example.invalid:11443', 'UNIFI_PASSWORD': 'synthetic-quote"\n$`!\\password',
                  'UNIFI_USERNAME': 'test-only-service', 'BACKUP_DIR': str(self.backups), 'BACKUP_TARGET_CONFIG_DIR': str(self.target_dir),
                  'LOCK_FILE': str(self.backups / 'operation.lock'), 'STATUS_FILE': str(self.backups / 'status.json'),
                  'CATALOG_FILE': str(self.backups / 'catalog.json'), 'AGE_RECIPIENTS_FILE': str(self.root / 'recipients.txt'),
                  'RESTORE_STAGING_DIR': str(self.root / 'restore')}
        for name in ('graph', 'storage', 'ntfy', 'webhook'):
            key = {'graph': 'GRAPH', 'storage': 'STORAGE', 'ntfy': 'NTFY', 'webhook': 'WEBHOOK'}[name] + '_CONFIG_FILE'
            values[key] = str(self.root / (name + '.env'))
        self.config.write_bytes(Document('# Custom header\nUNKNOWN_CUSTOM=\'literal preserved\' # keep\n').render(values))
        self.config.chmod(0o600)
        # The real validator intentionally rejects PrivateTmp-hidden paths.
        # Transaction unit fixtures use private temporary roots rather than
        # touching production /var directories. Test that policy separately.
        self.path_policy = patch('config_model.write_directory', side_effect=lambda p: checked(p, directory=True))
        self.path_policy.start()
        self.read_policy = patch('config_model.read_access', side_effect=checked)
        self.read_policy.start()

    def tearDown(self):
        self.path_policy.stop()
        self.read_policy.stop()
        self.temp.cleanup()

    def model(self):
        return Model(self.config, self.units)

    def put(self, path, values):
        path.write_bytes(Document().render(values)); path.chmod(0o600)

    def test_literal_roundtrip_preserves_comments_unknown_and_multiline(self):
        samples = ['', "'", '"', 'a b', '\n\n', 'line1\nline2', '$USER $(touch /never) `id`', '\\', 'é:☃', '--trace', '#comment']
        for value in samples:
            with self.subTest(value_length=len(value)):
                doc = Document('export VALUE=' + quote(value) + ' # annotation\nOTHER="kept"\n')
                self.assertEqual(doc.values['VALUE'], value)
                new = doc.render({'VALUE': value + 'changed'})
                self.assertIn(b'# annotation', new)
                self.assertIn(b'OTHER="kept"', new)
                self.assertEqual(Document(new.decode()).values['VALUE'], value + 'changed')
        doc = Document("A=$'quote\\\' tab\\t newline\\n hex\\x41'\nB=escaped\\ space\n")
        self.assertEqual(doc.values['A'], "quote' tab\t newline\n hexA")
        self.assertEqual(doc.values['B'], 'escaped space')
        self.assertEqual(Document("A=$'\\303\\251'\n").values['A'], 'é')
        self.assertEqual(Document("A=$'\\u00e9'\n").values['A'], 'é')
        with self.assertRaises(Failure):
            Document("A=$'\\xff'\n")
        self.assertEqual(Document("A='first\r\nsecond'\n").values['A'], 'first\r\nsecond')
        for text in ("A='value'\r\n", 'A=prefix:~root\n'):
            with self.assertRaises(Failure):
                Document(text)

    def test_unsafe_shell_is_never_executed(self):
        for text in ['A=$(id)\n', 'A="$HOME"\n', 'source /anything\n', 'A=x; id\n', 'A=x && id\n', 'A=(one two)\n', 'A=`id`\n', 'A=~root\n', 'A=one B=two\n', "A=$'\\x00'\n"]:
            with self.subTest(syntax=text[:8]):
                with self.assertRaises(Failure):
                    Document(text)

    def test_literal_dollars_are_not_mistaken_for_expansions(self):
        for value in ('synthetic$', 'synthetic$%', 'synthetic$.', 'synthetic$:', "synthetic$'quoted'", 'synthetic$)', '$'):
            with self.subTest(length=len(value)):
                self.assertEqual(Document('VALUE="' + value + '"\n').values['VALUE'], value)
        for value in ('synthetic$', 'synthetic$%', 'synthetic$.', 'synthetic$:'):
            self.assertEqual(Document('VALUE=' + value + '\n').values['VALUE'], value)
        for value in ('$HOME', '${HOME}', '$?', '$$', '$1', '$-', '$@', '$[1+1]', '$(id)', '$\\\nHOME'):
            with self.assertRaises(Failure):
                Document('VALUE="' + value + '"\n')

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Bash semantics comparison runs on Linux')
    def test_literal_dollars_match_real_bash_without_rewriting(self):
        path = self.root / 'synthetic.env'
        for value in ('synthetic$', 'synthetic$%', 'synthetic$.', "synthetic$'quoted'", 'synthetic$)'):
            data = ('SYNTHETIC_VALUE="' + value + '"\n').encode()
            path.write_bytes(data); path.chmod(0o600)
            parsed = load_document(path)
            result = subprocess.run(['bash', '--noprofile', '--norc', '-c', 'set -eu; source "$1"; printf "%s" "$SYNTHETIC_VALUE"', 'test', str(path)],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(parsed.values['SYNTHETIC_VALUE'], result.stdout.decode())
            self.assertEqual(path.read_bytes(), data)

    def test_syntax_error_identifies_file_line_setting_not_secret(self):
        path = self.root / 'synthetic.env'
        path.write_bytes(b'# header\nUNIFI_PASSWORD="synthetic-hidden$MISSING"\n'); path.chmod(0o600)
        with self.assertRaises(Failure) as caught:
            load_document(path)
        message = str(caught.exception)
        self.assertIn('synthetic.env: line 2, setting UNIFI_PASSWORD', message)
        self.assertNotIn('synthetic-hidden', message)
        self.assertNotIn('MISSING', message)
        self.assertEqual(caught.exception.code, 65)

    def test_existing_defaults_and_disabled_integrations_are_not_written(self):
        model = self.model()
        self.assertEqual(model.main['RETENTION_DAYS'], '35')
        self.assertEqual(model.main['UNIFI_PASSWORD'], 'synthetic-quote"\n$`!\\password')
        self.assertNotIn('graph', [item['scope'] for item in model.plan()])
        with patch('config_model.shutil.which', return_value='available'):
            self.assertFalse([i for i in model.validate() if not i.warning])
        self.assertFalse((self.root / 'graph.env').exists())

    def test_fresh_generation_and_idempotent_apply_with_rollback(self):
        model = self.model()
        old = self.config.read_bytes()
        model.set('main', 'RETENTION_DAYS', '60')
        with patch('config_model.shutil.which', return_value='available'), patch('config_transaction.reload_units'):
            identifier = model.apply()
            self.assertRegex(identifier, r'^[a-f0-9]{32}$')
            self.assertIn(b'# Custom header', self.config.read_bytes())
            self.assertIn(b'UNKNOWN_CUSTOM=\'literal preserved\' # keep', self.config.read_bytes())
            reloaded = self.model()
            self.assertEqual(reloaded.main['RETENTION_DAYS'], '60')
            self.assertEqual(reloaded.plan(), [])
            self.assertIsNone(reloaded.apply())
            Transaction(self.config, self.units).rollback(identifier, confirmed=True)
        self.assertEqual(self.config.read_bytes(), old)

    def test_fresh_missing_main_does_not_create_anything_until_apply(self):
        paths = {k: v for k, v in Document(self.config.read_text()).values.items() if k in defaults('main') and ('FILE' in k or 'DIR' in k)}
        self.config.unlink()
        with patch('config_model.defaults', side_effect=lambda scope: {**defaults(scope), **paths} if scope == 'main' else defaults(scope)):
            model = self.model()
            self.assertFalse(self.config.exists())
            self.assertTrue(any(item['path'] == self.config for item in model.plan()))
        self.assertFalse(self.config.exists())
        self.assertFalse((self.root / '.configure.lock').exists())

    def test_fresh_valid_configuration_is_generated_and_reloads(self):
        paths = {k: v for k, v in Document(self.config.read_text()).values.items() if k in defaults('main') and ('FILE' in k or 'DIR' in k)}
        self.config.unlink()
        with patch('config_model.defaults', side_effect=lambda scope: {**defaults(scope), **paths} if scope == 'main' else defaults(scope)), patch('config_model.shutil.which', return_value='available'), patch('config_transaction.reload_units'):
            model = self.model()
            model.set('main', 'UNIFI_URL', 'https://synthetic.example.invalid:11443')
            model.set('main', 'UNIFI_PASSWORD', 'fresh-synthetic-secret')
            model.apply()
            reloaded = self.model()
            self.assertEqual(reloaded.main['UNIFI_PASSWORD'], 'fresh-synthetic-secret')
            self.assertEqual(reloaded.plan(), [])
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600 if os.name == 'posix' else 0o666)

    def test_guided_finish_applies_only_after_confirmation(self):
        model = self.model()
        model.set('main', 'RETENTION_DAYS', '46')
        ui = FakeUI([('menu', (0, 'next')), ('menu', (0, 'next')), ('menu', (0, 'keep')),
                     ('menu', (0, 'next')), ('menu', (0, 'next')), ('menu', (0, 'next')), ('menu', (0, 'next')),
                     ('confirm', True), ('confirm', False)])
        with patch('config_model.shutil.which', return_value='available'), patch('config_transaction.reload_units'):
            Wizard(model, ui).guided()
        self.assertEqual(self.model().main['RETENTION_DAYS'], '46')
        self.assertFalse(ui.actions)

    def test_legacy_storage_is_preserved_and_migration_is_explicit(self):
        self.put(self.root / 'storage.env', {'S3_ENDPOINT': 'https://s3.example.invalid', 'S3_BUCKET': 'backups', 'S3_REGION': 'eu-west-1',
                                           'S3_ACCESS_KEY_ID': 'test-id', 'S3_SECRET_ACCESS_KEY': 'test-secret'})
        model = self.model()
        model.set('main', 'REMOTE_STORAGE_TYPE', 's3')
        model.add_target('secondary', 'azure_blob')
        with self.assertRaises(Failure):
            model.activate('secondary')
        model.set('main', 'REMOTE_STORAGE_TYPE', 'none')
        model.activate('secondary')
        self.assertEqual(model.main['BACKUP_TARGETS'], 'secondary')
        model.set('main', 'REMOTE_STORAGE_TYPE', 's3')
        with self.assertRaises(Failure):
            model.activate('secondary', False)
        self.assertEqual(model.main['BACKUP_TARGETS'], 'secondary')

    def test_multiple_targets_disabled_targets_and_required_quorum(self):
        model = self.model()
        for name in ('a', 'b'):
            model.add_target(name, 'filesystem')
        self.assertEqual(model.main['BACKUP_TARGETS'], '')
        model.activate('a'); model.activate('b')
        model.set('main', 'BACKUP_REQUIRED_TARGETS', '2')
        validate_operations({'main': model.main, 'a': model.values['target:a'], 'b': model.values['target:b']})
        model.activate('b', False)
        with self.assertRaises(Failure):
            validate_operations({'main': model.main, 'a': model.values['target:a']})
        self.assertIn('target:b', model.values)
        self.assertTrue(any(not issue.warning for issue in model.validate_target('b')))

    def test_target_ids_reject_traversal_duplicates_and_reserved(self):
        model = self.model()
        for identifier in ('../escape', 'main', 'a b', '/root', 'x' * 65):
            with self.assertRaises(Failure):
                model.add_target(identifier, 's3')
        model.main['BACKUP_TARGETS'] = 'a a'
        with self.assertRaises(Failure):
            model.target_ids()

    def test_invalid_target_path_loads_for_safe_literal_repair(self):
        values = Document(self.config.read_text()).values
        values['BACKUP_TARGET_CONFIG_DIR'] = 'relative-not-allowed'
        self.put(self.config, values)
        model = self.model()
        self.assertIsNotNone(model.target_error)
        self.assertTrue(any(not i.warning for i in model.validate()))
        model.set('main', 'BACKUP_TARGET_CONFIG_DIR', str(self.target_dir))
        self.assertIsNone(model.target_error)

    def test_config_file_roles_cannot_alias_manager_or_engine_state(self):
        for path in (self.root / '.configure.lock', self.root / '.configure-pending',
                     self.root / '.configure-transactions' / 'graph.env', self.backups / 'operation.lock',
                     self.backups / 'status.json', self.backups / 'catalog.json', self.root / 'recipients.txt', self.config):
            with self.subTest(role_path=path.name):
                model = self.model()
                model.set('main', 'GRAPH_CONFIG_FILE', str(path))
                with patch('config_model.shutil.which', return_value='available'):
                    self.assertTrue(any(issue.category == 'security' and 'role' in issue.location for issue in model.validate()))
                with self.assertRaises(Failure):
                    model.plan()

    def test_target_directory_and_moved_key_resources_remain_protected(self):
        model = self.model()
        model.set('main', 'BACKUP_TARGET_CONFIG_DIR', str(self.root / '.configure-transactions'))
        self.assertTrue(model.role_issues())
        with self.assertRaises(Failure):
            model.plan()
        model = self.model()
        model.set('main', 'AGE_RECIPIENTS_FILE', str(self.root / 'new-recipients.txt'))
        model.set('main', 'GRAPH_CONFIG_FILE', str(self.root / 'recipients.txt'))
        self.assertTrue(model.role_issues())
        with self.assertRaises(Failure):
            model.plan()

    def test_redacted_review_and_export_never_include_secrets(self):
        model = self.model()
        model.set('main', 'UNIFI_PASSWORD', 'new-sensitive-only')
        rendered = json.dumps(model.summary())
        for value in ('new-sensitive-only', 'synthetic-quote', 'test-only-service'):
            self.assertNotIn(value, rendered)
        self.assertIn('[set; hidden]', rendered)
        self.assertNotIn('literal preserved', rendered)

    def test_invalid_values_and_dependencies(self):
        model = self.model()
        for key, value in [('RETENTION_DAYS', '-1'), ('ENABLE_EMAIL', 'yes'), ('CURL_MAX_TIME', '0'), ('RETENTION_MODE', 'other')]:
            with self.assertRaises(Failure):
                model.set('main', key, value)
        model.set('main', 'UNIFI_URL', 'https://user:password@example.invalid')
        model.set('main', 'RETENTION_MODE', 'gfs')
        model.set('main', 'ENABLE_EMAIL', 'true')
        with patch('config_model.shutil.which', return_value=None):
            issues = model.validate()
        self.assertTrue(any(i.category == 'dependency' for i in issues))
        self.assertTrue(any(i.location == 'graph.CLIENT_SECRET' for i in issues))
        self.assertNotIn('password@example.invalid', json.dumps([i.message for i in issues]))

    def test_permissions_and_symlinks_fail_closed(self):
        if os.name == 'nt':
            self.skipTest('POSIX ownership and symlink enforcement runs in Linux CI')
        self.config.chmod(0o644)
        with self.assertRaises(Failure):
            self.model()
        self.config.chmod(0o600)
        target = self.root / 'link.env'; target.symlink_to(self.config)
        with self.assertRaises(Failure):
            Model(target, self.units)
        self.root.chmod(0o755)
        with self.assertRaises(Failure):
            self.model()
        self.root.chmod(0o700)

    def test_unsupported_inactive_file_is_preserved_and_cannot_be_edited(self):
        path = self.root / 'graph.env'
        path.write_text('CLIENT_SECRET=$(command-must-never-run)\n'); path.chmod(0o600)
        model = self.model()
        with self.assertRaises(Failure):
            model.set('graph', 'CLIENT_SECRET', 'replacement')
        self.assertNotIn('graph', [item['scope'] for item in model.plan()])
        model.set('main', 'ENABLE_EMAIL', 'true')
        self.assertTrue(any(i.category == 'syntax' for i in model.validate(filesystem=False)))

    def test_failed_second_write_rolls_back_every_file(self):
        first, second = self.root / 'one.env', self.root / 'two.env'
        self.put(first, {'A': 'old1'}); self.put(second, {'B': 'old2'})
        before = [first.read_bytes(), second.read_bytes()]
        plan = [{'path': p, 'mode': 0o600, 'before': fingerprint(p), 'data': Document().render({'NEW': 'changed'})} for p in (first, second)]
        from config_transaction import write as original
        failed = False
        def failing(path, data, mode):
            nonlocal failed
            if Path(path) == second and not failed:
                failed = True
                raise OSError('synthetic write failure')
            return original(path, data, mode)
        with patch('config_transaction.write', side_effect=failing):
            with self.assertRaises(Failure) as caught:
                Transaction(self.config, self.units).apply(plan, [str(self.backups / 'operation.lock')])
        self.assertEqual(caught.exception.code, 73)
        self.assertEqual([first.read_bytes(), second.read_bytes()], before)
        self.assertFalse((self.root / '.configure-pending').exists())

    def test_pending_transaction_blocks_apply_and_can_recover(self):
        first = self.root / 'one.env'
        self.put(first, {'A': 'original'})
        plan = [{'path': first, 'mode': 0o600, 'before': fingerprint(first), 'data': Document().render({'A': 'changed'})}]
        txn = Transaction(self.config, self.units)
        with patch('config_transaction.remove', side_effect=OSError('simulated persistent storage failure')):
            with self.assertRaises(Failure) as caught:
                txn.apply(plan, [str(self.backups / 'operation.lock')])
        self.assertEqual(caught.exception.code, 75)
        identifier = txn.pending_id()
        self.assertIsNotNone(identifier)
        txn.rollback(confirmed=True)
        self.assertEqual(Document(first.read_text()).values['A'], 'original')
        self.assertIsNone(txn.pending_id())

    def test_concurrent_attempts_and_changed_files_are_rejected(self):
        model = self.model()
        model.set('main', 'RETENTION_DAYS', '60')
        with lock(self.root / '.configure.lock'):
            with self.assertRaises(Failure) as caught:
                model.transaction.apply(model.plan(), [str(self.backups / 'operation.lock')])
        self.assertEqual(caught.exception.code, 75)
        self.config.write_bytes(self.config.read_bytes() + b'# external edit\n')
        with self.assertRaises(Failure) as caught:
            model.transaction.apply(model.plan(), [str(self.backups / 'operation.lock')])
        self.assertEqual(caught.exception.code, 75)

    def test_rollback_refuses_later_edits(self):
        first = self.root / 'one.env'
        self.put(first, {'A': 'original'})
        txn = Transaction(self.config, self.units)
        identifier = txn.apply([{'path': first, 'mode': 0o600, 'before': fingerprint(first), 'data': Document().render({'A': 'changed'})}], [])
        self.put(first, {'A': 'later operator change'})
        with self.assertRaises(Failure):
            txn.rollback(identifier, confirmed=True)
        self.assertEqual(Document(first.read_text()).values['A'], 'later operator change')

    def test_corrupt_rollback_preimage_fails_without_overwriting_current_file(self):
        first = self.root / 'one.env'; self.put(first, {'A': 'original'})
        txn = Transaction(self.config, self.units)
        identifier = txn.apply([{'path': first, 'mode': 0o600, 'before': fingerprint(first), 'data': b"A='changed'\n"}], [])
        (txn.history / identifier / '0.before').write_bytes(b'corrupt synthetic preimage')
        with self.assertRaises(Failure) as caught:
            txn.rollback(identifier, confirmed=True)
        self.assertEqual(caught.exception.code, 66)
        self.assertEqual(Document(first.read_text()).values['A'], 'changed')
        self.assertEqual(txn.pending_id(), identifier)

    def test_unchanged_dependency_edits_block_apply(self):
        self.put(self.root / 'graph.env', {'CLIENT_SECRET': 'old-synthetic-secret'})
        model = self.model()
        model.set('main', 'RETENTION_DAYS', '45')
        self.put(self.root / 'graph.env', {'CLIENT_SECRET': 'new-synthetic-secret'})
        with patch('config_model.shutil.which', return_value='available'), patch('config_transaction.reload_units'):
            with self.assertRaises(Failure) as caught:
                model.apply()
        self.assertEqual(caught.exception.code, 75)
        self.assertEqual(self.model().main['RETENTION_DAYS'], '35')

    def test_interruption_rolls_back_and_preserves_signal_exception(self):
        first = self.root / 'one.env'; self.put(first, {'A': 'original'})
        original = first.read_bytes()
        from config_transaction import write as normal
        interrupted = False
        def stop(path, data, mode):
            nonlocal interrupted
            if Path(path) == first and not interrupted:
                interrupted = True
                normal(path, data, mode)
                raise KeyboardInterrupt
            return normal(path, data, mode)
        with patch('config_transaction.write', side_effect=stop):
            with self.assertRaises(KeyboardInterrupt):
                Transaction(self.config, self.units).apply([{'path': first, 'mode': 0o600, 'before': fingerprint(first), 'data': b"A='changed'\n"}], [])
        self.assertEqual(first.read_bytes(), original)
        self.assertFalse((self.root / '.configure-pending').exists())

    def test_owned_dropin_retracts_old_extra_write_paths(self):
        model = self.model()
        target = self.units / 'unifi-backup.service.d/90-unifi-backup-configure.conf'
        target.parent.mkdir(parents=True)
        target.write_text(HEADER + '[Service]\nReadWritePaths=/old/destination\n')
        data = model.systemd_files()[target]
        self.assertNotIn('/old/destination', data)
        self.assertNotIn('ReadWritePaths=\n', data)

    def test_existing_managed_calendar_is_loaded_for_editing(self):
        model = self.model()
        path = self.units / 'unifi-backup.timer.d/90-unifi-backup-configure.conf'
        path.parent.mkdir(parents=True)
        path.write_bytes((HEADER + '[Timer]\nOnCalendar=\nOnCalendar=Tue *-*-* 05:15:00\n').encode())
        with patch('config_model.shutil.which', return_value=None):
            self.assertEqual(model.current_schedule(), 'Tue *-*-* 05:15:00')

    def test_invalid_ca_and_extreme_numbers_fail_without_secret_output(self):
        path = self.root / 'ca.txt'; path.write_text('invalid synthetic CA contents')
        model = self.model()
        model.set('main', 'UNIFI_CA_CERT', str(path))
        with patch('config_model.shutil.which', return_value='available'):
            issues = model.validate()
        self.assertTrue(any(i.location == 'main.UNIFI_CA_CERT' for i in issues))
        self.assertNotIn('invalid synthetic CA contents', str(issues))
        with self.assertRaises(Failure):
            model.set('main', 'RETENTION_DAYS', '9' * 10000)

    @unittest.skipUnless(sys.platform.startswith('linux') and shutil.which('systemd-analyze'), 'Real unit/drop-in verification needs Linux systemd tools')
    def test_generated_units_and_dropins_pass_systemd_analyze(self):
        model = self.model()
        model.schedule = 'Tue *-*-* 05:15:00'
        self.units.mkdir(mode=0o755)
        # Offline structural test only: /bin/true avoids requiring installed
        # backup commands here. CI separately verifies real installed units.
        import re
        for path in (ROOT / 'systemd').iterdir():
            text = re.sub(r'/usr/local/sbin/unifi-backup[^\s]*', '/bin/true', path.read_text())
            (self.units / path.name).write_text(text)
        for path, text in model.systemd_files().items():
            path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            path.write_text(re.sub(r'/usr/local/sbin/unifi-backup[^\s]*', '/bin/true', text))
        env = {**os.environ, 'SYSTEMD_UNIT_PATH': str(self.units) + ':/usr/lib/systemd/system:/lib/systemd/system'}
        result = subprocess.run(['systemd-analyze', 'verify', *map(str, self.units.glob('*.service')), *map(str, self.units.glob('*.timer'))],
                                env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        calendar(model.schedule)
        with self.assertRaises(Failure):
            calendar('not a valid calendar')

    def test_systemd_dropins_preserve_packaged_security_and_refuse_foreign_files(self):
        model = self.model()
        model.schedule = 'Mon *-*-* 04:30:00'
        with patch('config_model.shutil.which', return_value='systemd-analyze'), patch('config_model.subprocess.run') as run:
            run.return_value.returncode = 0
            calendar(model.schedule)
        plan = model.plan()
        timer = next(item for item in plan if item['path'].parent.name == 'unifi-backup.timer.d')
        self.assertIn(b'OnCalendar=\nOnCalendar=Mon', timer['data'])
        service = next(item for item in plan if item['path'].parent.name == 'unifi-backup.service.d')
        self.assertIn(b'ReadWritePaths=', service['data'])
        self.assertNotIn(b'ProtectSystem=', service['data'])
        self.assertNotIn(b'ProtectHome=', service['data'])
        service['path'].parent.mkdir(parents=True)
        service['path'].write_text('# Administrator-owned file\n')
        with self.assertRaises(Failure):
            model.plan()

    def test_public_identity_rejection_and_age_dependency(self):
        for content in (b'AGE-SECRET-KEY-' + b'TEST-ONLY', b'not-a-public-recipient', b''):
            with self.assertRaises(Failure):
                public_recipients(content, check_age=False)
        with patch('config_model.shutil.which', return_value=None):
            with self.assertRaises(Failure) as caught:
                public_recipients(b'age1' + b'q' * 58 + b'\n')
        self.assertEqual(caught.exception.code, 69)

    def test_no_tty_missing_dialog_small_terminal(self):
        with patch('config_ui.sys.stdin.isatty', return_value=False):
            with self.assertRaises(Failure):
                Dialog()
        with patch('config_ui.sys.stdin.isatty', return_value=True), patch('config_ui.sys.stdout.isatty', return_value=True), patch.dict(os.environ, {'TERM': 'xterm'}), patch('config_ui.shutil.which', return_value=None):
            with self.assertRaises(Failure) as caught:
                Dialog()
            self.assertEqual(caught.exception.code, 69)
        with patch('config_ui.sys.stdin.isatty', return_value=True), patch('config_ui.sys.stdout.isatty', return_value=True), patch.dict(os.environ, {'TERM': 'xterm'}), patch('config_ui.shutil.which', return_value='dialog'), patch('config_ui.shutil.get_terminal_size', return_value=(40, 10)):
            with self.assertRaises(Failure):
                Dialog().input('title', 'prompt')
        self.assertEqual(screen_text('safe\x1b[bad'), 'safe?[bad')

    def test_mocked_navigation_masked_change_back_cancel_and_exit(self):
        model = self.model()
        prior = self.config.read_bytes()
        ui = FakeUI([('menu', (0, 'UNIFI_PASSWORD')), ('menu', (0, 'replace')), ('input', (0, 'changed-secret')),
                     ('menu', (3, '')), ('menu', (255, '')), ('confirm', True)])
        wizard = Wizard(model, ui)
        self.assertEqual(wizard.section('main', {'connection'}), 'back')
        self.assertEqual(model.main['UNIFI_PASSWORD'], 'changed-secret')
        wizard.run()
        self.assertEqual(self.config.read_bytes(), prior)
        self.assertFalse((self.root / '.configure-pending').exists())
        self.assertFalse(ui.actions)

    def test_guided_back_and_cancel_never_apply(self):
        model = self.model(); wizard = Wizard(model, FakeUI())
        with patch.object(wizard, 'section', side_effect=['next', 'back', 'next', 'cancel']) as section:
            wizard.guided()
        self.assertEqual(section.call_count, 4)
        self.assertFalse((self.root / '.configure.lock').exists())

    def test_noninteractive_inspection_is_redacted_and_nonmutating(self):
        with patch('configure.Model', side_effect=lambda config: Model(config, self.units)), patch('config_model.shutil.which', return_value='available'), redirect_stdout(io.StringIO()) as output:
            result = configure.main(['--config', str(self.config), '--inspect', '--json'])
        self.assertEqual(result, 0)
        report = json.loads(output.getvalue())
        self.assertFalse(report['configuration_modified'])
        self.assertFalse(report['live_tests_run'])
        self.assertNotIn('synthetic-quote', output.getvalue())
        self.assertFalse((self.root / '.configure.lock').exists())

    @unittest.skipUnless(os.name == 'posix', 'POSIX protected-path policy')
    def test_systemd_hidden_and_broad_paths_are_refused(self):
        for path in ('/tmp/unifi', '/var/tmp/unifi', '/home/operator/backups', '/etc', '/var', '/var/backups', '/root/backups'):
            with self.assertRaises(Failure):
                write_directory(path)
        for path in ('/tmp/config.env', '/home/operator/ca', '/root/identity'):
            with self.assertRaises(Failure):
                read_access(path)

    def test_schema_covers_every_existing_template_assignment(self):
        for scope, filename in [('main', 'unifi-backup'), ('target', 'target'), ('storage', 'storage'), ('graph', 'graph'), ('ntfy', 'ntfy'), ('webhook', 'webhook')]:
            template = Document((ROOT / 'config' / (filename + '.env.example')).read_text())
            self.assertEqual(set(template.values), set(defaults(scope)) if scope != 'target' else set(template.values) & set(defaults(scope)))
        self.assertEqual(len({s.name for s in SCOPES['main']}), len(SCOPES['main']))
        self.assertIn('| UNIFI_PASSWORD |', reference())

    def test_generated_reference_matches_central_metadata(self):
        self.assertEqual((ROOT / 'docs/CONFIGURATION-REFERENCE.md').read_text(), reference())

    def test_inherited_target_read_limit_is_not_materialized_without_editing(self):
        model = self.model()
        model.set('main', 'RESTORE_MAX_BYTES', '500000')
        model.add_target('secondary', 's3')
        self.assertEqual(model.values['target:secondary']['RESTORE_MAX_BYTES'], '500000')
        data = next(item for item in model.plan() if item['scope'] == 'target:secondary')['data']
        self.assertNotIn(b'RESTORE_MAX_BYTES', data)
        self.assertEqual(model.values['target:secondary']['TARGET_LOCK_MODE'], 'GOVERNANCE')

    def test_omitted_provider_lock_mode_keeps_runtime_default(self):
        self.put(self.target_dir / 'source.env', {'TARGET_TYPE': 's3', 'TARGET_IMMUTABILITY': 'check'})
        model = self.model()
        self.assertEqual(model.values['target:source']['TARGET_LOCK_MODE'], 'GOVERNANCE')
        self.assertFalse(any(item['scope'] == 'target:source' for item in model.plan()))

    def test_installer_updater_and_uninstaller_deploy_manager_without_auto_migration(self):
        install = (ROOT / 'install.sh').read_text()
        update = (ROOT / 'update.sh').read_text()
        uninstall = (ROOT / 'uninstall.sh').read_text()
        for text in (install, update, uninstall):
            self.assertIn('config_schema config_files config_model config_transaction config_ui configure', text)
            self.assertIn('restore analyze diff configure;', text)
        self.assertIn('--configure)', install)
        self.assertIn('if [[ $CONFIGURE == true ]]', install)
        self.assertNotIn('unifi-backup-configure --guided', update)
        self.assertIn('if [[ ! -e $destination ]]', update)


if __name__ == '__main__':
    unittest.main()

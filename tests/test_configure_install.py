"""Exercise the real lifecycle scripts in a rewritten private filesystem tree.

Only fixed installation prefixes in fixture copies are rewritten. No chroot,
network, live unit, production file or production configuration is touched.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(sys.platform.startswith('linux') and os.geteuid() == 0, 'Lifecycle filesystem integration test requires the root Linux CI container')
class LifecycleCase(unittest.TestCase):
    def test_install_update_remove_and_purge_preserve_contract(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            checkout = root / 'checkout'
            staged = root / 'installation'
            staged.mkdir(mode=0o700)
            shutil.copytree(source, checkout, ignore=shutil.ignore_patterns('.git', '__pycache__', 'test-results'))
            for script in ('install.sh', 'update.sh', 'uninstall.sh'):
                path = checkout / script
                text = path.read_text()
                for prefix in ('/etc/unifi-backup', '/etc/systemd/system', '/usr/local', '/var/backups/unifi', '/var/lib/unifi-backup', '/opt/unifi-os-backup'):
                    text = text.replace(prefix, str(staged) + prefix)
                path.write_text(text)
            commands = root / 'commands'; commands.mkdir()
            systemctl = commands / 'systemctl'
            systemctl.write_text('#!/usr/bin/env bash\nexit 0\n'); systemctl.chmod(0o755)
            env = {**os.environ, 'PATH': str(commands) + os.pathsep + os.environ['PATH']}
            def run(script, *args):
                result = subprocess.run(['bash', str(checkout / script), *args], cwd=checkout, env=env,
                                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, check=False)
                self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            run('install.sh', '--no-enable')
            config = staged / 'etc/unifi-backup/unifi-backup.env'
            self.assertTrue((staged / 'usr/local/sbin/unifi-backup-configure').is_file())
            self.assertTrue((staged / 'usr/local/lib/unifi-backup/ub/config_schema.py').is_file())
            self.assertEqual(config.stat().st_mode & 0o777, 0o600)
            self.assertEqual(config.parent.stat().st_mode & 0o777, 0o700)
            original = config.read_bytes() + b"# custom comment\nUNKNOWN_CUSTOM='preserved'\n"
            config.write_bytes(original)
            backup = staged / 'var/backups/unifi/synthetic.unifi'; backup.write_bytes(b'synthetic test data')
            run('install.sh', '--no-enable')
            self.assertEqual(config.read_bytes(), original)
            run('update.sh')
            self.assertEqual(config.read_bytes(), original)
            self.assertTrue(backup.exists())
            self.assertTrue((config.parent / '.configure.lock').exists())
            run('uninstall.sh')
            self.assertEqual(config.read_bytes(), original)
            self.assertTrue(backup.exists())
            self.assertFalse((staged / 'usr/local/sbin/unifi-backup-configure').exists())
            run('install.sh', '--no-enable')
            custom = staged / 'custom-backups'; custom.mkdir(); (custom / 'kept').write_text('synthetic')
            run('uninstall.sh', '--purge')
            self.assertFalse(config.parent.exists())
            self.assertFalse(backup.exists())
            self.assertTrue((custom / 'kept').exists())

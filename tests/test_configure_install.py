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
            # Every package-manager call is intercepted, including unexpected
            # calls: this test must never provision the CI host itself.
            apt = commands / 'apt-get'
            apt.write_text('#!/usr/bin/env bash\necho "Unexpected real APT invocation" >&2\nexit 99\n'); apt.chmod(0o755)
            env = {**os.environ, 'PATH': str(commands) + os.pathsep + os.environ['PATH']}
            def run(script, *args, code=0):
                result = subprocess.run(['bash', str(checkout / script), *args], cwd=checkout, env=env,
                                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, check=False)
                self.assertEqual(result.returncode, code, result.stderr.decode(errors='replace'))
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
            provisioned = root / 'dialog-installed'
            apt_log = root / 'apt-calls'
            shell_mock = root / 'dependency-mock.bash'
            shell_mock.write_text('''command() {
  if [[ $1 == -v && $2 == dialog && ! -e "$UB_TEST_MARKER" ]]; then return 1; fi
  builtin command "$@"
}
apt-get() {
  printf '%s\\n' "$*" >> "$UB_TEST_LOG"
  if [[ -n $UB_TEST_FAIL && " $* " == *" $UB_TEST_FAIL "* ]]; then return 100; fi
  if [[ " $* " == *" install "* ]]; then touch "$UB_TEST_MARKER"; fi
}
''')
            deployed = staged / 'usr/local/sbin/unifi-backup-configure'
            sentinel = deployed.read_bytes() + b'\n# synthetic deployment sentinel\n'
            deployed.write_bytes(sentinel)
            env.update(BASH_ENV=str(shell_mock), UB_TEST_MARKER=str(provisioned), UB_TEST_LOG=str(apt_log), UB_TEST_FAIL='update')
            run('update.sh', code=69)
            self.assertEqual(config.read_bytes(), original)
            self.assertEqual(deployed.read_bytes(), sentinel)
            self.assertFalse(provisioned.exists())
            apt_log.unlink()
            env['UB_TEST_FAIL'] = ''
            run('update.sh')
            self.assertTrue(provisioned.exists())
            self.assertEqual(len(apt_log.read_text().splitlines()), 2)
            self.assertTrue(apt_log.read_text().splitlines()[1].endswith(' install dialog'))
            self.assertNotEqual(deployed.read_bytes(), sentinel)
            env.pop('BASH_ENV')
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

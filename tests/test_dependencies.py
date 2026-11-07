"""Provisioner regression tests: APT is always mocked, never executed."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(sys.platform.startswith('linux') and os.geteuid() == 0,
                     'Dependency provisioning requires the root Linux CI container')
class DependenciesCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.log = self.root / 'apt.log'
        self.marker = self.root / 'installed'
        mock = self.root / 'mock.bash'
        mock.write_text('''command() {
  if [[ $1 == -v && $2 == "$UB_TEST_MISSING" && ! -e "$UB_TEST_INSTALLED" ]]; then return 1; fi
  builtin command "$@"
}
apt-get() {
  printf '%s\\n' "$*" >> "$UB_TEST_APT_LOG"
  if [[ " $* " == *" $UB_TEST_FAIL "* && -n $UB_TEST_FAIL ]]; then return 100; fi
  if [[ " $* " == *" install "* ]]; then touch "$UB_TEST_INSTALLED"; fi
}
''')
        self.env = {**os.environ, 'BASH_ENV': str(mock), 'UB_TEST_MISSING': 'dialog',
                    'UB_TEST_INSTALLED': str(self.marker), 'UB_TEST_APT_LOG': str(self.log),
                    'UB_TEST_FAIL': ''}
        self.installer = Path(__file__).resolve().parents[1] / 'install.sh'

    def run_installer(self, *options, code=0):
        result = subprocess.run(['bash', str(self.installer), *options], env=self.env,
                                stdin=subprocess.DEVNULL, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, code, result.stderr.decode(errors='replace'))
        return result

    def test_missing_dialog_is_provisioned_once_with_safe_apt_options(self):
        self.run_installer('--dependencies-only')
        lines = self.log.read_text().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].endswith(' update'))
        self.assertTrue(lines[1].endswith(' install dialog'))
        for option in ('--no-remove', '--no-upgrade', '--no-install-recommends', '--assume-yes'):
            self.assertIn(option, lines[1])
        self.run_installer('--dependencies-only')
        self.assertEqual(self.log.read_text().splitlines(), lines)

    def test_opt_out_permits_missing_optional_but_rejects_missing_core(self):
        result = self.run_installer('--dependencies-only', '--no-install-deps')
        self.assertIn(b'Automatic provisioning disabled', result.stdout)
        self.env['UB_TEST_MISSING'] = 'curl'
        self.run_installer('--dependencies-only', '--no-install-deps', code=69)
        self.assertFalse(self.log.exists())

    def test_bootstrap_git_and_optional_age_are_provisioned(self):
        for executable in ('git', 'age'):
            with self.subTest(executable=executable):
                self.env['UB_TEST_MISSING'] = executable
                self.run_installer('--dependencies-only')
                self.assertTrue(self.log.read_text().splitlines()[1].endswith(' install ' + executable))
                self.marker.unlink()
                self.log.unlink()

    def test_apt_failures_abort_before_deployment(self):
        for stage in ('update', 'install'):
            with self.subTest(stage=stage):
                self.env['UB_TEST_FAIL'] = stage
                result = self.run_installer('--dependencies-only', code=69)
                self.assertIn(b'application files and configuration were not changed', result.stderr)
                self.assertFalse(self.marker.exists())
                self.log.unlink()

    def test_help_and_non_tty_configure_do_not_provision(self):
        self.run_installer('--help')
        self.run_installer('--configure', code=69)
        self.run_installer('--unknown', code=64)
        self.assertFalse(self.log.exists())

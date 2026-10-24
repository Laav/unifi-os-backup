"""Guard the public source tree against accidental operational artifacts."""
from pathlib import Path
import re
import subprocess
import unittest


class PublicationCase(unittest.TestCase):
    def test_no_operational_artifacts_or_obvious_live_credentials(self):
        root = Path(__file__).resolve().parents[1]
        files = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard'], cwd=root, text=True).splitlines()
        forbidden = re.compile(r'(?:\.unifi(?:\.age)?|\.eml|\.env|\.pem|\.key|\.pfx|\.p12)$', re.I)
        credential = re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{36,}|AKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')
        for relative in set(files):
            with self.subTest(file=relative):
                self.assertFalse(forbidden.search(relative), 'Operational artifact must never be tracked')
                path = root / relative
                if path.is_file() and path.stat().st_size < 2 * 1024 * 1024:
                    self.assertIsNone(credential.search(path.read_text(encoding='utf-8', errors='replace')), 'Potential live credential/private key')


if __name__ == '__main__':
    unittest.main()

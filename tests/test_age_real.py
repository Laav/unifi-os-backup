"""Run actual recipient encryption/decryption; no private fixture is committed."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import unittest

import test_engine as fixtures
from core import atomic
from verify import verify
from recovery import restore


@unittest.skipUnless(shutil.which('age') and shutil.which('age-keygen'), 'Real age binaries are not installed')
class AgeCase(unittest.TestCase):
    setUp = fixtures.EngineCase.setUp
    tearDown = fixtures.EngineCase.tearDown
    backup = fixtures.EngineCase.backup
    restore_args = fixtures.EngineCase.restore_args
    def test_real_decryption_and_wrong_identity(self):
        original = self.backup()
        key, wrong = self.root / 'identity.txt', self.root / 'wrong.txt'
        for path in (key, wrong):
            subprocess.run(['age-keygen', '-o', str(path)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            path.chmod(0o600)
        recipients = subprocess.check_output(['age-keygen', '-y', str(key)]).decode().strip()
        encrypted = Path(str(original) + '.age')
        subprocess.run(['age', '--encrypt', '-r', recipients, '-o', str(encrypted), str(original)], check=True)
        encrypted.chmod(0o600)
        doc = json.loads(Path(str(original) + '.json').read_text())
        doc['encryption'] = {'enabled': True, 'type': 'age', 'original_filename': original.name,
                             'plaintext_sha256': doc['backup']['sha256'], 'plaintext_size_bytes': original.stat().st_size}
        doc['backup'].update({'filename': encrypted.name, 'size_bytes': encrypted.stat().st_size, 'sha256': hashlib.sha256(encrypted.read_bytes()).hexdigest()})
        atomic(str(encrypted) + '.json', doc)
        self.assertTrue(verify(encrypted, self.c)['success'])
        checked = verify(encrypted, self.c, key)
        self.assertTrue(checked['success'])
        self.assertEqual(checked['decryption'], 'valid')
        self.assertFalse(verify(encrypted, self.c, wrong)['success'])
        args = self.restore_args()
        args.identity = str(key)
        report = restore(self.c, args)
        self.assertEqual(Path(report['output_file']).read_bytes(), original.read_bytes())
        self.assertFalse(list(self.root.glob('.decrypt.*')))
        self.assertFalse(list(self.root.glob('.recovery.*')))


if __name__ == '__main__':
    unittest.main()

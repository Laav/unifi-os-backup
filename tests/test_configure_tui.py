"""Real dialog smoke tests on a Linux pseudo-terminal; never uses live secrets."""
import os
from pathlib import Path
import select
import shutil
import subprocess
import sys
import time
import unittest


@unittest.skipUnless(sys.platform.startswith('linux') and shutil.which('dialog'), 'Real dialog PTY tests require Linux and the optional dialog package')
class DialogCase(unittest.TestCase):
    def run_dialog(self, script, typed, expected_prompt=b'Synthetic prompt'):
        import fcntl
        import pty
        import struct
        import termios
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 28, 100, 0, 0))
        def terminal():
            os.setsid()
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)
        env = {**os.environ, 'TERM': 'xterm', 'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'lib' / 'ub')}
        process = subprocess.Popen([sys.executable, '-c', script], stdin=slave, stdout=slave, stderr=slave,
                                   env=env, preexec_fn=terminal, close_fds=True)
        os.close(slave)
        output, sent = b'', False
        deadline = time.monotonic() + 15
        try:
            while time.monotonic() < deadline:
                if select.select([master], [], [], 0.1)[0]:
                    try:
                        block = os.read(master, 65536)
                    except OSError:
                        break
                    if not block:
                        break
                    output += block
                    if not sent and expected_prompt in output:
                        os.write(master, typed)
                        sent = True
                if process.poll() is not None:
                    break
            if process.poll() is None:
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    self.fail('dialog did not finish within the PTY deadline')
            self.assertTrue(sent, 'dialog prompt was not rendered')
            self.assertEqual(process.returncode, 0, output[-1500:].decode(errors='replace'))
            return output
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            os.close(master)

    def test_passwordbox_masks_typed_value(self):
        secret = b'synthetic-masked-value'
        script = "from config_ui import Dialog; c,v=Dialog().input('Synthetic test','Synthetic prompt',secret=True); assert c==0 and len(v)==22"
        output = self.run_dialog(script, secret + b'\n')
        self.assertNotIn(secret, output)
        self.assertNotIn(secret.decode(), script)

    def test_option_like_initial_value_cannot_inject_dialog_options(self):
        script = "from config_ui import Dialog; c,v=Dialog().input('Synthetic test','Synthetic prompt','--trace'); assert c==0 and v=='--trace'"
        self.run_dialog(script, b'\n')

    def test_escape_cancels_without_a_value(self):
        script = "from config_ui import Dialog; c,v=Dialog().input('Synthetic test','Synthetic prompt',secret=True); assert c==255 and not v"
        self.run_dialog(script, b'\x1b')

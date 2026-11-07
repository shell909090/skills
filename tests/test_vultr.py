"""Isolated rotation tests: never touch user credentials or contact Vultr."""
import importlib.util
import json
import multiprocessing
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('vultr', Path(__file__).resolve().parents[1] / 'vultr/scripts/vultr.py')
v = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v)


def fake_gpg(arguments, data=None):
    return data if '--encrypt' in arguments else Path(arguments[-1]).read_bytes()


class RotationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='vultr-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = self.root / 'actual.gpg'
        self.link = self.root / 'entry.gpg'
        self.link.symlink_to(self.target)
        self.target.write_text(json.dumps({'refresh_token': 'old', 'gpg_recipient': 'test', 'expires_at': 0}))
        self.patches = [patch.object(v, 'TOKEN_FILE', self.link), patch.object(v, 'gpg', fake_gpg),
                        patch.object(v.tempfile, 'gettempdir', return_value=str(self.root / 'local-tmp'))]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def test_concurrent_callers_rotate_once_and_preserve_link(self):
        counter = self.root / 'requests'
        def exchange(store, form):
            with counter.open('a') as out:
                out.write('request\n')
            time.sleep(0.1)
            return {'access_token': 'new', 'refresh_token': 'rotated',
                    'expires_at': time.time() + 3600, 'gpg_recipient': 'test'}
        with patch.object(v, 'token_request', exchange):
            ctx = multiprocessing.get_context('fork')
            workers = [ctx.Process(target=v.access_token) for _ in range(6)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(10)
                self.assertEqual(worker.exitcode, 0)
        self.assertEqual(counter.read_text(), 'request\n')
        self.assertTrue(self.link.is_symlink())
        self.assertFalse(self.target.with_name(self.target.name + '.lock').exists())
        lockdir = self.root / 'local-tmp' / ('vultr-' + str(v.os.getuid()))
        self.assertEqual(len(list(lockdir.iterdir())), 1)
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(self.target.read_text())['refresh_token'], 'rotated')

    def test_uncertain_request_is_not_retried(self):
        with patch.object(v, 'token_request', side_effect=SystemExit(3)) as request:
            with self.assertRaises(SystemExit):
                v.access_token()
            with self.assertRaises(SystemExit):
                v.access_token()
            self.assertEqual(request.call_count, 1)
        self.assertTrue(json.loads(self.target.read_text())['refresh_pending'])

    def test_write_failure_after_rotation_blocks_reuse(self):
        real_save = v.save_store
        count = 0
        def save(path, data):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError('disk full')
            real_save(path, data)
        with patch.object(v, 'save_store', save), patch.object(v, 'token_request', return_value={}) as request:
            with self.assertRaises(OSError):
                v.access_token()
            with self.assertRaises(SystemExit):
                v.access_token()
            self.assertEqual(request.call_count, 1)

    def test_encryption_failure_prevents_request(self):
        with patch.object(v, 'save_store', side_effect=SystemExit(2)), patch.object(v, 'token_request') as request:
            with self.assertRaises(SystemExit):
                v.access_token()
            request.assert_not_called()

    def test_show_does_not_acquire_writer_lock(self):
        # A reader may observe the durable in-progress marker while refresh runs.
        with v.store_lock(self.target):
            with patch.object(v, 'store_lock', side_effect=AssertionError('show must not lock')):
                v.auth_command('show')

    def test_callback_validation(self):
        self.assertEqual(v.callback_code('http://localhost:8765/callback?code=example',
                                        'http://localhost:8765/callback'), 'example')
        for raw in ('http://evil.invalid/callback?code=x',
                    'http://localhost:8765/callback?code=x&code=y',
                    'http://localhost:8765/callback?error=denied'):
            with self.assertRaises(SystemExit):
                v.callback_code(raw, 'http://localhost:8765/callback')


if __name__ == '__main__':
    unittest.main()

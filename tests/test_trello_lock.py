"""Lock boundaries without GPG, real credentials, or network requests."""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('trello', Path(__file__).resolve().parents[1] / 'trello/scripts/trello.py')
t = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(t)


class LockTests(unittest.TestCase):
    def test_refresh_locked_business_unlocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / '.config/agent/auth/trello.json.gpg'
            path.parent.mkdir(parents=True)
            path.touch()
            cfg = dict(client_id='test', client_secret='test', redirect_uri='http://localhost/callback',
                       scopes=['read'], gpg_recipient='test', refresh_token='old', expires_at=0)
            lock = root / ('trello-' + str(os.getuid())) / t.hashlib.sha256(str(path).encode()).hexdigest()
            events = []
            def is_locked():
                with lock.open('a') as out:
                    try:
                        fcntl.flock(out, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        return True
                    return False
            def exchange(data, **kwargs):
                self.assertTrue(is_locked())
                data.update(access_token='new', expires_at=time.time() + 3600)
                events.append('exchange')
            def save(*args):
                self.assertTrue(is_locked())
                events.append('save')
            def request(*args):
                self.assertFalse(is_locked())
                self.assertEqual(args[-1], 'new')
                events.append('business')
                return {}
            with patch.object(t.Path, 'home', return_value=root), \
                 patch.object(t.tempfile, 'gettempdir', return_value=tmp), \
                 patch.object(t, 'gpg', return_value=json.dumps(cfg).encode()), \
                 patch.object(t, 'exchange', exchange), patch.object(t, 'save', save), \
                 patch.object(t, 'request', request), \
                 patch('sys.argv', ['trello.py', 'api', 'GET', '/members/me']):
                t.main()
            self.assertEqual(events, ['exchange', 'save', 'business'])


if __name__ == '__main__':
    unittest.main()

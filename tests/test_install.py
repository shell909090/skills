import contextlib
import io
import subprocess
import sys
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from ruamel.yaml import YAML
yaml = YAML(typ='safe')

SPEC = importlib.util.spec_from_file_location('installer', Path(__file__).resolve().parents[1] / 'scripts/install.py')
i = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(i)


class InstallerTests(unittest.TestCase):
    def test_hermes_backup_preservation_idempotence_and_symlink(self):
        with tempfile.TemporaryDirectory(prefix='hermes-test-') as tmp:
            target = Path(tmp) / 'config.yaml'
            link = Path(tmp) / 'profile.yaml'
            link.symlink_to(target)
            original = b'# important comment\nmodel: "example"  # model comment\nprompt: |\n  keep this text\n\nskills:\n  other: true\n  external_dirs: [/other]\n'
            target.write_bytes(original)
            with patch.dict(os.environ, HERMES_CONFIG=str(link)):
                i.hermes_config()
                data = yaml.load(target.read_bytes())
                self.assertEqual(data['model'], 'example')
                self.assertTrue(data['skills']['other'])
                self.assertIn(b'# important comment', target.read_bytes())
                self.assertIn(b'model: "example"  # model comment', target.read_bytes())
                self.assertIn(b'prompt: |\n  keep this text', target.read_bytes())
                self.assertEqual(data['skills']['external_dirs'], ['/other', str(i.ROOT)])
                self.assertTrue(link.is_symlink())
                backups = list(Path(tmp).glob('config.yaml.bak-*'))
                self.assertEqual(len(backups), 1)
                self.assertEqual(backups[0].read_bytes(), original)
                self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)
                before = target.stat().st_mtime_ns
                i.hermes_config()
                self.assertEqual(target.stat().st_mtime_ns, before)
                self.assertEqual(list(Path(tmp).glob('config.yaml.bak-*')), backups)

    def test_missing_directory_skips_without_creating_it(self):
        with tempfile.TemporaryDirectory(prefix='hermes-test-') as tmp:
            home = Path(tmp) / 'absent'
            with patch.dict(os.environ, HERMES_HOME=str(home), HERMES_CONFIG=''):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    i.hermes_config()
                self.assertIn('config directory does not exist', output.getvalue())
                self.assertFalse(home.exists())

    def test_missing_dependency_exits_successfully_without_changes(self):
        with tempfile.TemporaryDirectory(prefix='hermes-test-') as tmp:
            config = Path(tmp) / 'config.yaml'
            config.write_text('model: example\n')
            before = config.stat()
            # -S disables site-packages, including the test environment's ruamel.
            env = dict(os.environ, HERMES_CONFIG=str(config), PYTHONPATH='')
            result = subprocess.run([sys.executable, '-S', str(i.ROOT / 'scripts/install.py'),
                                     'install-hermes'], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('ruamel.yaml is not installed', result.stdout)
            self.assertEqual(config.read_text(), 'model: example\n')
            self.assertEqual(config.stat().st_mtime_ns, before.st_mtime_ns)
            self.assertEqual(list(Path(tmp).iterdir()), [config])

    def test_invalid_config_untouched(self):
        for content in ('skills: []', 'skills:\n  external_dirs: value', 'a: 1\na: 2', '[broken'):
            with tempfile.TemporaryDirectory(prefix='hermes-test-') as tmp:
                path = Path(tmp) / 'config.yaml'
                path.write_text(content)
                with patch.dict(os.environ, HERMES_CONFIG=str(path)):
                    with self.assertRaises(ValueError):
                        i.hermes_config()
                self.assertEqual(path.read_text(), content)
                self.assertFalse(list(Path(tmp).glob('*.bak-*')))

    def test_separate_targets(self):
        with tempfile.TemporaryDirectory(prefix='skills-test-') as tmp:
            a, c = Path(tmp) / 'agents', Path(tmp) / 'claude'
            config = Path(tmp) / 'config.yaml'
            with patch.dict(os.environ, AGENTS_DIR=str(a), CLAUDE_DIR=str(c), HERMES_CONFIG=str(config)):
                with patch('sys.argv', ['install.py', 'install-codex']):
                    i.main()
                self.assertTrue((a / 'vultr').is_symlink())
                self.assertFalse(c.exists())
                self.assertFalse(config.exists())
                with patch('sys.argv', ['install.py', 'install-claude']):
                    i.main()
                self.assertTrue((c / 'vultr').is_symlink())
                self.assertFalse(config.exists())
                with patch('sys.argv', ['install.py', 'install-hermes']):
                    i.main()
                self.assertIn(str(i.ROOT), config.read_text())

    def test_install_conflicts_idempotence_and_uninstall(self):
        with tempfile.TemporaryDirectory(prefix='skills-test-') as tmp:
            a, c = Path(tmp) / 'agents', Path(tmp) / 'claude'
            a.mkdir()
            (a / 'vultr').mkdir()
            with patch.dict(os.environ, AGENTS_DIR=str(a), CLAUDE_DIR=str(c), HERMES_CONFIG=str(Path(tmp) / 'config.yaml')):
                with patch('sys.argv', ['install.py', 'install']):
                    with self.assertRaises(ValueError):
                        i.main()
                    self.assertFalse(c.exists())
                    (a / 'vultr').rmdir()
                    i.main()
                    i.main()
                self.assertTrue((a / 'vultr').is_symlink())
                with patch('sys.argv', ['install.py', 'uninstall']):
                    i.main()
                self.assertEqual(list(a.iterdir()), [])
                self.assertEqual(list(c.iterdir()), [])


if __name__ == '__main__':
    unittest.main()

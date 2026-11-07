#!/usr/bin/env python3
"""Install per-skill links without overwriting existing user content."""
import argparse
import fcntl
import io
import tempfile
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent


def skills():
    result = []
    for file in sorted(ROOT.glob('*/SKILL.md')):
        name = file.parent.name
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name) or len(name) > 64:
            raise ValueError(f'Invalid skill directory name: {name}')
        if name in ('synced', 'anthropic-skills'):
            raise ValueError(f'Reserved Claude skill name: {name}')
        text = file.read_text()
        parts = text.split('---', 2)
        if len(parts) != 3 or parts[0].strip():
            raise ValueError(f'Missing YAML frontmatter: {file}')
        match = re.search(r'^name:\s*([^\n]+)$', parts[1], re.M)
        if not match or match[1].strip().strip('\"\'') != name:
            raise ValueError(f'Frontmatter name must match directory: {file}')
        if not re.search(r'^description:\s*\S', parts[1], re.M):
            raise ValueError(f'Missing description: {file}')
        result.append(file.parent)
    return result


def same_link(dest, source):
    return dest.is_symlink() and dest.resolve() == source.resolve()


def hermes_config():
    try:
        from ruamel.yaml import YAML
        from ruamel.yaml.error import YAMLError
        from ruamel.yaml.comments import CommentedMap, CommentedSeq
    except ImportError:
        raise ValueError('install-hermes requires ruamel.yaml: pip install ruamel.yaml')
    yaml = YAML(typ='rt')
    yaml.preserve_quotes = True
    yaml.allow_duplicate_keys = False
    yaml.width = 4096
    default = Path(os.environ.get('HERMES_HOME') or str(Path.home() / '.hermes')) / 'config.yaml'
    path = Path(os.environ.get('HERMES_CONFIG') or default).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path) + '.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        exists = path.exists()
        original = path.read_bytes() if exists else b''
        try:
            data = yaml.load(original)
        except YAMLError:
            raise ValueError('Invalid or unsupported Hermes YAML; nothing changed')
        if data is None:
            data = CommentedMap()
        if not isinstance(data, dict):
            raise ValueError('Hermes config must be a YAML mapping')
        section = data.setdefault('skills', CommentedMap())
        if not isinstance(section, dict):
            raise ValueError('skills must be a YAML mapping')
        dirs = section.get('external_dirs', CommentedSeq())
        if not isinstance(dirs, list) or not all(isinstance(x, str) for x in dirs):
            raise ValueError('skills.external_dirs must be a list of paths')
        # Edit the round-trip sequence in place to preserve comments and style.
        indices = [n for n, value in enumerate(dirs) if Path(value).expanduser().resolve() == ROOT]
        if len(indices) == 1:
            print(f'Hermes config unchanged: {path}')
            return
        if indices:
            for n in reversed(indices[1:]):
                del dirs[n]
        else:
            dirs.append(str(ROOT))
        section['external_dirs'] = dirs
        output = io.StringIO()
        yaml.dump(data, output)
        content = output.getvalue().encode()
        backup = None
        if exists:
            bfd, backup = tempfile.mkstemp(prefix=path.name + '.bak-', dir=path.parent)
            with os.fdopen(bfd, 'wb') as out:
                out.write(original)
                out.flush()
                os.fsync(out.fileno())
        tfd, temp = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
        try:
            with os.fdopen(tfd, 'wb') as out:
                out.write(content)
                out.flush()
                os.fsync(out.fileno())
            if (path.read_bytes() if path.exists() else b'') != original:
                raise ValueError('Hermes config changed concurrently; update aborted')
            os.replace(temp, path)
            dfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
        print(f'Updated Hermes config: {path}')
        if backup:
            print(f'Original backup (mode 600): {backup}')
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check', 'install', 'install-codex', 'install-claude', 'install-hermes', 'uninstall', 'hermes-config'])
    action = parser.parse_args().action
    if action in ('hermes-config', 'install-hermes'):
        hermes_config()
        return
    sources = skills()
    targets = [('AGENTS_DIR', '.agents/skills'), ('CLAUDE_DIR', '.claude/skills')]
    if action == 'install-codex':
        targets = targets[:1]
    elif action == 'install-claude':
        targets = targets[1:]
    roots = list(dict.fromkeys(Path(os.environ.get(key) or str(Path.home() / default)).expanduser().absolute()
                              for key, default in targets))
    pairs = [(root / source.name, source) for root in roots for source in sources]
    if action != 'uninstall':
        for root in roots:
            if os.path.lexists(root) and not root.is_dir():
                raise ValueError(f'Not a usable directory: {root}')
        conflicts = [str(dest) for dest, source in pairs
                     if os.path.lexists(dest) and not same_link(dest, source)]
        if conflicts:
            raise ValueError('Conflicting targets (nothing changed):\n' + '\n'.join(conflicts))
    for dest, source in pairs:
        if action in ('install', 'install-codex', 'install-claude') and not same_link(dest, source):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.symlink_to(source, target_is_directory=True)
            print(f'Linked {dest} -> {source}')
        elif action == 'uninstall' and same_link(dest, source):
            dest.unlink()
            print(f'Unlinked {dest}')
    print(f'{action}: {len(sources)} skills; {len(roots)} discovery directories')
    if action == 'install':
        hermes_config()


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)

#!/usr/bin/env python3
"""Lightweight CI checks for the Girl Agent Love framework.

Runs without the Ren'Py SDK: validates the repository structure, YAML
templates, Python helpers, Ren'Py scripts (encoding + required defines),
version consistency, and the bilingual README links.
"""

import glob
import os
import py_compile
import re
import sys
import tempfile

try:
    import yaml
except ImportError:  # pragma: no cover - CI installs pyyaml
    yaml = None

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

errors = []
notes = []


def fail(msg):
    errors.append(msg)


def ok(msg):
    notes.append(msg)


def rel(p):
    return os.path.join(ROOT, p)


def check_required_files():
    required = [
        'README.md',
        'README-us.md',
        'LICENSE',
        'NOTICE',
        'THIRD_PARTY_NOTICES.md',
        'options.txt',
        'key.txt',
        'game/options.rpy',
        'game/script.rpy',
        'game/ai.rpy',
        'game/screens.rpy',
        'game/settings.rpy',
        'game/seikai.example.md',
    ]
    for p in required:
        if not os.path.isfile(rel(p)):
            fail('missing required file: %s' % p)
    ok('required files present')


def check_yaml():
    if yaml is None:
        fail('pyyaml is not installed')
        return
    files = glob.glob(rel('.github/**/*.yml'), recursive=True) + glob.glob(rel('.github/**/*.yaml'), recursive=True)
    if not files:
        fail('no YAML templates found under .github/')
        return
    for f in files:
        try:
            with open(f, encoding='utf-8') as fh:
                yaml.safe_load(fh)
        except Exception as exc:
            fail('invalid YAML: %s (%s)' % (os.path.relpath(f, ROOT), exc))
    ok('YAML templates valid (%d files)' % len(files))


def check_python():
    files = [p for p in glob.glob(rel('**/*.py'), recursive=True) if '.git' not in p]
    pyc_dir = tempfile.mkdtemp(prefix='ci-check-')
    for f in files:
        try:
            py_compile.compile(f, doraise=True, cfile=os.path.join(pyc_dir, 'check.pyc'))
        except Exception as exc:
            fail('python syntax error: %s (%s)' % (os.path.relpath(f, ROOT), exc))
    ok('python helpers compile (%d files)' % len(files))


def check_rpy():
    files = [p for p in glob.glob(rel('**/*.rpy'), recursive=True) if '.git' not in p]
    if not files:
        fail('no .rpy files found')
        return
    for f in files:
        try:
            with open(f, encoding='utf-8') as fh:
                text = fh.read()
        except UnicodeDecodeError as exc:
            fail('invalid UTF-8 in %s (%s)' % (os.path.relpath(f, ROOT), exc))
            continue
        if not text.strip():
            fail('empty .rpy file: %s' % os.path.relpath(f, ROOT))
        if 'renpy' in text and '"' not in text and "'" not in text:
            notes.append('suspicious quoting in %s' % os.path.relpath(f, ROOT))
    ok('Ren\'Py scripts readable (%d files)' % len(files))


def check_version():
    options = rel('game/options.rpy')
    try:
        text = open(options, encoding='utf-8').read()
    except OSError:
        return
    m = re.search(r'define\s+config\.version\s*=\s*"([^"]+)"', text)
    if not m:
        fail('game/options.rpy has no config.version')
        return
    version = m.group(1)
    if not re.search(r'define\s+config\.name\s*=', text):
        fail('game/options.rpy has no config.name')
    for readme in ('README.md', 'README-us.md'):
        try:
            body = open(rel(readme), encoding='utf-8').read()
        except OSError:
            continue
        if version not in body:
            fail('%s does not mention version %s' % (readme, version))
    ok('version consistent: %s' % version)


def check_bilingual():
    try:
        zh = open(rel('README.md'), encoding='utf-8').read()
        en = open(rel('README-us.md'), encoding='utf-8').read()
    except OSError:
        return
    if 'README-us.md' not in zh:
        fail('README.md does not link to README-us.md')
    if 'README.md' not in en:
        fail('README-us.md does not link back to README.md')
    ok('bilingual README links present')


def main():
    check_required_files()
    check_yaml()
    check_python()
    check_rpy()
    check_version()
    check_bilingual()

    print('--- checks passed ---')
    for n in notes:
        print('  ok:', n)
    if errors:
        print('--- failures ---')
        for e in errors:
            print('  FAIL:', e)
        print('%d check(s) failed' % len(errors))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())

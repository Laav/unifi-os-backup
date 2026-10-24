#!/usr/bin/env python3
"""Entry point; configuration arrives as NUL-delimited stdin from Bash."""
import argparse
import json
import os
from pathlib import Path
import sys

from core import Failure, select
from verify import record, verify
from replication import replicate


def configuration():
    raw = sys.stdin.buffer.read(4 * 1024 * 1024).split(b'\0')
    if raw and raw[-1] == b'':
        raw.pop()
    if len(raw) % 2:
        raise Failure('Incomplete configuration stream', 78)
    sections, current, complete = {'main': {}}, 'main', False
    for key, value in zip(raw[::2], raw[1::2]):
        key, value = key.decode(), value.decode()
        if key == '@section':
            current = value
            sections.setdefault(current, {})
        elif key == '@complete':
            complete = value == 'true'
        else:
            sections[current][key] = value
    if not complete:
        raise Failure('Configuration loading failed', 78)
    return sections


def parser(command):
    p = argparse.ArgumentParser(prog='unifi-backup-' + command)
    p.add_argument('--config', help='Root-owned Bash config (processed by wrapper)')
    p.add_argument('--json', action='store_true')
    p.add_argument('--quiet', action='store_true')
    p.add_argument('--latest', action='store_true')
    p.add_argument('--all', action='store_true')
    p.add_argument('--file')
    p.add_argument('--backup-id')
    p.add_argument('--decrypt-check', action='store_true')
    p.add_argument('--identity')
    p.add_argument('--target')
    return p


def main():
    os.umask(0o077)
    command = sys.argv[1]
    args = parser(command).parse_args(sys.argv[2:])
    sections = configuration()
    c = sections['main']
    if args.target:
        if args.target not in sections or args.target == 'main':
            raise Failure('Unknown storage target', 78)
        sections = {'main': c, args.target: sections[args.target]}
    if args.decrypt_check and not args.identity:
        raise Failure('--decrypt-check requires a protected --identity file', 78)
    if command == 'verify':
        if not (args.latest or args.all or args.file or args.backup_id):
            args.latest = True
        results = [verify(path, c, args.identity if args.decrypt_check else None) for path in select(c, args)]
        record(c, results)
        if not args.quiet:
            if args.json:
                print(json.dumps({'schema_version': 1, 'results': results}, separators=(',', ':')))
            else:
                for item in results:
                    print(f"{'OK' if item['success'] else 'FAILED'} {item['filename']}: hash={item['hash_valid']} metadata={item['metadata_valid']} decryption={item['decryption']} structure={item['structure']['status']} restore_tested=false")
        return 0 if all(r['success'] for r in results) else 74
    if command == 'replicate':
        reports = [replicate(path, sections) for path in select(c, args)]
        if not args.quiet:
            print(json.dumps({'results': reports}, separators=(',', ':')) if args.json else '\n'.join(f"Local={r['local_backup']} replication={r['replication']} policy={r['policy_satisfied']}" for r in reports))
        return 0 if all(r['policy_satisfied'] for r in reports) else 75
    raise Failure('Unsupported command', 64)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Failure as exc:
        print(json.dumps({'event': 'operation_failed', 'error': str(exc), 'exit_code': exc.code}), file=sys.stderr)
        sys.exit(exc.code)
    except (OSError, ValueError, TypeError, KeyError):
        # Never stringify untrusted provider/JSON exceptions: they may contain
        # URLs, credentials or plaintext configuration data.
        print('Operation failed: invalid data or unavailable local resource', file=sys.stderr)
        sys.exit(74)

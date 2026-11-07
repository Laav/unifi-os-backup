#!/usr/bin/env python3
"""Configuration CLI: independent of Bash sourcing, UI and backup execution."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

from core import Failure, VERSION
from config_model import Model, Issue
from config_schema import reference
from config_transaction import Transaction


class Interrupted(BaseException):
    def __init__(self, signum):
        self.code = 128 + signum


def main(argv=None):
    os.umask(0o077)
    p = argparse.ArgumentParser(description='Secure full-screen configuration manager; no live tests or backup runs without explicit action.')
    p.add_argument('--version', action='version', version='unifi-backup-configure ' + VERSION)
    p.add_argument('--config', default='/etc/unifi-backup/unifi-backup.env', help='Main configuration path; existing referenced paths are respected')
    actions = p.add_mutually_exclusive_group()
    actions.add_argument('--guided', action='store_true', help='Open guided setup before the main menu (TTY and dialog required)')
    actions.add_argument('--validate', action='store_true', help='Offline syntax, permissions, dependencies and enabled-feature validation; no TTY')
    actions.add_argument('--inspect', '--dry-run', dest='inspect', action='store_true', help='Non-mutating redacted inspection and file-change plan; no TTY')
    actions.add_argument('--reference', action='store_true', help='Print the generated complete configuration inventory; no configuration required')
    actions.add_argument('--recover', action='store_true', help='Roll back an interrupted file transaction')
    actions.add_argument('--rollback', metavar='TRANSACTION_ID', help='Roll back a completed transaction if no affected files changed since')
    p.add_argument('--yes', action='store_true', help='Explicitly confirm --recover or --rollback; never bypasses validation or conflict checks')
    p.add_argument('--json', action='store_true', help='Machine-readable redacted inspection/validation')
    args = p.parse_args(argv)
    if args.yes and not (args.recover or args.rollback):
        p.error('--yes is only for recovery/rollback')
    if args.reference:
        print(reference(), end='')
        return 0
    if args.recover or args.rollback:
        if os.name != 'posix' or os.geteuid() != 0:
            raise Failure('Production configuration recovery requires Linux root privileges', 77)
        identifier = Transaction(args.config).rollback(args.rollback, args.yes)
        print('Configuration rolled back: ' + identifier)
        return 0
    if not (args.validate or args.inspect):
        if os.name != 'posix' or os.geteuid() != 0:
            raise Failure('Interactive production configuration requires Linux root privileges', 77)
        # Fail fast on missing TTY/dependency, before touching any config path.
        from config_ui import Dialog, Wizard
        ui = Dialog()
        model = Model(args.config)
        helper = Path(__file__).resolve().parents[2] / 'bin'
        Wizard(model, ui, helper if helper.is_dir() else '/usr/local/sbin').run(args.guided)
        return 0
    model = Model(args.config)
    issues = model.validate()
    report = {'schema_version': 1, 'live_tests_run': False}
    if args.inspect:
        try:
            plan = model.plan()
        except Failure as exc:
            issues.append(Issue('security' if exc.code == 77 else 'configuration', 'plan', str(exc)))
            plan = []
        report.update({'settings': model.summary(), 'files': [{'path': str(i['path']), 'new': i['before'] is None,
                       'scope': i['scope'], 'settings': i['keys']} for i in plan], 'configuration_modified': False})
    report.update({'valid': not any(not i.warning for i in issues), 'issues': [asdict(i) for i in issues]})
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=True))
    else:
        from config_ui import issue_text
        print(issue_text(issues))
        if args.inspect:
            for row in report['settings']:
                print(row['section'] + '.' + row['setting'] + '=' + row['new'])
            for item in report['files']:
                print(('Would create: ' if item['new'] else 'Would update: ') + item['path'])
    errors = [i for i in issues if not i.warning]
    for category, code in [('syntax', 65), ('security', 77), ('dependency', 69)]:
        if any(i.category == category for i in errors):
            return code
    return 78 if errors else 0


def entry():
    def interrupted(signum, _frame):
        raise Interrupted(signum)
    for name in ('SIGHUP', 'SIGINT', 'SIGTERM'):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), interrupted)
    try:
        return main()
    except Failure as exc:
        if '--json' in sys.argv:
            print(json.dumps({'schema_version': 1, 'valid': False, 'event': 'configuration_failed', 'exit_code': exc.code, 'error': str(exc)}), file=sys.stderr)
        else:
            print('unifi-backup-configure: ' + str(exc), file=sys.stderr)
        return exc.code
    except Interrupted as exc:
        print('Configuration interrupted. Unapplied edits were discarded; recover a pending transaction if reported.', file=sys.stderr)
        return exc.code
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, subprocess.SubprocessError):
        # Do not print exception bodies: third-party/system values may be secret.
        print('Configuration operation failed safely: invalid data or unavailable resource. No diagnostic values were exported.', file=sys.stderr)
        return 74


if __name__ == '__main__':
    sys.exit(entry())

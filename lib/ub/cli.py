#!/usr/bin/env python3
"""Entry point; configuration arrives as NUL-delimited stdin from Bash."""
import argparse
import json
import os
import signal
from pathlib import Path
import sys

from core import Failure, select
from verify import record, verify
from replication import replicate
from replication import remote_check
from storage import Store
from retry_queue import retry
from retry_queue import update as queue_update
from core import iso, save_state, state, metric, now
from policy import capability, confirmation, settings
from retention import apply as retain
from recovery import restore
from anomaly import analyze, history_record
from config_diff import diff
from core import local_files, metadata
from core import boolean, integer
from core import VERSION


class Interrupted(BaseException):
    def __init__(self, signum):
        self.code = 128 + signum


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
    p.add_argument('--version', action='version', version='%(prog)s ' + VERSION)
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
    p.add_argument('--full', action='store_true')
    p.add_argument('--force-due', action='store_true', help='Retry pending jobs now; attempt/age limits still apply')
    p.add_argument('--check', action='store_true')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--list', action='store_true')
    p.add_argument('--date', help='ISO date prefix, such as 2026-10-24')
    p.add_argument('--output', help='Private restore destination directory')
    p.add_argument('--verify-only', action='store_true')
    p.add_argument('--baseline', type=int)
    p.add_argument('--explain', action='store_true')
    p.add_argument('--run-id')
    p.add_argument('--exit-code', type=int, default=0)
    p.add_argument('--duration', type=int, default=0)
    p.add_argument('--failure-category', choices=('none', 'authentication', 'download', 'replication', 'other'), default='none')
    p.add_argument('--old')
    p.add_argument('--new')
    p.add_argument('--latest-two', action='store_true')
    p.add_argument('--backup-id-old')
    p.add_argument('--backup-id-new')
    p.add_argument('--summary', action='store_true')
    p.add_argument('--category')
    p.add_argument('--unchanged', action='store_true')
    p.add_argument('--scheduled', action='store_true', help='Honor opt-in automatic-operation configuration')
    return p


def main():
    os.umask(0o077)
    def interrupted(signum, frame):
        raise Interrupted(signum)
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, interrupted)
    command = sys.argv[1]
    args = parser(command).parse_args(sys.argv[2:])
    if sum(bool(x) for x in (args.latest, args.all, args.file, args.backup_id)) > 1:
        raise Failure('Choose one backup selector: --latest, --all, --file or --backup-id', 64)
    sections = configuration()
    c = sections['main']
    if args.scheduled:
        flag = {'verify': 'VERIFY_ENABLED', 'remote-verify': 'REMOTE_VERIFY_ENABLED', 'retry': 'RETRY_ENABLED',
                'analyze': 'ANOMALY_ENABLED', 'diff': 'DIFF_ENABLED'}.get(command)
        if flag and not boolean(c, flag):
            return 0
    if command == 'validate':
        for flag in ('VERIFY_ENABLED', 'VERIFY_DECRYPT_CHECK', 'RETRY_ENABLED', 'REMOTE_VERIFY_ENABLED', 'ANOMALY_ENABLED', 'DIFF_ENABLED'):
            boolean(c, flag)
        integer(c, 'BACKUP_REQUIRED_TARGETS', 0, 0, max(0, len(sections) - 1))
        integer(c, 'RETRY_MAX_ATTEMPTS', 8, 1, 100)
        integer(c, 'RETRY_QUEUE_LIMIT', 1000, 1, 100000)
        interval = integer(c, 'RETRY_MAX_INTERVAL', 86400, 1, 604800)
        integer(c, 'RETRY_BASE_INTERVAL', 300, 1, interval)
        integer(c, 'RETRY_MAX_AGE_DAYS', 7, 1, 365)
        baseline = integer(c, 'ANOMALY_BASELINE', 20, 2, 200)
        integer(c, 'ANOMALY_MIN_SAMPLES', 5, 2, baseline)
        integer(c, 'ANOMALY_SIZE_PERCENT', 50, 1, 10000)
        integer(c, 'ANOMALY_DURATION_PERCENT', 200, 1, 10000)
        integer(c, 'ANOMALY_IDENTICAL_COUNT', 0, 0, 200)
        integer(c, 'ANOMALY_HISTORY_LIMIT', 200, 30, 10000)
        integer(c, 'ANOMALY_FAILURE_STREAK', 3, 2, 100)
        integer(c, 'RESTORE_MAX_BYTES', 10737418240, 1, 1099511627776)
        if c.get('RETENTION_MODE', 'legacy') not in ('legacy', 'gfs'):
            raise Failure('RETENTION_MODE must be legacy or gfs', 78)
        tiers = [integer(c, 'GFS_' + tier, 0) for tier in ('DAILY', 'WEEKLY', 'MONTHLY', 'YEARLY')]
        if c.get('RETENTION_MODE') == 'gfs' and not any(tiers):
            raise Failure('GFS requires at least one nonzero tier', 78)
        for identifier, values in sections.items():
            if identifier != 'main':
                if values.get('TARGET_TYPE') not in ('s3', 'azure_blob', 'filesystem'):
                    raise Failure('Invalid TARGET_TYPE', 78)
                boolean(values, 'TARGET_REQUIRED')
                if values.get('TARGET_VERIFY', 'metadata') not in ('none', 'exists', 'metadata', 'full'):
                    raise Failure('Invalid TARGET_VERIFY', 78)
                action = values.get('TARGET_IMMUTABILITY', 'none')
                if action not in ('none', 'check', 'request'):
                    raise Failure('Invalid TARGET_IMMUTABILITY', 78)
                integer(values, 'TARGET_LOCK_DAYS', 30, 1, 36500)
                mode = values.get('TARGET_LOCK_MODE', 'GOVERNANCE' if values['TARGET_TYPE'] == 's3' else 'locked')
                if action == 'request' and mode in ('COMPLIANCE', 'locked') and not boolean(values, 'TARGET_ALLOW_PERMANENT_LOCK'):
                    raise Failure('Permanent immutable protection requires explicit consent in target configuration', 78)
        return 0
    if args.target:
        if args.target not in sections or args.target == 'main':
            raise Failure('Unknown storage target', 78)
        sections = {'main': c, args.target: sections[args.target]}
    if args.decrypt_check and not args.identity:
        raise Failure('--decrypt-check requires a protected --identity file', 78)
    if command == 'restore':
        store = Store(args.target, sections[args.target]) if args.target else None
        report = restore(c, args, store)
        if not args.quiet:
            print(json.dumps(report, separators=(',', ':')) if args.json else json.dumps(report, indent=2))
        return 0
    if command == 'history':
        history_record(c, {'id': args.run_id, 'exit_code': args.exit_code, 'duration_seconds': args.duration,
                          'recorded_at': iso(), 'failure_category': args.failure_category})
        return 0
    if command == 'enqueue':
        for path in select(c, args):
            queue_update(c, path, args.target or 'legacy', False, 'legacy_upload_failed')
        return 0
    if command == 'diff':
        older, newer = args.old, args.new
        if args.latest_two:
            items = local_files(c)
            if len(items) < 2:
                raise Failure('Two backups are required', 66)
            newer, older = items[:2]
        if args.backup_id_old or args.backup_id_new:
            matches = {}
            for path in local_files(c):
                bid = metadata(path)['backup']['id']
                if bid in matches:
                    raise Failure('Ambiguous backup ID', 65)
                matches[bid] = path
            older, newer = matches.get(args.backup_id_old), matches.get(args.backup_id_new)
        if not older or not newer:
            raise Failure('Select --old/--new, --latest-two or both backup IDs', 64)
        report = diff(c, older, newer, args.category, args.unchanged)
        if args.summary:
            report.pop('changes')
        if not args.quiet:
            print(json.dumps(report, separators=(',', ':')) if args.json else json.dumps(report, indent=2))
        return 0
    if command == 'analyze':
        if args.baseline is not None and not 2 <= args.baseline <= 200:
            raise Failure('--baseline must be between 2 and 200', 78)
        report = analyze(c, args.baseline, args.all)
        if not args.quiet:
            print(json.dumps(report, separators=(',', ':')) if args.json else json.dumps(report, indent=2))
        return 1 if report['results'][-1]['findings'] else 0
    if command == 'retention':
        report = retain(c, args.dry_run)
        if not args.quiet:
            print(json.dumps(report, separators=(',', ':')))
        return 0
    if command == 'storage-policy':
        results = []
        for identifier, config in sections.items():
            if identifier == 'main':
                continue
            report = {'target': identifier, 'success': False, 'dry_run': args.dry_run}
            try:
                store = Store(identifier, config)
                action, mode, days = settings(store)
                report.update({'capabilities': capability(store), 'configured_action': action, 'configured_mode': mode, 'configured_days': days})
                if args.file:
                    report['object'] = confirmation(store, Path(args.file).name)
                report['success'] = action == 'none' or report['capabilities']['supported']
                if action != 'none' and 'object' in report:
                    report['success'] = report['success'] and report['object']['confirmed']
            except Failure as exc:
                report['error'] = str(exc)
            results.append(report)
        if not results:
            raise Failure('No storage targets configured', 78)
        if not args.quiet:
            print(json.dumps({'results': results}, separators=(',', ':')))
        return 0 if all(r['success'] for r in results) else 75
    if command == 'verify':
        if args.scheduled and boolean(c, 'VERIFY_DECRYPT_CHECK'):
            args.identity = c.get('VERIFY_IDENTITY_FILE')
            if not args.identity:
                raise Failure('VERIFY_IDENTITY_FILE required for scheduled decryption check', 78)
            args.decrypt_check = True
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
    if command == 'retry':
        results = retry(sections, args.force_due)
        if not args.quiet:
            print(json.dumps({'results': results}, separators=(',', ':')))
        return 0 if all(r['policy_satisfied'] for r in results) else 75
    if command == 'remote-verify':
        results = []
        for path in select(c, args):
            local_result = verify(path, c)
            if not local_result['success']:
                raise Failure('Remote verification refused: local reference failed integrity checks', 74)
            for identifier, config in sections.items():
                if identifier == 'main':
                    continue
                result = {'filename': path.name, 'target': identifier, 'success': False}
                try:
                    store = Store(identifier, config)
                    if store.level == 'none':
                        store.level = 'metadata'
                    result.update(remote_check(store, path, c, args.full))
                    if args.decrypt_check:
                        from verify import decrypt
                        from core import state_dir, atomic
                        import tempfile
                        with tempfile.TemporaryDirectory(dir=state_dir(c)) as directory:
                            downloaded = Path(directory) / path.name
                            store.download(path.name, downloaded)
                            atomic(str(downloaded) + '.json', metadata(path))
                            decrypted = verify(downloaded, c, args.identity)
                            if not decrypted['success']:
                                raise Failure('Remote decrypt verification failed', 74)
                            result['decryption'] = decrypted['decryption']
                    result['success'] = True
                except Failure as exc:
                    result['error'] = str(exc)
                    result['error_code'] = exc.code
                    result['status'] = {66: 'missing', 74: 'mismatch', 69: 'unavailable', 75: 'rejected'}.get(exc.code, 'failed')
                results.append(result)
        if not results:
            raise Failure('No remote targets selected', 78)
        previous_remote = state(c, 'remote-verification.json', {'targets': {}})
        target_state = previous_remote.get('targets', {})
        for result in results:
            previous_target = target_state.get(result['target'], {})
            target_state[result['target']] = {'last_checked_at': iso(), 'last_result': result,
                'last_success_at': iso() if result['success'] else previous_target.get('last_success_at')}
        save_state(c, 'remote-verification.json', {'schema_version': 1, 'checked_at': iso(), 'results': results, 'targets': target_state})
        metric(c, 'unifi_remote_verification.prom', {'unifi_backup_remote_verification_success': int(all(x['success'] for x in results)),
               'unifi_backup_remote_verification_failures': sum(not x['success'] for x in results), 'unifi_backup_remote_verification_timestamp_seconds': now()})
        if not args.quiet:
            print(json.dumps({'results': results}, separators=(',', ':')))
        return 0 if all(r['success'] for r in results) else 74
    raise Failure('Unsupported command', 64)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Failure as exc:
        print(json.dumps({'event': 'operation_failed', 'error': str(exc), 'exit_code': exc.code}), file=sys.stderr)
        sys.exit(exc.code)
    except Interrupted as exc:
        print('Operation interrupted; persistent state is retained', file=sys.stderr)
        sys.exit(exc.code)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        # Never stringify untrusted provider/JSON exceptions: they may contain
        # URLs, credentials or plaintext configuration data.
        print('Operation failed: invalid data or unavailable local resource', file=sys.stderr)
        sys.exit(74)

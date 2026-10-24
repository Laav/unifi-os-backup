"""Legacy retention plus opt-in GFS protection and retry pins."""
import datetime as dt
from pathlib import Path

from core import Failure, integer, local_files, now, safe_path
from retry_queue import pins


def plan(c):
    files = sorted(local_files(c), key=lambda p: (p.stat().st_mtime, p.name), reverse=True)
    days = integer(c, 'RETENTION_DAYS', 35)
    maximum = integer(c, 'RETENTION_COUNT', 0)
    minimum = integer(c, 'RETENTION_MIN_COUNT', 1)
    if maximum and maximum < minimum:
        raise Failure('RETENTION_COUNT must be zero or >= RETENTION_MIN_COUNT', 78)
    mode = c.get('RETENTION_MODE', 'legacy')
    if mode not in ('legacy', 'gfs'):
        raise Failure('RETENTION_MODE must be legacy or gfs', 78)
    protected = {p.name: ['minimum'] for p in files[:minimum]}
    if mode == 'gfs':
        levels = [('DAILY', lambda t: t.strftime('%Y-%m-%d')), ('WEEKLY', lambda t: t.strftime('%G-%V')),
                  ('MONTHLY', lambda t: t.strftime('%Y-%m')), ('YEARLY', lambda t: t.strftime('%Y'))]
        counts = [integer(c, 'GFS_' + name, 0) for name, _ in levels]
        if not any(counts):
            raise Failure('GFS requires at least one nonzero retention tier', 78)
        for (level, key), count in zip(levels, counts):
            chosen = set()
            for path in sorted(files, key=lambda p: p.name, reverse=True):
                try:
                    stamp = dt.datetime.strptime(path.name[16:35], '%Y-%m-%d_%H-%M-%S')
                except ValueError:
                    raise Failure('Managed filename has invalid calendar date; retention refused', 65) from None
                bucket = key(stamp)
                if bucket not in chosen and len(chosen) < count:
                    chosen.add(bucket)
                    protected.setdefault(path.name, []).append('gfs_' + level.lower())
    for name in pins(c):
        protected.setdefault(name, []).append('pending_retry')
    decisions = []
    for index, path in enumerate(files):
        reason = protected.get(path.name, [])
        expired = bool((days and now() - path.stat().st_mtime > days * 86400) or (maximum and index >= maximum))
        delete = not reason and (mode == 'gfs' or expired)
        decisions.append({'filename': path.name, 'delete': delete, 'keep_reasons': reason or ([] if delete else ['within_legacy_policy'])})
    return decisions


def apply(c, dry_run=False):
    decisions = plan(c)
    directory = safe_path(c.get('BACKUP_DIR', '/var/backups/unifi'))
    if not dry_run:
        # Validate every selected pair before deleting anything.
        for decision in decisions:
            if decision['delete']:
                p = safe_path(directory / decision['filename'])
                side = safe_path(str(p) + '.json')
                if side.exists() and not side.is_file():
                    raise Failure('Unexpected sidecar object; retention refused')
        for decision in decisions:
            if decision['delete']:
                p = directory / decision['filename']
                p.unlink()
                Path(str(p) + '.json').unlink(missing_ok=True)
    return {'dry_run': dry_run, 'decisions': decisions, 'removed_count': sum(d['delete'] for d in decisions)}

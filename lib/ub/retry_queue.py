"""Crash-safe bounded retry queue. Caller holds the shared operation lock."""
import hashlib
from pathlib import Path
import random

from core import Failure, NAME, digest, event, integer, iso, metadata, metric, now, save_state, state


def task_key(backup_id, target):
    return hashlib.sha256((backup_id + '\0' + target).encode()).hexdigest()


def update(c, path, target, success, error='', increment=True):
    doc = metadata(path)
    queue = state(c, 'retry-queue.json', {'schema_version': 1, 'tasks': {}})
    key = task_key(doc['backup']['id'], target)
    job = queue['tasks'].get(key)
    if success:
        if job:
            job.update({'status': 'complete', 'completed_at': iso(), 'last_error': ''})
    else:
        limit = integer(c, 'RETRY_QUEUE_LIMIT', 1000, 1, 100000)
        if job and job.get('status') == 'dead' and job.get('last_error') == 'queue_capacity_exceeded':
            return
        if not job:
            active = sum(t['status'] == 'pending' for t in queue['tasks'].values())
            job = {'backup_id': doc['backup']['id'], 'filename': path.name, 'target': target,
                   'expected_sha256': doc['backup']['sha256'], 'attempts': 0, 'created_timestamp': now()}
            queue['tasks'][key] = job
            if active >= limit:
                # This task is explicitly dead-lettered rather than silently
                # disappearing or pinning unlimited backup data.
                job.update({'status': 'dead', 'last_error': 'queue_capacity_exceeded', 'updated_at': iso()})
                save_state(c, 'retry-queue.json', queue)
                return
        attempts = job['attempts'] + int(increment)
        max_attempts = integer(c, 'RETRY_MAX_ATTEMPTS', 8, 1, 100)
        maximum = integer(c, 'RETRY_MAX_INTERVAL', 86400, 1, 604800)
        base = integer(c, 'RETRY_BASE_INTERVAL', 300, 1, maximum)
        interval = min(maximum, base * 2 ** min(attempts - 1, 30))
        age_limit = integer(c, 'RETRY_MAX_AGE_DAYS', 7, 1, 365) * 86400
        dead = attempts >= max_attempts or now() - job['created_timestamp'] >= age_limit
        job.update({'status': 'dead' if dead else 'pending', 'attempts': attempts,
                    'next_attempt_timestamp': now() + random.SystemRandom().randint(max(1, interval // 2), interval),
                    'updated_at': iso(), 'last_error': error})
    # Bound historical terminal state as well as active pins.
    terminal = sorted((k for k, t in queue['tasks'].items() if t['status'] != 'pending'), key=lambda k: queue['tasks'][k]['created_timestamp'])
    for old in terminal[:-integer(c, 'RETRY_QUEUE_LIMIT', 1000, 1, 100000)]:
        del queue['tasks'][old]
    save_state(c, 'retry-queue.json', queue)
    if job:
        event(c, 'retry_task_updated', 'Persistent retry state updated', target=target, status=job['status'], attempts_count=job['attempts'])
    metrics(c, queue)


def metrics(c, queue=None):
    queue = queue or state(c, 'retry-queue.json', {'tasks': {}})
    tasks = list(queue['tasks'].values())
    pending = [t for t in tasks if t['status'] == 'pending']
    metric(c, 'unifi_retry.prom', {
        'unifi_backup_pending_uploads': len(pending),
        'unifi_backup_dead_uploads': sum(t['status'] == 'dead' for t in tasks),
        'unifi_backup_retry_attempts': sum(t['attempts'] for t in tasks),
        'unifi_backup_replication_lag_seconds': max((now() - t['created_timestamp'] for t in pending), default=0),
    })


def pins(c, persist=True):
    queue = state(c, 'retry-queue.json', {'tasks': {}})
    tasks = queue.get('tasks')
    if not isinstance(tasks, dict):
        raise Failure('Malformed retry queue; retention refused', 65)
    pinned = set()
    changed = False
    age_limit = integer(c, 'RETRY_MAX_AGE_DAYS', 7, 1, 365) * 86400
    for task in tasks.values():
        if not isinstance(task, dict) or not NAME.fullmatch(str(task.get('filename', ''))) or task.get('status') not in ('pending', 'dead', 'complete'):
            raise Failure('Malformed retry task; retention refused', 65)
        if task['status'] == 'pending':
            if not isinstance(task.get('created_timestamp'), int):
                raise Failure('Malformed retry timestamp; retention refused', 65)
            if now() - task['created_timestamp'] >= age_limit:
                task.update({'status': 'dead', 'last_error': 'retry_age_exhausted', 'updated_at': iso()})
                changed = True
            else:
                pinned.add(task['filename'])
    if changed and persist:
        save_state(c, 'retry-queue.json', queue)
        metrics(c, queue)
    return pinned


def retry(sections, force=False):
    from replication import replicate
    c = sections['main']
    results = []
    pins(c)  # Validate every persisted filename before resolving any path.
    tasks = state(c, 'retry-queue.json', {'tasks': {}})['tasks']
    directory = Path(c.get('BACKUP_DIR', '/var/backups/unifi'))
    for job in list(tasks.values()):
        if job['status'] != 'pending' or (not force and job['next_attempt_timestamp'] > now()):
            continue
        path = directory / job['filename']
        # Both metadata and job identity are checked before provider actions.
        try:
            doc = metadata(path)
            if doc['backup']['id'] != job['backup_id'] or digest(path) != job['expected_sha256']:
                raise Failure('Retry source identity/checksum mismatch')
            if job['target'] not in sections:
                raise Failure('Retry target no longer configured', 78)
            report = replicate(path, sections, only_target=job['target'])
            results.append(report)
        except Failure:
            # A vanished/corrupt source cannot safely be retried. Keep an
            # explicit dead letter for monitoring and operator investigation.
            key = task_key(job['backup_id'], job['target'])
            queue = state(c, 'retry-queue.json')
            queue['tasks'][key].update({'status': 'dead', 'last_error': 'source_or_target_unavailable', 'updated_at': iso()})
            save_state(c, 'retry-queue.json', queue)
            results.append({'backup_id': job['backup_id'], 'policy_satisfied': False, 'target': job['target'], 'error': 'source_or_target_unavailable'})
    metrics(c)
    latest = {}
    for result in results:
        latest[result['backup_id']] = result
    return list(latest.values())

"""Per-target replication policy, independent from local artifact validity."""
import tempfile
from pathlib import Path

from core import Failure, atomic, digest, event, integer, iso, load, metadata, metric, now, save_state, state, state_dir
from storage import Store
from verify import verify
from retry_queue import update as queue_update
from policy import upload_headers, confirmation, settings


def remote_check(store, path, c, full=False):
    doc = metadata(path)
    expected = doc['backup']
    info = store.head(path.name)
    result = {'exists': True, 'size_matches': info['size'] == expected['size_bytes'],
              'metadata_matches': info['sha256'] == expected['sha256'],
              'contents_match': 'not_checked', 'checked_at': iso()}
    if store.level == 'exists' and not full:
        result['size_matches'] = 'not_checked'
        result['metadata_matches'] = 'not_checked'
        return result
    if not result['size_matches']:
        raise Failure('Remote object size mismatch')
    if full:
        with tempfile.TemporaryDirectory(prefix='.remote-check.', dir=state_dir(c)) as directory:
            candidate = Path(directory) / path.name
            store.download(path.name, candidate)
            result['contents_match'] = digest(candidate) == expected['sha256']
            if not result['contents_match']:
                raise Failure('Remote SHA256 mismatch')
    elif store.level == 'metadata' and not result['metadata_matches']:
        raise Failure('Remote checksum metadata mismatch')
    return result


def replicate(path, sections, only_target=None):
    c = sections['main']
    checked = verify(path, c)
    if not checked['success']:
        raise Failure('Replication refused: local integrity check failed')
    doc = metadata(path)
    previous = doc.get('replication', {}).get('targets', {})
    targets = {identifier: {**previous.get(identifier, {'status': 'not_attempted'}),
                           'required': config.get('TARGET_REQUIRED', 'false') == 'true'}
               for identifier, config in sections.items() if identifier != 'main'}
    for identifier, config in sections.items():
        if identifier == 'main' or (only_target and identifier != only_target):
            continue
        # Persist intent before any provider action. A killed worker leaves a
        # resumable task even if the PUT completed but its response was lost.
        queue_update(c, path, identifier, False, 'upload_in_progress')
        try:
            store = Store(identifier, config)
            start = now()
            lock_headers, horizon = upload_headers(store, path)
            store.upload(path, lock_headers)
            immutable = confirmation(store, path.name, horizon) if settings(store)[0] != 'none' else {'status': 'not_requested'}
            if settings(store)[0] != 'none' and not immutable['confirmed']:
                raise Failure('Provider did not confirm required object immutability', 75)
            verification = remote_check(store, path, c, store.level == 'full') if store.level != 'none' else {'status': 'not_checked'}
            # Provider sidecars are immutable snapshots. Never rewrite a remote
            # metadata object merely to update later local verification state.
            sidecar = Path(str(path) + '.json')
            side_headers, side_horizon = upload_headers(store, sidecar)
            try:
                store.upload(sidecar, side_headers)
            except Failure as exc:
                # An existing immutable snapshot may predate later operational
                # annotations. Accept only identical original artifact identity.
                if exc.code != 75:
                    raise
                with tempfile.TemporaryDirectory(dir=state_dir(c)) as directory:
                    remote_sidecar = Path(directory) / sidecar.name
                    store.download(sidecar.name, remote_sidecar)
                    prior = load(remote_sidecar, 65536)
                    if prior.get('backup') != doc['backup'] or prior.get('encryption') != doc.get('encryption'):
                        raise Failure('Remote metadata identity conflict; overwrite refused', 75)
            if settings(store)[0] != 'none' and not confirmation(store, sidecar.name, side_horizon)['confirmed']:
                raise Failure('Provider did not confirm required sidecar immutability', 75)
            targets[identifier] = {'status': 'success', 'type': store.kind,
                                   'verification': verification, 'duration_seconds': now() - start,
                                   'immutability': immutable,
                                   'completed_at': iso(), 'required': store.required}
            queue_update(c, path, identifier, True)
        except Failure as exc:
            targets[identifier] = {'status': 'failed', 'error': str(exc), 'error_code': exc.code,
                                   'required': config.get('TARGET_REQUIRED', 'false') == 'true', 'type': config.get('TARGET_TYPE', 'unknown')}
            queue_update(c, path, identifier, False, str(exc), increment=False)
        event(c, 'target_replication_result', 'Storage target replication evaluated', target=identifier,
              status=targets[identifier]['status'], filename=path.name)
    successes = sum(item['status'] == 'success' for item in targets.values())
    minimum = integer(c, 'BACKUP_REQUIRED_TARGETS', 0, 0, len(targets))
    policy = successes >= minimum and all(not x['required'] or x['status'] == 'success' for x in targets.values())
    replication_status = 'success' if successes == len(targets) else ('partial' if successes else 'failed')
    report = {'backup_id': doc['backup']['id'], 'local_backup': 'success', 'replication': replication_status, 'policy_satisfied': policy,
              'required_remote_count': minimum, 'successful_remote_count': successes, 'targets': targets, 'updated_at': iso()}
    doc['replication'] = report
    atomic(str(path) + '.json', doc)
    data = state(c, 'replication.json', {'schema_version': 1, 'backups': {}})
    data['backups'][doc['backup']['id']] = report
    save_state(c, 'replication.json', data)
    metric(c, 'unifi_replication.prom', {'unifi_backup_replication_success': int(policy), 'unifi_backup_remote_targets_success': successes})
    return report

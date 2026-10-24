"""Provider immutability capability inspection and explicit new-object requests."""
import base64
import datetime as dt
import email.utils
import hashlib

from core import Failure, boolean, integer, iso, now
from storage import xml


def settings(store):
    action = store.c.get('TARGET_IMMUTABILITY', 'none')
    if action not in ('none', 'check', 'request'):
        raise Failure('TARGET_IMMUTABILITY must be none, check or request', 78)
    mode = store.c.get('TARGET_LOCK_MODE', 'GOVERNANCE' if store.kind == 's3' else 'locked')
    allowed = ('GOVERNANCE', 'COMPLIANCE') if store.kind == 's3' else ('locked', 'unlocked')
    if action != 'none' and (store.kind == 'filesystem' or mode not in allowed):
        raise Failure('Configured immutability mode is unsupported by target', 78)
    days = integer(store.c, 'TARGET_LOCK_DAYS', 30, 1, 36500)
    if action == 'request' and mode in ('COMPLIANCE', 'locked') and not boolean(store.c, 'TARGET_ALLOW_PERMANENT_LOCK', False):
        raise Failure('Permanent compliance/locked protection requires TARGET_ALLOW_PERMANENT_LOCK=true', 78)
    return action, mode, days


def capability(store):
    if store.kind == 'filesystem':
        return {'supported': False, 'reason': 'filesystem_worm_not_claimed'}
    if store.kind == 's3':
        _, body = store.request('GET', query={'object-lock': ''}, bucket=True)
        enabled = xml(body).findtext('ObjectLockEnabled') == 'Enabled'
        _, versions = store.request('GET', query={'versioning': ''}, bucket=True)
        versioning = xml(versions).findtext('Status') == 'Enabled'
        return {'supported': enabled and versioning, 'object_lock_enabled': enabled, 'versioning_enabled': versioning}
    headers, _ = store.request('HEAD', query={'restype': 'container'})
    return {'supported': headers.get('x-ms-has-immutability-policy') == 'true',
            'container_immutability': headers.get('x-ms-has-immutability-policy', 'unknown'),
            'container_legal_hold': headers.get('x-ms-has-legal-hold', 'unknown'),
            'note': 'Blob-level protection must be confirmed per object; account/versioning configuration remains administrator-managed'}


def confirmation(store, name, required_until=None):
    action, mode, days = settings(store)
    headers = store.head(name)['headers']
    if store.kind == 's3':
        actual_mode = headers.get('x-amz-object-lock-mode', '')
        raw_date = headers.get('x-amz-object-lock-retain-until-date', '')
        legal_hold = headers.get('x-amz-object-lock-legal-hold', 'unknown')
    elif store.kind == 'azure_blob':
        actual_mode = headers.get('x-ms-immutability-policy-mode', '')
        raw_date = headers.get('x-ms-immutability-policy-until-date', '')
        legal_hold = headers.get('x-ms-legal-hold', 'unknown')
    else:
        return {'confirmed': False, 'mode': 'unsupported', 'legal_hold': 'unsupported'}
    try:
        until = (dt.datetime.fromisoformat(raw_date.replace('Z', '+00:00')) if store.kind == 's3' else email.utils.parsedate_to_datetime(raw_date)).timestamp()
    except (ValueError, TypeError, OverflowError):
        until = 0
    # Existing objects must retain the original requested horizon; retries must
    # never silently shorten it or extend a lock through a policy mutation.
    threshold = required_until if required_until is not None else now()
    confirmed = actual_mode == mode and until > threshold - 2
    return {'confirmed': confirmed, 'mode': actual_mode or 'unknown', 'retain_until': iso(until) if until else None,
            'legal_hold': legal_hold, 'requested_days': days, 'action': action}


def upload_headers(store, source):
    action, mode, days = settings(store)
    if action == 'none':
        return {}, None
    caps = capability(store)
    if not caps['supported'] and (store.kind != 'azure_blob' or action != 'request'):
        raise Failure('Required immutable target capability is absent or unconfirmed', 75)
    if action != 'request':
        return {}, None
    until = int(source.stat().st_mtime) + days * 86400
    if until <= now():
        raise Failure('Configured object retention horizon has already expired', 75)
    if store.kind == 's3':
        md5 = hashlib.md5(usedforsecurity=False)
        with source.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                md5.update(chunk)
        return {'x-amz-object-lock-mode': mode, 'x-amz-object-lock-retain-until-date': iso(until),
                'content-md5': base64.b64encode(md5.digest()).decode()}, until
    return {'x-ms-immutability-policy-mode': mode,
            'x-ms-immutability-policy-until-date': email.utils.format_datetime(dt.datetime.fromtimestamp(until, dt.timezone.utc), usegmt=True)}, until

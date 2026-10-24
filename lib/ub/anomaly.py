"""Deterministic robust statistics; anomaly state never implies corruption."""
import statistics

from core import Failure, atomic, boolean, integer, iso, local_files, metadata, metric, save_state, state


def history_record(c, row):
    data = state(c, 'history.json', {'schema_version': 1, 'runs': []})
    data['runs'].append(row)
    data['runs'] = data['runs'][-integer(c, 'ANOMALY_HISTORY_LIMIT', 200, 30, 10000):]
    save_state(c, 'history.json', data)


def samples(c):
    result = []
    for path in reversed(local_files(c)):
        try:
            doc = metadata(path)
            backup, enc = doc['backup'], doc.get('encryption', {})
            plaintext = enc.get('plaintext_size_bytes')
            if not isinstance(plaintext, int) or plaintext <= 0:
                plaintext = backup['size_bytes'] if not path.name.endswith('.age') else None
            result.append({'id': backup['id'], 'filename': path.name, 'controller': backup.get('source', ''),
                           'size': plaintext, 'hash': enc.get('plaintext_sha256', backup['sha256'] if not path.name.endswith('.age') else None),
                           'timings': doc.get('timings', {})})
        except Failure:
            continue
    return result


def evaluate(rows, c, baseline=None):
    window = baseline or integer(c, 'ANOMALY_BASELINE', 20, 2, 200)
    minimum = integer(c, 'ANOMALY_MIN_SAMPLES', 5, 2, window)
    percent = integer(c, 'ANOMALY_SIZE_PERCENT', 50, 1, 10000)
    duration_percent = integer(c, 'ANOMALY_DURATION_PERCENT', 200, 1, 10000)
    identical = integer(c, 'ANOMALY_IDENTICAL_COUNT', 0, 0, 200)
    findings, deviation = [], 0.0
    if not rows:
        return {'status': 'cold_start', 'severity': 'INFO', 'findings': [], 'sample_count': 0, 'size_deviation_percent': 0}
    latest = rows[-1]
    comparable = [r for r in rows[:-1] if r['controller'] == latest['controller']][-window:]
    values = [r['size'] for r in comparable if isinstance(r.get('size'), (int, float)) and r['size'] > 0]
    cold = len(values) < minimum
    if not cold and latest.get('size'):
        median = statistics.median(values)
        mad = statistics.median(abs(v - median) for v in values)
        deviation = (latest['size'] - median) * 100 / median
        if abs(deviation) >= percent and abs(latest['size'] - median) > 6 * mad:
            findings.append({'kind': 'size_deviation', 'severity': 'WARNING', 'deviation_percent': round(deviation, 3),
                             'baseline_median_bytes': median, 'baseline_mad_bytes': mad})
    for field, actual in latest.get('timings', {}).items():
        values = [r.get('timings', {}).get(field) for r in comparable]
        values = [v for v in values if isinstance(v, (int, float)) and v > 0]
        if isinstance(actual, (int, float)) and len(values) >= minimum:
            median = statistics.median(values)
            if actual > median * (1 + duration_percent / 100):
                findings.append({'kind': 'duration_deviation', 'stage': field, 'severity': 'WARNING'})
    if identical and latest.get('hash'):
        streak = 1
        for row in reversed(comparable):
            if row.get('hash') != latest['hash']:
                break
            streak += 1
        if streak >= identical:
            findings.append({'kind': 'identical_plaintext_hashes', 'severity': 'WARNING', 'consecutive_count': streak})
    return {'status': 'anomaly' if findings else ('cold_start' if cold else 'normal'),
            'severity': 'WARNING' if findings else 'INFO', 'backup_id': latest['id'],
            'sample_count': len(values), 'findings': findings, 'size_deviation_percent': round(deviation, 3)}


def analyze(c, baseline=None, all_rows=False):
    rows = samples(c)
    reports = [evaluate(rows[:i], c, baseline) for i in range(1, len(rows) + 1)] if all_rows else [evaluate(rows, c, baseline)]
    history = state(c, 'history.json', {'runs': []})['runs']
    failures = integer(c, 'ANOMALY_FAILURE_STREAK', 3, 2, 100)
    recent = history[-failures:]
    if len(recent) == failures:
        for category in ('authentication', 'download', 'replication'):
            if all(r.get('failure_category') == category for r in recent):
                reports[-1]['findings'].append({'kind': 'repeated_' + category + '_failures', 'severity': 'WARNING', 'count': failures})
                reports[-1].update({'status': 'anomaly', 'severity': 'WARNING'})
    queue = state(c, 'retry-queue.json', {'tasks': {}})['tasks']
    if any(t['status'] == 'dead' for t in queue.values()):
        reports[-1]['findings'].append({'kind': 'replication_dead_letters', 'severity': 'WARNING'})
        reports[-1].update({'status': 'anomaly', 'severity': 'WARNING'})
    result = {'schema_version': 1, 'evaluated_at': iso(), 'results': reports}
    save_state(c, 'anomalies.json', result)
    latest = reports[-1]
    metric(c, 'unifi_anomaly.prom', {'unifi_backup_anomaly_detected': int(bool(latest['findings'])),
           'unifi_backup_anomaly_severity': int(latest['severity'] == 'WARNING'),
           'unifi_backup_size_deviation_percent': latest['size_deviation_percent']})
    return result

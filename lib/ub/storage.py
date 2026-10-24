"""Minimal shared storage interface: filesystem, Azure Blob, and S3 SigV4.

No provider SDK, redirects, remote deletion or credentials in process arguments.
"""
import base64
import datetime as dt
import hashlib
import hmac
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import urllib.parse as url
import xml.etree.ElementTree as ET

from core import Failure, OBJECT, boolean, digest, integer, private_dir, regular, safe_path


def https(value, origin=False):
    p = url.urlsplit(value)
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.query or p.fragment or any(ord(c) < 33 for c in value):
        raise Failure('Storage endpoint must be HTTPS without credentials/query/fragment', 78)
    if origin and p.path not in ('', '/'):
        raise Failure('S3 endpoint must be an HTTPS origin', 78)
    return p


def prefix(value):
    if value.startswith('/') or '\\' in value or any(x in ('.', '..') for x in value.split('/')):
        raise Failure('Unsafe storage prefix', 78)
    return value.strip('/')


def xml(data):
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper() or len(data) > 16 * 1024 * 1024:
        raise Failure('Unsafe provider XML', 65)
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        raise Failure('Invalid provider response', 65) from None
    for element in root.iter():
        element.tag = element.tag.split('}')[-1]
    return root


class Store:
    def __init__(self, identifier, c):
        self.id, self.c = identifier, c
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', identifier):
            raise Failure('Invalid target identifier', 78)
        self.kind = c.get('TARGET_TYPE', '')
        if self.kind not in ('filesystem', 's3', 'azure_blob'):
            raise Failure('TARGET_TYPE must be filesystem, s3 or azure_blob', 78)
        self.required = boolean(c, 'TARGET_REQUIRED', False)
        self.level = c.get('TARGET_VERIFY', 'metadata')
        if self.level not in ('none', 'exists', 'metadata', 'full'):
            raise Failure('TARGET_VERIFY must be none, exists, metadata or full', 78)
        self.timeout = integer(c, 'STORAGE_MAX_TIME', 1800, 1, 86400)
        self.connect = integer(c, 'STORAGE_CONNECT_TIMEOUT', 15, 1, self.timeout)
        self.maximum = integer(c, 'RESTORE_MAX_BYTES', 10737418240, 1, 1099511627776)
        self.ca = c.get('STORAGE_CA_CERT', '')
        if self.ca:
            regular(self.ca)
        if self.kind == 'filesystem':
            self.root = safe_path(c.get('FILESYSTEM_PATH', ''))
            if not self.root.is_dir() or self.root == self.root.parent:
                raise Failure('Filesystem target directory must already exist', 78)
            if boolean(c, 'FILESYSTEM_REQUIRE_MOUNT', True) and not os.path.ismount(self.root):
                raise Failure('Filesystem target is not mounted', 69)
            marker = regular(self.root / '.unifi-backup-target')
            if marker.read_text(encoding='utf-8').strip() != identifier:
                raise Failure('Filesystem target marker does not match target ID', 78)
            if os.name != 'nt' and (self.root.stat().st_mode & 0o077 or self.root.stat().st_uid != os.geteuid()):
                raise Failure('Filesystem target requires root ownership and mode 0700', 78)
        elif self.kind == 's3':
            self.endpoint = c.get('S3_ENDPOINT', '')
            self.parsed = https(self.endpoint, True)
            self.bucket = c.get('S3_BUCKET', '')
            self.region = c.get('S3_REGION', '')
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{1,61}[A-Za-z0-9]', self.bucket) or not re.fullmatch(r'[A-Za-z0-9-]+', self.region):
                raise Failure('Invalid S3 bucket or region', 78)
            self.prefix = prefix(c.get('S3_PREFIX', ''))
            self.path_style = boolean(c, 'S3_PATH_STYLE', True)
            for key in ('S3_ACCESS_KEY_ID', 'S3_SECRET_ACCESS_KEY'):
                if not c.get(key) or c[key] == 'CHANGE_ME':
                    raise Failure(f'{key} is required', 78)
        else:
            self.endpoint = c.get('AZURE_BLOB_BASE_URL', '')
            self.parsed = https(self.endpoint)
            if not self.parsed.path.strip('/') or '/' in self.parsed.path.strip('/'):
                raise Failure('Azure endpoint must identify a container', 78)
            self.prefix = prefix(c.get('AZURE_BLOB_PREFIX', ''))
            if not c.get('AZURE_BLOB_SAS_TOKEN') or c['AZURE_BLOB_SAS_TOKEN'] == 'CHANGE_ME':
                raise Failure('AZURE_BLOB_SAS_TOKEN is required', 78)

    def object_name(self, name):
        if not OBJECT.fullmatch(name):
            raise Failure('Unsafe or unmanaged object name', 65)
        return name

    def location(self, name='', query=None, bucket=False):
        query = query or {}
        key = '/'.join(x for x in (self.prefix, name) if x)
        if self.kind == 'azure_blob':
            endpoint = self.endpoint.rstrip('/')
            uri = self.parsed.path.rstrip('/')
            if name:
                encoded = '/'.join(url.quote(x, safe='-_.~') for x in key.split('/'))
                endpoint += '/' + encoded
                uri += '/' + encoded
            pairs = url.parse_qsl(self.c['AZURE_BLOB_SAS_TOKEN'].lstrip('?'), keep_blank_values=True)
            pairs += list(query.items())
            return endpoint + '?' + url.urlencode(pairs), uri, ''
        host = self.parsed.netloc
        uri = '/' + url.quote(self.bucket, safe='-_.~') if self.path_style else ''
        if not self.path_style:
            host = self.bucket + '.' + host
        uri += '/' if bucket or not name else '/' + '/'.join(url.quote(x, safe='-_.~') for x in key.split('/'))
        canonical_query = '&'.join(f'{url.quote(str(k), safe="-_.~")}={url.quote(str(v), safe="-_.~")}' for k, v in sorted(query.items()))
        return f'https://{host}{uri}' + ('?' + canonical_query if canonical_query else ''), uri, canonical_query

    def request(self, method, name='', query=None, source=None, output=None, headers=None, bucket=False):
        if name:
            self.object_name(name)
        address, uri, canonical_query = self.location(name, query, bucket)
        headers = dict(headers or {})
        payload_hash = digest(source) if source else hashlib.sha256(b'').hexdigest()
        if self.kind == 's3':
            host = url.urlsplit(address).netloc
            stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            headers.update({'host': host, 'x-amz-date': stamp, 'x-amz-content-sha256': payload_hash})
            if self.c.get('S3_SESSION_TOKEN'):
                headers['x-amz-security-token'] = self.c['S3_SESSION_TOKEN']
            names = ';'.join(sorted(headers))
            canonical_headers = ''.join(k + ':' + ' '.join(str(headers[k]).split()) + '\n' for k in sorted(headers))
            canonical = '\n'.join([method, uri, canonical_query, canonical_headers, names, payload_hash])
            scope = f'{stamp[:8]}/{self.region}/s3/aws4_request'
            to_sign = '\n'.join(['AWS4-HMAC-SHA256', stamp, scope, hashlib.sha256(canonical.encode()).hexdigest()])
            signing = ('AWS4' + self.c['S3_SECRET_ACCESS_KEY']).encode()
            for part in (stamp[:8], self.region, 's3', 'aws4_request'):
                signing = hmac.new(signing, part.encode(), hashlib.sha256).digest()
            signature = hmac.new(signing, to_sign.encode(), hashlib.sha256).hexdigest()
            headers['authorization'] = f'AWS4-HMAC-SHA256 Credential={self.c["S3_ACCESS_KEY_ID"]}/{scope}, SignedHeaders={names}, Signature={signature}'
        else:
            headers['x-ms-version'] = '2023-11-03'
        if any('\r' in str(v) or '\n' in str(v) for v in headers.values()):
            raise Failure('Invalid provider header value', 78)
        with tempfile.TemporaryDirectory(prefix='unifi-storage-') as temp:
            temp = Path(temp)
            config, auth, response, response_headers = [temp / n for n in ('curl', 'auth', 'response', 'headers')]
            escaped = address.replace('\\', '\\\\').replace('"', '\\"')
            if any(ord(ch) < 32 for ch in escaped):
                raise Failure('Invalid storage URL', 78)
            config.write_text(f'url = "{escaped}"\n', encoding='utf-8')
            auth.write_text(''.join(f'{k}: {v}\n' for k, v in headers.items()), encoding='utf-8')
            args = ['curl', '-q', '--silent', '--show-error', '--connect-timeout', str(self.connect), '--max-time', str(self.timeout),
                    '--proto', '=https', '--config', str(config), '--header', '@' + str(auth), '--dump-header', str(response_headers),
                    '--output', str(output or response), '--write-out', '%{http_code}']
            if method == 'HEAD':
                args += ['--head']
            else:
                args += ['--request', method]
            if method == 'GET':
                args += ['--max-filesize', str(self.maximum if output else 16 * 1024 * 1024)]
            if source:
                args += ['--upload-file', str(source)]
            if self.ca:
                args += ['--cacert', self.ca]
            try:
                process = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=self.timeout + 10, check=False)
            except (OSError, subprocess.TimeoutExpired):
                raise Failure('Storage transport unavailable or timed out', 69) from None
            if process.returncode:
                raise Failure(f'Storage transport failed (curl code {process.returncode})', 69)
            try:
                status = int(process.stdout)
            except ValueError:
                raise Failure('Invalid HTTP status from storage transport', 69) from None
            response_data = response.read_bytes() if response.exists() else b''
            returned = {}
            for line in response_headers.read_text(encoding='iso-8859-1').splitlines():
                if line.startswith('HTTP/'):
                    returned = {}
                elif ':' in line:
                    k, v = line.split(':', 1)
                    returned[k.lower()] = v.strip()
            if status >= 300:
                raise Failure(f'Storage HTTP {status}', 66 if status == 404 else 75)
            return returned, response_data

    def head(self, name):
        self.object_name(name)
        if self.kind == 'filesystem':
            p = regular(self.root / name)
            return {'size': p.stat().st_size, 'sha256': digest(p), 'headers': {}}
        h, _ = self.request('HEAD', name)
        try:
            size = int(h['content-length'])
        except (ValueError, KeyError):
            raise Failure('Storage did not return object size') from None
        key = 'x-ms-meta-sha256' if self.kind == 'azure_blob' else 'x-amz-meta-sha256'
        return {'size': size, 'sha256': h.get(key, ''), 'headers': h}

    def download(self, name, output):
        self.object_name(name)
        output = safe_path(output)
        if output.exists():
            raise Failure('Download output already exists', 73)
        if self.kind == 'filesystem':
            source = regular(self.root / name)
            if source.stat().st_size > self.maximum:
                raise Failure('Object exceeds download limit', 74)
            with output.open('xb') as dst, source.open('rb') as src:
                shutil.copyfileobj(src, dst)
        else:
            self.request('GET', name, output=output)
        os.chmod(output, 0o600)

    def upload(self, source, extra=None):
        source = regular(source, private=True)
        name = self.object_name(source.name)
        checksum = digest(source)
        if self.kind == 'filesystem':
            target = safe_path(self.root / name)
            if target.exists():
                if target.is_file() and digest(target) == checksum:
                    return 'already_present'
                raise Failure('Existing target differs; overwrite refused', 75)
            fd, temp = tempfile.mkstemp(prefix='.upload.', dir=self.root)
            try:
                with os.fdopen(fd, 'wb') as dst, source.open('rb') as src:
                    shutil.copyfileobj(src, dst)
                    dst.flush()
                    os.fsync(dst.fileno())
                os.link(temp, target)
            finally:
                Path(temp).unlink(missing_ok=True)
            return 'uploaded'
        headers = {'if-none-match': '*', 'content-type': 'application/json' if name.endswith('.json') else 'application/octet-stream'}
        if self.kind == 'azure_blob':
            headers.update({'x-ms-blob-type': 'BlockBlob', 'x-ms-meta-sha256': checksum})
        else:
            headers['x-amz-meta-sha256'] = checksum
            encryption = self.c.get('S3_SERVER_SIDE_ENCRYPTION', '')
            if encryption not in ('', 'AES256', 'aws:kms'):
                raise Failure('Invalid S3 encryption configuration', 78)
            if encryption:
                headers['x-amz-server-side-encryption'] = encryption
            if encryption == 'aws:kms':
                if not self.c.get('S3_SSE_KMS_KEY_ID'):
                    raise Failure('S3_SSE_KMS_KEY_ID is required', 78)
                headers['x-amz-server-side-encryption-aws-kms-key-id'] = self.c['S3_SSE_KMS_KEY_ID']
        headers.update(extra or {})
        try:
            self.request('PUT', name, source=source, headers=headers)
        except Failure as exc:
            if str(exc) in ('Storage HTTP 409', 'Storage HTTP 412'):
                # Crash after successful PUT is idempotent only after a full
                # re-download proves identical bytes, never on metadata alone.
                with tempfile.TemporaryDirectory() as directory:
                    candidate = Path(directory) / name
                    self.download(name, candidate)
                    if digest(candidate) == checksum:
                        return 'already_present'
            raise
        return 'uploaded'

    def listing(self):
        if self.kind == 'filesystem':
            return sorted(p.name for p in self.root.iterdir() if p.is_file() and not p.is_symlink() and OBJECT.fullmatch(p.name))
        objects, marker = [], ''
        for _ in range(1000):
            if self.kind == 's3':
                query = {'list-type': '2', 'prefix': self.prefix + '/' if self.prefix else ''}
                if marker:
                    query['continuation-token'] = marker
                _, body = self.request('GET', query=query, bucket=True)
                root = xml(body)
                keys = [x.text for x in root.findall('Contents/Key')]
                next_marker = root.findtext('NextContinuationToken', '')
                truncated = root.findtext('IsTruncated', 'false') == 'true'
                if truncated and not next_marker:
                    raise Failure('S3 listing truncated without continuation token', 74)
            else:
                query = {'restype': 'container', 'comp': 'list', 'prefix': self.prefix + '/' if self.prefix else ''}
                if marker:
                    query['marker'] = marker
                _, body = self.request('GET', query=query)
                root = xml(body)
                keys = [x.text for x in root.findall('Blobs/Blob/Name')]
                next_marker = root.findtext('NextMarker', '')
            base = self.prefix + '/' if self.prefix else ''
            for key in keys:
                if key and key.startswith(base):
                    name = key[len(base):]
                    if OBJECT.fullmatch(name):
                        objects.append(name)
            if not next_marker:
                return sorted(set(objects))
            if next_marker == marker:
                raise Failure('Provider repeated listing continuation', 74)
            marker = next_marker
        raise Failure('Provider listing exceeds safety page limit', 74)


def stores(sections):
    return [Store(k, v) for k, v in sections.items() if k != 'main']

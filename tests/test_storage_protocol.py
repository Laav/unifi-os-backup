"""Exercise real curl argument construction/SigV4 paths against a fake service."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import urllib.parse
from unittest.mock import patch

import test_engine as fixtures
from core import Failure, atomic
from storage import Store
from replication import replicate, remote_check
from recovery import restore


class ProtocolCase(unittest.TestCase):
    tearDown = fixtures.EngineCase.tearDown
    backup = fixtures.EngineCase.backup
    filesystem = fixtures.EngineCase.filesystem
    restore_args = fixtures.EngineCase.restore_args

    def setUp(self):
        fixtures.EngineCase.setUp(self)
        self.objects = {}
        self.captured = []

    def curl(self, args, **kwargs):
        def arg(flag):
            return args[args.index(flag) + 1]
        conf = Path(arg('--config')).read_text()
        address = json.loads(conf.split('=', 1)[1].strip())
        parsed = urllib.parse.urlsplit(address)
        headers = Path(arg('--header')[1:]).read_text()
        self.captured.append((args, headers, address))
        name = urllib.parse.unquote(parsed.path.rsplit('/', 1)[-1])
        method = 'HEAD' if '--head' in args else arg('--request')
        response, status = b'', 200
        extra = ''
        query = urllib.parse.parse_qs(parsed.query)
        if method == 'PUT':
            if name in self.objects:
                status = 412
            else:
                self.objects[name] = Path(arg('--upload-file')).read_bytes()
                status = 201 if 'azure' in parsed.hostname else 200
        elif method == 'HEAD':
            if name not in self.objects:
                status = 404
            else:
                content = self.objects[name]
                key = 'x-ms-meta-sha256' if 'azure' in parsed.hostname else 'x-amz-meta-sha256'
                extra = f'Content-Length: {len(content)}\r\n{key}: {hashlib.sha256(content).hexdigest()}\r\n'
        elif 'list-type' in query:
            response = ('<ListBucketResult><IsTruncated>false</IsTruncated>' + ''.join(f'<Contents><Key>production/{n}</Key></Contents>' for n in self.objects) + '</ListBucketResult>').encode()
        elif query.get('comp') == ['list']:
            response = ('<EnumerationResults><Blobs>' + ''.join(f'<Blob><Name>production/{n}</Name></Blob>' for n in self.objects) + '</Blobs><NextMarker /></EnumerationResults>').encode()
        elif name in self.objects:
            response = self.objects[name]
        else:
            status = 404
        Path(arg('--output')).write_bytes(response)
        Path(arg('--dump-header')).write_text(f'HTTP/1.1 {status} Result\r\n{extra}\r\n')
        return subprocess.CompletedProcess(args, 0, stdout=str(status).encode())

    def provider(self, kind):
        config = {'TARGET_TYPE': kind, 'TARGET_REQUIRED': 'true', 'TARGET_VERIFY': 'full'}
        if kind == 's3':
            config.update({'S3_ENDPOINT': 'https://s3.example.invalid', 'S3_BUCKET': 'bucket', 'S3_REGION': 'eu-west-1',
                           'S3_PREFIX': 'production', 'S3_ACCESS_KEY_ID': 'test-access', 'S3_SECRET_ACCESS_KEY': 'test-secret', 'S3_SESSION_TOKEN': 'test-session'})
        else:
            config.update({'AZURE_BLOB_BASE_URL': 'https://azure.example.invalid/container', 'AZURE_BLOB_PREFIX': 'production',
                           'AZURE_BLOB_SAS_TOKEN': 'sv=test&sig=private-test-signature'})
        return config

    def test_s3_and_azure_roundtrip_recovery(self):
        p = self.backup()
        for kind in ('s3', 'azure_blob'):
            with self.subTest(kind=kind):
                self.objects = {}
                config = self.provider(kind)
                store = Store('cloud', config)
                with patch('storage.subprocess.run', side_effect=self.curl):
                    report = replicate(p, {'main': self.c, 'cloud': config})
                    self.assertTrue(report['policy_satisfied'])
                    self.assertEqual(store.upload(p), 'already_present')
                    args = self.restore_args()
                    args.output = str(self.root / ('restore-' + kind))
                    restored = restore(self.c, args, store)
                    self.assertEqual(Path(restored['output_file']).read_bytes(), p.read_bytes())
                    self.objects[p.name] = b'x' * p.stat().st_size
                    with self.assertRaises(Failure):
                        remote_check(store, p, self.c, full=True)
                for args, headers, address in self.captured:
                    self.assertNotIn('test-secret', ' '.join(args))
                    self.assertNotIn('test-session', ' '.join(args))
                    self.assertNotIn('private-test-signature', ' '.join(args))
                    self.assertIn('--proto', args)
                    if 's3.' in address:
                        self.assertIn('AWS4-HMAC-SHA256', headers)

    def test_listing_pagination_and_immutability_fail_closed(self):
        store = Store('cloud', self.provider('s3'))
        with patch.object(store, 'request', side_effect=[({}, b'<ListBucketResult><IsTruncated>true</IsTruncated><NextContinuationToken>next</NextContinuationToken><Contents><Key>production/unifi_os_backup_2026-10-01_03-00-00.unifi</Key></Contents></ListBucketResult>'),
             ({}, b'<ListBucketResult><IsTruncated>false</IsTruncated><Contents><Key>production/../../unsafe</Key></Contents></ListBucketResult>')]) as req:
            self.assertEqual(len(store.listing()), 1)
            self.assertEqual(req.call_args.kwargs['query']['continuation-token'], 'next')
        config = self.provider('s3')
        config.update({'TARGET_IMMUTABILITY': 'check'})
        with patch('storage.Store.request', return_value=({}, b'<ObjectLockConfiguration><ObjectLockEnabled>Disabled</ObjectLockEnabled></ObjectLockConfiguration>')):
            report = replicate(self.backup(), {'main': self.c, 'cloud': config})
        self.assertFalse(report['policy_satisfied'])

    def test_transport_timeout_and_auth_failure(self):
        store = Store('cloud', self.provider('s3'))
        with patch('storage.subprocess.run', return_value=subprocess.CompletedProcess([], 28, stdout=b'')):
            with self.assertRaisesRegex(Failure, 'curl code 28'):
                store.head(self.backup().name)
        def unauthorized(args, **kwargs):
            output = Path(args[args.index('--output') + 1])
            output.write_bytes(b'')
            Path(args[args.index('--dump-header') + 1]).write_text('HTTP/1.1 403 Forbidden\r\n\r\n')
            return subprocess.CompletedProcess(args, 0, stdout=b'403')
        with patch('storage.subprocess.run', side_effect=unauthorized):
            with self.assertRaisesRegex(Failure, 'HTTP 403'):
                store.head(self.backup().name)


if __name__ == '__main__':
    unittest.main()

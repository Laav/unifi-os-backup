# Remote object storage

Remote storage is optional. A validated local backup is always completed first and is never deleted because an upload fails. Set one backend in `/etc/unifi-backup/unifi-backup.env`:

```bash
REMOTE_STORAGE_TYPE="azure_blob"  # none, azure_blob, or s3
STORAGE_CONFIG_FILE="/etc/unifi-backup/storage.env"
REMOTE_UPLOAD_REQUIRED="true"
```

Azure Blob Storage and S3 are different protocols. Azure Blob is the preferred backend for Azure environments; it is not described as “S3-compatible” by this project. The uploader implements Azure `Put Blob` and S3 Signature Version 4 separately, using only curl and Python's standard library.

The backup object is uploaded first. Its final `.unifi.json` metadata sidecar is uploaded after the optional email step. Existing object names are protected with `If-None-Match: *`; the tool never silently overwrites an object.

## Azure Blob Storage

Copy and protect the example:

```bash
sudo install -o root -g root -m 0600 \
  /opt/unifi-os-backup/config/storage.env.example \
  /etc/unifi-backup/storage.env
sudoedit /etc/unifi-backup/storage.env
```

Configure the container URL, SAS, and optional prefix:

```bash
AZURE_BLOB_BASE_URL="https://storageaccount.example.invalid/unifi-backups"
AZURE_BLOB_SAS_TOKEN="REPLACE_WITH_SAS_QUERY_STRING"
AZURE_BLOB_PREFIX="production/controller-01"
```

Use a short-lived, container-scoped **user delegation SAS** where operationally possible. Grant only the create/write permissions required by `Put Blob`, use HTTPS, set an expiry, and rotate it. Microsoft recommends Microsoft Entra authorization over account keys; this initial implementation supports SAS so it also works from a non-Azure Linux server without an Azure SDK. It never accepts a storage account key.

Azure receives:

- `x-ms-blob-type: BlockBlob`;
- `If-None-Match: *` to prevent replacement;
- the SHA256 as blob metadata;
- the backup or metadata file as the request body.

See Microsoft's [Put Blob REST documentation](https://learn.microsoft.com/rest/api/storageservices/put-blob) and [user delegation SAS guidance](https://learn.microsoft.com/azure/storage/blobs/storage-blob-user-delegation-sas-create-cli).

## S3 and S3-compatible storage

Configure the endpoint, region, bucket, and a key restricted to one prefix:

```bash
S3_ENDPOINT="https://s3.example.invalid"
S3_REGION="us-east-1"
S3_BUCKET="unifi-os-backups"
S3_PREFIX="production/controller-01"
S3_ACCESS_KEY_ID="REPLACE_ME"
S3_SECRET_ACCESS_KEY="REPLACE_ME"
S3_SESSION_TOKEN=""
S3_PATH_STYLE="true"
```

`S3_PATH_STYLE=true` is appropriate for MinIO and many compatible services. Set it to `false` only when the provider requires virtual-host style and the bucket name is valid in DNS.

The least-privilege policy normally needs `s3:PutObject` only for the selected prefix. The tool does not list or delete remote objects. A conceptual AWS policy is:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": "s3:PutObject",
    "Resource": "arn:aws:s3:::unifi-os-backups/production/controller-01/*"
  }]
}
```

Provider-side encryption can be requested with:

```bash
S3_SERVER_SIDE_ENCRYPTION="AES256"
S3_SSE_KMS_KEY_ID=""
```

For AWS KMS use `aws:kms`, supply `S3_SSE_KMS_KEY_ID`, and grant the corresponding narrowly scoped KMS permissions. Bucket policies can also enforce encryption. Signature Version 4 covers the payload hash, object metadata, session token, and encryption headers. See AWS's [header-based Signature Version 4 documentation](https://docs.aws.amazon.com/AmazonS3/latest/API/sig-v4-header-based-auth.html).

Compatibility varies between S3 implementations. Test conditional PUT, path style, TLS, Signature V4, metadata, and encryption against the exact product/version before production use.

## Remote retention

Use Azure Blob lifecycle management or the S3 provider's lifecycle rules for remote retention. Keeping deletion out of this service has two advantages:

- the upload identity does not need destructive delete permissions;
- a local configuration error cannot erase the offsite copy.

Configure remote lifecycle independently from local retention. Consider immutable/versioned storage and a separate administrative identity for lifecycle changes.

## Failure behavior

With `REMOTE_UPLOAD_REQUIRED="true"`, an upload failure exits with code 75 after retaining the local backup. With `false`, the run continues, but metadata, JSON logs, the status file, and monitoring metrics report the remote failure.

When client-side age encryption is enabled, the uploader receives the `.unifi.age` artifact rather than plaintext. Provider-side encryption can still be used as a separate control. See [ENCRYPTION.md](ENCRYPTION.md).

SAS tokens, S3 secret keys, session tokens, authorization signatures, and signed URLs are stored only in root-owned configuration or mode-0600 temporary files. They are not placed on curl's command line or in logs.

# Optional Microsoft Graph email

The local backup path is independent of Microsoft 365. Leave `ENABLE_EMAIL="false"` unless email is explicitly required.

## App registration

1. Create a single-tenant Microsoft Entra application and a service principal.
2. Create a client secret with the shortest practical lifetime and arrange rotation before expiry.
3. Choose exactly one authorization model below.

Microsoft documents `Mail.Send` as the least-privileged application permission for `POST /users/{id}/sendMail`, but there are now two distinct places it can be granted:

### Recommended for new, mailbox-scoped deployments: Exchange RBAC for Applications

Create the Exchange Online service-principal pointer, a resource scope containing only the sender mailbox, and a scoped `Application Mail.Send` role assignment. In this model, **do not also grant/admin-consent the unscoped Microsoft Graph `Mail.Send` application permission in Entra**. Microsoft states that Entra grants and Exchange RBAC grants are additive; leaving the Entra grant in place defeats the RBAC mailbox scope.

Follow Microsoft's current [RBAC for Applications](https://learn.microsoft.com/exchange/permissions-exo/application-rbac) procedure and validate with `Test-ServicePrincipalAuthorization`, then perform a real negative Graph test against an out-of-scope mailbox. The test cmdlet itself does not account for independent Entra grants, so also inspect the app registration.

### Traditional tenant-wide model

Add Microsoft Graph **Application** permission `Mail.Send` (not delegated) in Entra and grant Admin Consent. This is the classic model requested by many existing deployments, but it is tenant-wide by default: the app can send as any mailbox. Microsoft's legacy Application Access Policies can constrain Entra-granted mail permissions, but Microsoft says those policies have been replaced by RBAC for Applications and should not be selected for a new deployment. Existing environments should plan a migration to scoped Exchange RBAC and remove the unscoped Entra consent after the scoped assignment is proven.

Do not combine unscoped Entra `Mail.Send` consent with a scoped Exchange RBAC `Application Mail.Send` assignment and assume the latter narrows the former; it does not.

## Configuration

Edit `/etc/unifi-backup/graph.env`:

```bash
TENANT_ID="00000000-0000-0000-0000-000000000000"
CLIENT_ID="11111111-1111-1111-1111-111111111111"
GRAPH_AUTH_METHOD="client_secret"
CLIENT_SECRET="replace-with-a-real-secret"
MAIL_FROM="unifi-backup@example.com"
MAIL_TO="operations@example.com"
GRAPH_SIMPLE_ATTACHMENT_MAX_BYTES="2800000"
```

Then set `ENABLE_EMAIL="true"` in `unifi-backup.env`. Keep both files root:root 0600.

The OAuth request uses the v2 token endpoint, client credentials grant, and `https://graph.microsoft.com/.default`. The secret is URL-encoded by Python and streamed to curl via stdin. The access token is held briefly in a root-only temporary header file, never in a process argument or log, and removed by a trap. `GRAPH_AUTH_METHOD` makes the authentication strategy explicit; only `client_secret` is accepted in 1.2.0. A later certificate implementation can add a separate assertion generator without changing backup or mail-payload logic.

## Attachment limit

Microsoft's current guidance uses a direct file attachment only for files **under 3 MB**. Files from 3 MB through 150 MB use an Outlook message attachment upload session. That flow first creates a draft and requires `Mail.ReadWrite`, which is materially broader than this project's intentionally minimal `Mail.Send` design.

This implementation therefore:

- defaults to a conservative 2,800,000-byte ceiling;
- refuses values above 3,000,000;
- detects size before requesting a token or building base64;
- leaves the local backup untouched and exits nonzero when too large;
- builds normal JSON in a mode-0600 payload file and sends it with `--data-binary @file`, never as a giant shell argument.

When a managed metadata sidecar is available, its small JSON file is attached separately and the backup ID, encryption state, and remote-storage status appear in the HTML body. The `.unifi` or `.unifi.age` size ceiling remains the controlling limit; metadata is independently limited to 65,536 bytes.

For larger backups, prefer a dedicated encrypted backup store and email only a notification. A future upload-session module would need a separate security review, draft-message lifecycle, chunking/retry logic, and `Mail.ReadWrite`; simply posting a huge `sendMail` body is unsupported.

## Delivery semantics

Graph returns HTTP 202 when the request is accepted. This does not prove final delivery; Exchange transport rules, throttling, recipient limits, or later processing can still reject it. Monitor the sending mailbox and Microsoft 365 message trace where delivery assurance matters.

Microsoft references:

- [Client credentials flow](https://learn.microsoft.com/entra/identity-platform/v2-oauth2-client-creds-grant-flow)
- [user: sendMail](https://learn.microsoft.com/graph/api/user-sendmail?view=graph-rest-1.0)
- [Large Outlook attachments](https://learn.microsoft.com/graph/outlook-large-attachments)

# Dedicated UniFi service account

Use a separate local administrative identity named `uni-bck` by default. Do not reuse an owner's personal account, a daily administrator account, or an account whose unattended login conflicts with MFA policy.

## Create it

UniFi menu labels differ across UniFi OS Server/Network releases:

1. Open the UniFi instance through its local HTTPS controlplane URL and sign in as the Owner or an administrator permitted to manage admins.
2. Open the local administration page. In current Ubiquiti guidance this is exposed through **People / New Admin** for managed sites, or **Admins** and the `+` action for local-only management. Some releases place it under **Settings > System > Administration** or **Control Plane > Admins & Users**.
3. Create a local-only admin named `uni-bck`. Do not enable remote management for this identity unless your tested release requires it and the security consequence is accepted.
4. Generate a long unique password, store it only in the root-owned configuration file, and record its rotation owner/expiry in the organization's secret-management process.
5. Assign the narrowest available role and application/site scope that can create and download a **System Config Backup** from **Settings > Control Plane > Backups**.
6. Sign out of the administrative account and verify the new identity locally. Then run `sudo unifi-backup-check --live` and one real `sudo systemctl start unifi-backup.service`.

Ubiquiti documents that Super Admin is highly privileged and comparable to Owner for many operations. It does not publish a stable, fine-grained permission specifically for the undocumented backup-download endpoint. Start with the least-privileged role presented by your installed release and test it. Escalate to Super Admin only when a lower role demonstrably returns 403 or cannot create the System Config Backup, and document that exception. Re-test after every upgrade because both roles and endpoints may change.

Disable interactive/daily use, do not share the password, and monitor login activity if the installed version exposes it. Disable or delete the identity when this automation is retired.

Official guidance:

- [Adding Admins in UniFi](https://help.ui.com/hc/en-us/articles/28692158912279-Adding-Admins-in-UniFi)
- [UniFi Roles Explained](https://help.ui.com/hc/en-us/articles/1500011491541-UniFi-Roles-Explained-Admins-and-Users)
- [UniFi Local Management](https://help.ui.com/hc/en-us/articles/28457353760919-UniFi-Local-Management)

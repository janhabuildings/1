# Shared company workspace

The deployment hosts one company. Users have individual revocable access keys and either the `admin` or `inspector` role. No paid identity provider or custom domain is required.

## Start using it

1. Sign into the website using the existing owner credential. Keep that credential private; it is the owner/recovery administrator, not a team login.
2. Expand **Company users and inspection assignments**. Create each person with their name, email and role. An email identifies the account; this version does not send invitations or use email/password authentication.
3. Copy the generated personal access key and give it privately to that person. It is displayed once. The database stores its SHA-256 hash, never the raw key. Replacing a key invalidates the old one; deactivating an account denies all its API access.
4. Save/open an inspection, select its assignees and save assignments. Existing inspections remain visible to administrators and become available to inspectors when assigned. Inspectors' new inspections are assigned to themselves automatically.
5. On the web, enter the personal key in **Sign in to your company workspace**. On an updated iPhone build, enter it under **Settings → Company workspace → Save connection**. Use the website for user administration and assignments.

Do not distribute the owner key. Use the updated native build before switching accounts on a shared phone. No accounts are created automatically and no credentials are emailed by this app.

## Access rules

- Admins see all inspections, manage accounts and assignments, manage templates and import workspace-wide saved-row history.
- Inspectors can create inspections and read/edit/delete assigned inspections, including their evidence and generated reports. Guessing another inspection, photo or artifact ID does not grant access.
- Templates, reference libraries and reusable attendee/company/open-item suggestions belong to the company workspace. Suggestions can be maintained by company users; full history import is admin-only.
- Stamp originals are private to the uploading account, including against other admins. Existing stamp originals belong to the recovery owner. Applying a stamp still requires explicit report review and the existing matching PE-attendee check. Shared generated reports may themselves include an approved stamp image.
- Account creation, key replacement, activation/deactivation and assignment changes have a metadata-only audit log at `/workspace/audit`. Raw keys are not logged there. Account roles are chosen at creation.
- Access is checked server-side on every API request. Account changes and permissions are serialized with other storage operations and mirrored to Cloudflare along with the existing records.

Inspection updates carry a revision. New web/iPhone clients reject stale edits with HTTP 409 rather than silently overwrite another person's work. Preserve a JSON backup and reopen the latest record before merging edits. Legacy owner-token clients remain compatible and can omit revisions; update them before relying on concurrent editing. This is not simultaneous live editing.

## iPhone accounts and offline data

Each account/server combination has its own protected local cache, media, exports and saved stamp directory. Replacing the entire store on sign-in also binds unfinished work to the previous account's credentials and directory. Switching back reopens that account's local drafts. The existing owner profile on the default backend retains its original directory for migration.

Signing out hides that profile and opens an empty signed-out profile; it does not delete saved drafts. Offline access to data already downloaded cannot be remotely revoked until the device reconnects. Removed assignments are returned separately from deletion tombstones so the new app clears revoked cached records without preventing later reassignment. Administrators should deactivate lost-device credentials and follow their device-security process.

## Hosting

Render still runs one instance of the application; Cloudflare D1/R2 provide durable storage. Account and assignment tables use the existing private gateway and need no Worker schema deployment. Do not scale the service to multiple instances without reviewing its existing cloud-conflict behavior. Free-tier quotas and Render idle sleep still apply. No hosting-plan upgrade, domain purchase or email service is configured by this change.

# JBI private Cloudflare storage

This gateway connects the existing Render app to the already-created D1 database and private R2 bucket. It does not change Render's free plan. The configured Account ID, Database ID, and bucket name are resource identifiers, not credentials.

## Deploy the gateway first

1. In Cloudflare, open **Workers & Pages → Create application → Import a repository** (the wording can also be **Connect to Git**).
2. Connect GitHub and select **janhabuildings/1**.
3. Select production branch **codex/cloudflare-durable-storage** while this change is awaiting activation.
4. Set **Root directory** to `cloudflare/storage`. Leave the build command empty and use deploy command `npx wrangler deploy`.
5. Deploy the Worker named `jbi-inspection-storage`. The Wrangler configuration binds the existing D1 database as `DB` and R2 bucket as `FILES`. Keep Workers on the Free plan and keep R2 public access disabled.
6. Open the Worker's **Settings → Variables and Secrets → Add**. Select **Secret**, name it `STORAGE_TOKEN`, and copy the existing `INSPECTION_API_TOKEN` value from **Render → jbi-inspections → Environment** into it. Save/deploy the secret. Do not send this value in chat or commit it to GitHub.
7. Copy the actual `https://jbi-inspection-storage.<your-subdomain>.workers.dev` URL. Share that URL with the assistant; it is not a credential.

If an earlier build shows `main` and fails with `root directory not found`, it used the wrong branch. After saving the production branch and root settings above, a new push to the configured production branch starts a fresh build. Retrying an old build may reuse its original branch; check the branch label on the new build.

A browser visit without authentication returns an authentication/configuration error. That is intentional, not a public report browser. With no STORAGE_TOKEN configured, every request returns 503 and no storage data is exposed.

## Activate the Render connection after the gateway is ready

Back up any currently visible reports, JSON drafts, photos, stamps and custom templates before redeploying the free Render service. Its old temporary filesystem is not guaranteed to survive deployment. The integration cannot recover files that were already lost.

When the gateway has been deployed and its secret saved:

1. Merge the prepared backend integration.
2. Add Render environment variable `INSPECTION_CLOUD_URL` containing the actual Worker URL. Do not include quotes or `/status`.
3. Render reuses `INSPECTION_API_TOKEN` for server-to-server authentication. If an independent storage secret is preferred, set the same independent value in `INSPECTION_CLOUD_TOKEN` on Render and `STORAGE_TOKEN` on the Worker instead. Keep both secret values outside chat and source control.
4. Redeploy. Startup verifies the gateway, restores saved metadata and uploads any available local state. Bad credentials or unavailable cloud storage cause startup/save errors; the app does not silently fall back to temporary saving.
5. After signing in, the workspace must show **Cloud saving connected**. Edit an inspection and wait for **Saved**. Then reopen it in another browser/session.
6. Save a photo and generate a report, restart Render, and verify that the record, photo, generated file and attendees can all be reopened. This is the final live acceptance check.

Until INSPECTION_CLOUD_URL is set, the app continues using its existing temporary storage. Creating the Cloudflare resources or deploying only the Worker does not activate cloud saving.

## Behavior and limits

- D1 stores inspection records, evidence metadata, generated-file metadata, reusable stamps/templates and deletion markers. R2 stores checksum-verified, immutable private file versions. Report generation still runs on Render.
- This adapter supports the existing **single-instance, single-operator** backend. It is not a horizontally scalable multi-writer database adapter. It detects a stale server revision and rejects its write instead of overwriting newer cloud state. Simultaneous edits of one inspection in clients are not merged.
- Each acknowledged mutation commits its durable metadata after file uploads. Saves that cannot be confirmed return an error and leave the browser draft unsaved. Automatic saving retries network failures; revision conflicts require refreshing after backing up the draft.
- Templates and stamps restore eagerly. Photos and report downloads restore lazily, so a large photo collection does not have to download every time Render wakes. Unchanged local files are not re-uploaded or rehashed on every edit.
- Removing an inspection/photo removes its durable references and queues unreferenced R2 content for deletion. Cleanup runs during saving and retries daily through the Worker. Identical content shared by another record is retained until its last reference is removed.
- Local-only reference-code indexes are not copied to Cloudflare. Re-ingest any separately managed indexes after a new Render deployment.
- Metadata change sets are bounded to 1.5 MB. Files are bounded to the app's existing 40 MB upload ceiling. Very large initial migrations need a separate staged importer; do not connect a large pre-existing database without checking its size.
- D1/Workers Free limits and R2's usage-based free allowance still apply. There is no account-wide $0 billing guarantee. Do not enable R2 Infrequent Access for this bucket.
- Keep independent backups. Durable storage is not a separate backup copy, and deleted photos remain in already-generated documents until those documents are also deleted or regenerated.

## Local verification

Run from the repository root:

```sh
node cloudflare/storage/worker.test.mjs
python -m unittest discover -s tests -p test_cloud_storage.py -v
python -m unittest discover -s tests -p test_cloud_autosave.py -v
```

Gateway SQL is tested against SQLite and the backend against an isolated HTTP gateway fixture. These checks do not replace the live Cloudflare/Render acceptance check after account-side deployment.

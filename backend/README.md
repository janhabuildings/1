# Inspection backend

FastAPI + SQLite + a private filesystem; no Supabase dependency. Supports single-operator inspection records, retry-safe uploads, optional AI suggestions, portable keyword/vector references and the existing template-preserving report generator. It has no mail-send, WhatsApp-read or phone-call recording endpoints.

## Run locally

From the repository root:

```sh
python -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt
.venv/bin/python scripts/build_plugin.py
```

Configure `INSPECTION_API_TOKEN` with a strong random value using your secure environment settings. Choose a persistent `INSPECTION_DATA_DIR`; `/tmp/jbi-inspections` is only a development default. See `.env.example` for variable names; this app does not automatically load an `.env` file. Never commit credentials. Configure the same token in the iPhone Settings screen. Only `/health` is usable without authentication; data routes require a bearer token, and fail closed if no token is configured.

Install LibreOffice Writer with its normal verified platform packages. This cloud machine already has a local converter; use `DSENY_OFFICE_BIN=/workspace/1/.tools/bin/libreoffice` when running the backend here. A Render container installs LibreOffice from signed Debian packages.

```sh
.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --no-access-log
.venv/bin/python scripts/smoke_backend.py
.venv/bin/python -m unittest discover -s tests -v
```

The iPhone requires an HTTPS backend URL (simulator localhost HTTP is allowed for development). A physical phone cannot reach your Mac/server through its own localhost. Use a reachable HTTPS deployment. Client/server tokens are single-operator credentials, not a complete multi-user identity/authorization solution.

## Render deployment

`render.yaml` now selects Render’s **free plan**, uses `backend/Dockerfile`, generates an API token and stores test data in `/tmp/jbi-inspections`. There is no persistent disk. Code is on GitHub; no Render service has been deployed from this session. Select the `main` branch and verify the plan says Free before deployment.

**Test storage is temporary:** SQLite records, uploaded photos/audio, imported code indexes and generated reports can disappear on restart or redeployment. Keep originals on your phone/computer and download reports promptly. The free service may sleep while idle, and startup/PDF conversion can be slow or exceed free-plan resource limits. Do not rely on it as the only copy of client records. AI API usage is billed separately. For ongoing use, add durable storage (a paid disk or an external storage/database service) and a backup/retention plan. The optional local Docker volume example below remains useful for durable local development; it is not included in the free Render blueprint.

Docker commands for a local validation build:

```sh
docker build -f backend/Dockerfile -t jbi-inspections:local .
# Supply INSPECTION_API_TOKEN through your shell/secret environment; no literal secret is needed here.
docker run --rm -p 8000:8000 --env INSPECTION_API_TOKEN \
  --mount type=volume,src=jbi-data,dst=/var/data jbi-inspections:local
```

The non-root image uses UID 10001. Ensure the mounted data volume is writable by that user. Font substitutions remain a separate rendering issue even when the container starts successfully.

## Optional AI

Set `AI_API_KEY` securely on the backend to enable OpenAI analysis and embeddings. Defaults are `AI_MODEL=gpt-4.1-mini` and `EMBEDDING_MODEL=text-embedding-3-small`; select models available to your account. The app shows a confirmation before submitting calendar text, notes, transcript and up to six selected photos. It does not automatically send recorded audio. No provider requests or billable AI operations were performed in this development session.

Suggestions are schema-checked and returned separately from the inspection; they never automatically mark an inspection clear, modify findings or accept unsupported code citations. Analysis retrieves date-appropriate reviewed sections using keyword matching, sends those source records with the notes, and accepts suggested references only when their IDs and exact excerpts match the retrieved records. Unsupported citations and unrecognized suggested photo IDs are removed. Applicability still requires inspector review. The inspector must review observations/corrective actions. If no provider is configured the API returns a clear unavailable response; manual workflows continue.

## Portable OSHA / NYC DOB / NYC SCA reference library

The code index starts **empty**. No authoritative corpus was uploaded or approved in this task, and the existing JBI drawing-review repository has not been provided. This implementation can hold vectors in SQLite; it is not a claim to reuse an unseen app's actual storage.

1. Create `code_library/sections.json` using `sections.example.json` as the shape, replacing all placeholders with permitted authoritative text. Keep section numbers, exceptions, agency, source HTTPS URL and actual effective dates. Explicitly mark a section `verified: true` only after reviewing its source and applicability. Legal text, SCA contract requirements and guidance must remain distinguishable in your titles/text; the system does not decide their legal equivalence.
2. Import keyword-searchable sections:

   ```sh
   .venv/bin/python -m backend.ingest_codes code_library/sections.json --require-verified
   ```

3. Add `--embed` to generate embeddings through the configured provider. It requires a real key and makes billable requests. Embedding vectors, model and text checksum are stored alongside the section; original text and source metadata remain retrievable.
4. App keyword search works without an AI key. Enabling semantic search sends the query to the embedding provider, then combines cosine similarity with keyword matching. Only matching embedding models/dimensions are compared. Retrieval excludes unverified sections and those outside the inspection date. Results retain source URLs and effective dates; they are references, not automatic compliance determinations.
5. `.github/workflows/build-code-index.yml` provides an explicit, manual GitHub Actions build. It requires the reviewed corpus in the private repo and `AI_API_KEY` in Actions Secrets. It fails rather than publishing an empty/unreviewed corpus. It creates a portable SQLite artifact; it does **not** deploy or overwrite the live backend database.
6. After review, merge only its code records into the running service's configured data directory:

   ```sh
   .venv/bin/python -m backend.ingest_codes --index /path/to/reviewed-index.sqlite3 --require-verified
   ```

   The import validates text hashes and source/date metadata. It does not replace inspections/media tables. Back up the live database before administrative corpus changes. A growing corpus may justify FTS/vector extensions or an external index later; the initial implementation compares reviewed vectors in-process and is intended for a modest reference library.

## API overview

- `GET /health`, authenticated `GET /capabilities`
- `POST/GET /inspections`, `GET/PUT /inspections/{uuid}` (PUT is retry-safe creation/update)
- `POST /calendar/extract` returns unconfirmed labeled candidates, not inspection results
- `POST/GET /inspections/{id}/media`, authenticated `GET/PUT /media/{id}`
- `POST /inspections/{id}/analyze` with explicit consent
- `POST /codes/search` with query, inspection date and semantic flag
- `POST /inspections/{id}/reports`, authenticated `GET /artifacts/{id}`

Media upload uses raw request bytes with the correct Content-Type and optional retry-safe X-Asset-ID. File signatures/types and a 40 MB limit are checked. Artifact IDs resolve to protected files, never public filesystem links. This API intentionally does not create Gmail drafts; native iOS Mail handles user-controlled composition, while the earlier plugin still provides a host-specific Gmail handoff.

### Verified cloud-container build

The Docker image was built and exercised successfully with a 512 MB memory limit, a fresh persistent volume and UID 10001. It created an authenticated inspection, generated actual scaffold HTML and shed PDF reports and returned the PDF through the protected endpoint. Initial startup failed because copied source files were unreadable by the non-root user; the image now sets source read/traverse permissions explicitly. The failure was not an out-of-memory kill. This is container validation, not a Render deployment.

The cloud execution machine uses a proxy that Docker did not initially resolve/trust. `scripts/build_container.py --environment-proxy --docker-config /tmp/jbi-docker-config` supplies the existing proxy hostname mapping and forwards the current public CA bundle as an ephemeral BuildKit secret. It preserves TLS, Debian package signatures and artifact verification; the temporary CA configuration is removed and the CA bundle is not baked into the runtime image. No proxy credentials are printed or stored by the script. Ordinary Render/public-network builds need no such flags. Re-run `scripts/smoke_container.py` after a local build; the cloud sandbox may need the same `--docker-config` option because its normal home directory is read-only.

### Staging source PDFs

Install `backend/requirements-ingest.txt` and run:

```sh
python -m backend.stage_pdf /path/to/code.pdf --output /new/private/staging-directory
```

This preserves `source.pdf` with SHA-256, complete extracted text per PDF page, numbered section records, parent-section references and bounded retrieval chunks with exact character/page spans. It does not read document instructions as commands, assign guessed effective dates, declare source verification or call an embedding API. Tables/figures and cross-page conditions still require visual comparison. Review JSON is deliberately distinct from the approved `ingest_codes` format; do not rename it and mark everything verified. Approving chunks requires source URL/date provenance and contextual retrieval of complete provisions, exceptions and parents. The current active search index is not modified by staging.


### Browser workspace for Windows testing

Open the service root URL after deployment. Public static UI files contain no private inspection data or credentials. Connect using `INSPECTION_API_TOKEN` from Render's Environment settings; the token is sent as a same-origin bearer header, never a query string, cookie, localStorage or sessionStorage entry. The workspace is cleared on disconnect. Authenticated data/download routes still require the token, and responses use no-store headers. External scripts/CDNs are not used; the content security policy disallows script evaluation and embedding by other sites.

Workflow: connect → create/open an inspection → paste calendar text and review candidates → enter actual attendees → upload and label evidence → add scaffold/shed report facts and explicit outcomes → generate → download DOCX, PDF, HTML or unsent EML. Existing transcripts can be imported as UTF-8 TXT. Optional AI analysis sends only consented text and selected photos, with at most six images. It does not transcribe audio recordings. The reference tab clearly reports an empty library until reviewed sections are ingested.

This page is a testing UI, not a native iOS simulator. Report-formatting/signature review, temporary free-tier storage and external AI configuration limits still apply. Email files preserve MIME/HTML/attachments for local review; they are not automatically inserted into Gmail or Outlook.

Browser checks use Playwright and Chromium. `backend/requirements-dev.txt` includes Playwright; install its Chromium browser with `playwright install chromium` where a system Chromium is not available. Browser tests exercise wrong-token rejection, nonpersistent credentials, calendar candidate confirmation without inferred outcomes, actual photo upload, both report workflows and a real PDF download. They use temporary local test data, not the deployed Render API token.

### Photo findings grounded in uploaded DOB/SCA vectors

`POST /inspections/{id}/analyze` now uses a two-pass review workflow by default (`use_draft_references: true`). After explicit consent, it observes the selected photos and notes, embeds up to six distinct observed-condition queries, retrieves up to two chunks per query from each uploaded draft library, and supplies those references to a final photo review. A second vision pass can check the photos against the retrieved excerpts. Draft citations have namespaced IDs, exact text validation, agency, source document/hash, physical PDF pages and explicit unverified status. Unknown photo IDs and unsupported/invented quotations are removed. Retrieval failures produce an explicit warning rather than invented citations. `use_draft_references: false` retains the previous reviewed-reference-only single-pass behavior.

This requires the existing Render `AI_API_KEY` and matching `text-embedding-3-small` query model. No new embedding of the full manuals is needed. Queries are derived from the initial observations, so an unlabeled photograph can retrieve relevant clauses. The model still cannot establish hidden connections, dimensions, measurements, applicable code edition, or No OIs. Results remain suggestions and are never written to inspection/report facts by this endpoint. The operator must confirm or edit an open item. Draft sources are not promoted into the date-verified library.

Tests use controlled AI responses and real stored vectors to exercise retrieval, photo ownership/identity, exact quote checks and report non-mutation. They do not measure the real model's accuracy on field photos. Validate on representative inspection photographs before relying on suggestions.

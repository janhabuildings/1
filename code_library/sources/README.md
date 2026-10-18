# NYC Chapter 33 source and draft embeddings

`nyc-2022-chapter33.pdf` is the user's uploaded 137-page PDF, not a freshly verified official download.
SHA-256: `d7d4e9d4403d0cca91f67f811cefa355ef2888e62c26b1898e0dc16cfbe165fe`.

To generate vectors without a paid Render service:

1. In GitHub repository Settings → Secrets and variables → Actions, add a repository secret named `AI_API_KEY` containing your OpenAI API key. ChatGPT subscriptions do not include API usage; this uses your API account's billing.
2. Open Actions → **Embed NYC Chapter 33 (draft)** → Run workflow on `main`.
3. Download `nyc-chapter33-draft-vectors` from the completed run. Keep a permanent copy: artifacts expire after 30 days and caches can be evicted.

The job uses `text-embedding-3-small`, batches requests and reuses cached vectors when source, parser and model match. A failed job uploads its checkpoint; download it to resume locally if the cache was not saved. The vector JSON retains the original chunk text, section IDs, parent sections, PDF page references, source hash and source review flags. The artifact is **not** installed in the app's active reference library.

Activation still requires source provenance, amendment/effective-date review and visual checks of extraction (particularly tables and figures). The uploaded PDF includes amendment notes; do not assign one assumed effective date to the whole chapter. Draft vectors alone do not establish applicability or compliance. The existing reviewed-index workflow remains separate.

Local equivalent (with `AI_API_KEY` supplied securely in the environment):

```sh
python -m backend.stage_pdf code_library/sources/nyc-2022-chapter33.pdf --output /tmp/chapter33
python -m backend.embed_staged /tmp/chapter33 /tmp/chapter33-vectors/chapter33.draft.json
```

Repeat the second command with the same file to resume. No inspection records, photos, email data or credentials are sent by this job; it embeds only the uploaded code text.

## Bundled Render preview

GitHub Actions run `39091244250` completed successfully. All 951 vectors (1536 dimensions) were validated against the extracted chunks and source PDF hash. Its compressed vector artifact and checksum are bundled in `backend/data/`, which the Docker image includes. This keeps the index available across Render Free redeploys without runtime artifact downloads or persistent disks.

In the browser Code reference library, select **Search uploaded NYC Chapter 33 draft (unreviewed)**. Keyword search works immediately. Semantic search additionally requires `AI_API_KEY` in Render Environment settings, with the default `text-embedding-3-small` model. The Actions secret is not automatically shared with Render. Only the query is sent for search embedding; stored vectors are reused.

The authenticated `/codes/draft/search` endpoint returns section text, parent references and PDF page numbers with explicit draft flags. It does not filter by effective date, populate the reviewed SQLite index, or feed draft references into report analysis.

## SCA Safety Manual upload

`sca-safety-manual-january-2026.pdf` is the uploaded 155-page manual (SHA-256 `c8dc63a3204e39ec29cf6fe00eb1f5d113c9f47f4fae6d0c100c2ee05e7d018d`). Its filename says January 2026; internal headers say SCA Safety Programs 2025. Source edition, effective dates and project applicability are not verified.

The dedicated `backend.stage_sca` extractor detects all 21 chapters, keeps numbered sections and continued headings, and preserves unnumbered headings within parent text. All extracted page text is retained in staging. Cover/table of contents are retained for audit and excluded from the 293 embedding chunks. PDF page numbers are physical file pages, not the printed footer page numbers.

Actions workflow **Embed SCA Safety Manual (draft)** ran successfully as run `39094105461`. Its artifact is `sca-safety-manual-draft-vectors`, retained for 30 days. All 293 vectors (1536 dimensions) were subsequently downloaded, checked against the exact extracted chunks and source PDF hash, and packaged with a checksum in `backend/data/sca-manual.draft.json.gz`. The Docker image includes the bundle, so it survives Render Free restarts. In Code reference library, select the uploaded reference draft checkbox and choose **NYC SCA Safety Manual**. The authenticated draft search accepts `library: "sca-manual"`; omitted library defaults to Chapter 33. Draft references are excluded from reviewed references and report analysis. Semantic search uses the existing Render `AI_API_KEY` and `text-embedding-3-small`; keyword search needs no API key. Do not label these provisions as NYC DOB rules or infer effective dates from the filename.

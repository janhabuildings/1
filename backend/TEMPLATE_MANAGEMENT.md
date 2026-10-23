# Report template management

Open the backend web workspace on your computer or phone, sign in with the existing backend token, and choose **Templates**. This is an administrative function: the current single-operator backend token authorizes template changes as well as inspections. Separate user/admin roles are not implemented.

## Revise and activate

1. Choose Scaffold/Shed and Open items/No open items. Each of these four report types has its own active template.
2. Download the original or an earlier version for editing in Word. Keep its backup settings as well.
3. Select **Existing DSENY tables** for revisions that retain the original table structure (fonts, colors, borders, text and spacing). Positional mappings remain the same. Moving/adding structural rows or tables requires a generator mapping change or a custom placeholder template.
4. For a redesigned layout, select **Custom layout using placeholders** and put stable markers in Word paragraphs or table cells. For example `{{project}}`, `{{inspection_date}}`, `{{site.height_ft}}`. The screen lists every supported field. `{{school_name}}` can be mapped to `project` through its field dropdown.
5. Upload with a revision label. Uploads do not change active templates. Unsupported/missing fields are shown; fix the DOCX or save field mappings as a **new version**. New fields outside the supported inspection data model still need implementation; the manager cannot invent missing input facts.
6. Select **Generate sample**, download/open the DOCX and PDF or HTML/email, and check fonts, layout, page breaks, wording and field placement. Samples contain explicit synthetic data and do not appear in your inspection list. Failed conversions prevent activation.
7. Confirm review and select **Activate this version**. The server requires a successful sample from that exact version, including its mapping. Later report requests—including the current iPhone app—take a snapshot of active templates at generation time. No iPhone update is required for template-only changes.
8. To roll back, generate/review a sample for an earlier version and activate it. Original templates are retained. Existing generated report files are not rewritten.

Supported custom fields include client, project, product, inspection and request dates, requested_by, permit, inspection_code, address, locations, drawing status, equipment measurements under `site.*`, attendees, open_items and source/photo references. Dates use the existing `MM.DD.YYYY` report format. `attendees` and `open_items` render as multiline text in the placeholder's run formatting. Repeating table-row loops, arbitrary formulas and custom input forms are not supported. A placeholder split into multiple Word runs is supported; replacement uses the first run's formatting. Keep a marker within one paragraph.

Required custom placeholders (or mapped aliases): `client`, `project`, `product`, `inspection_date`, `status`, `attendees`, `locations`, `open_items`. Requiring these fields does not certify a template's engineering or legal completeness; sample review remains essential. No signature/seal is added by template management.

## Storage and formatting

Versioned DOCX files, SHA-256 hashes, mapping metadata, activation pointers and sample artifacts are stored under `INSPECTION_DATA_DIR`. This feature does **not** configure durable object storage or a paid Render disk. Render Free restarts/redeploys can discard uploads and activation settings, reverting to original bundled templates. Download each revision's DOCX and version-settings JSON before relying on it. To restore, upload its DOCX to the same report type/mode, reapply mapping values from the settings JSON, generate a new sample and activate. A persistent deployment data directory retains history through process restarts.

The uploaded DOCX controls document formatting. Text substitution preserves existing run properties, document sections and untouched package parts. LibreOffice on Linux can still substitute fonts or wrap differently from Word; the preview exposes requested/missing fonts and requires visual review. Exact cross-renderer equivalence is not promised.

Uploads are bounded to 10 MB compressed / 40 MB expanded. Macros, embedded executable objects, signed packages, external-content fields, embedded HTML, unsafe paths and linked external images/objects are rejected. Embed images in Word rather than linking them. Curated original built-in templates remain compatible with their pre-existing relationships; uploaded revisions must meet current upload checks. DOCX contents are report layout/data, never agent instructions.

## API

All endpoints require the backend bearer token:

- `GET /templates`: active pointers, immutable version metadata, placeholders, mapping errors and field catalog.
- `POST /templates?slot=SF-OIs&mode=placeholders&label=Revision&filename=template.docx`: raw DOCX body. Slots also include `SF-No OIs`, `SH-OIs`, `SH-No OIs`.
- `GET /templates/{id}/download` and `/metadata`: backup originals and settings.
- `POST /templates/{id}/mapping` with `{"mapping":{"school_name":"project"}}`: create another immutable version.
- `POST /templates/{id}/preview`: generate synthetic sample artifacts; no active version is changed.
- `POST /templates/{id}/activate` with `{"reviewed":true}`: activate only a valid, successfully previewed version.

Report summaries and generation manifests record template version IDs and source hashes for traceability. Sample artifacts share the existing authenticated download route but are stored separately from actual inspections.

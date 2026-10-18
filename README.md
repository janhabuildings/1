# JBI Inspection App

Native iPhone app and configurable report backend for scaffold/shed field inspections. The same checked-in Xcode project is intended to be opened and compiled on a Mac; no rewrite is required. The earlier report plugin remains available as a separate integration.

## Implemented first version

- Camera/photo import, scaffold/shed labeling and location notes.
- In-person conversation recording, audio/transcript import and optional **on-device** English transcription where supported.
- Offline local inspection/media storage with manual, retry-safe backend synchronization.
- Pasted calendar extraction as unconfirmed candidates; actual attendee, drawing, dimension and result review.
- Optional AI suggestions from notes/transcript/photos, adopted only by inspector action.
- Original-template DOCX generation; OIs as inline HTML and No OIs as a DOCX/PDF plus cover email.
- Native iOS Mail composition, Messages text composition, and user-controlled sharing to WhatsApp/other installed apps. No personal inbox scraping or call-audio interception.
- Date-filtered OSHA/DOB/SCA keyword/vector reference search using **SQLite and private files**, with no Supabase requirement.
- Manual GitHub Actions embedding builds, portable index import, Dockerfile and Render deployment blueprint.

The reference corpus starts empty; the existing JBI drawing-review repository was not provided, so this is a new configurable index, not a verified reuse of that app. Direct Gmail API draft creation and Twilio/WhatsApp Business inbound messaging are not implemented in this first iOS version. The app uses Apple's Mail composer and share sheet instead.

## Browser testing on Windows

The backend now serves a browser workspace at its root URL, including `https://jbi-inspections.onrender.com/` after Render deploys this revision. Enter the service's `INSPECTION_API_TOKEN` in the password field; do not share it in chat. It stays only in page memory and is cleared on reload/disconnect, with no local/session storage. The page supports manual inspections, calendar candidates, attendee/report forms, evidence uploads, optional reviewed AI suggestions, code search and actual authenticated report downloads. It does not send mail or create mailbox drafts. Browser audio support is file upload and transcript import, not recording/transcription.

Keep original evidence locally. Free Render storage is temporary; download reports and optionally an inspection JSON backup. The JSON backup does not contain photo/audio bytes. A server restart can remove saved inspections and file links. AI features require backend configuration; the code index remains empty until approved content is ingested.

## Start here

- [iPhone / Xcode instructions](ios/README.md)
- [Backend, Render and reference-library instructions](backend/README.md)
- [Earlier plugin instructions](plugins/dseny-inspections/README.md)

Open `ios/JBIInspections.xcodeproj` in Xcode 16+, select your team and iPhone, and build. This Linux environment has no Xcode or Swift compiler: Swift syntax and project structure are checked here, not Apple SDK typechecking, simulator execution or device behavior. Camera, audio interruptions, permissions, transcription, email layout and share targets still need device tests.

## Development setup and checks

Python 3.12:

```sh
python -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt
.venv/bin/python scripts/build_plugin.py
.venv/bin/python scripts/create_xcode_project.py
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/smoke_backend.py
```

Report conversion needs LibreOffice Writer or the plugin's Windows Word renderer. The cloud environment has a trusted local LibreOffice installation; `scripts/setup_local_office.py` can reproduce it on Debian 13. Set `DSENY_OFFICE_BIN` to that converter for the backend. Backend tests run real DOCX/HTML/PDF generation and authenticated artifact downloads. The live HTTP smoke starts a temporary Uvicorn process, exercises authenticated create/read and then stops its own process.

The native structure tests parse Swift syntax, Info.plist and Xcode project references. This helps catch malformed source/package files but **does not replace an Xcode build**. Optional AI provider calls and GitHub Actions were not run against real credentials/corpora. No app/backend was deployed or published to the user's accounts.

## Document formatting boundary

Original DOCX template package parts outside the populated main document are preserved. Current Linux fonts still substitute several original faces, causing some wrapping and footer-only pages. The app does not resolve missing fonts by altering template widths or shrinking text. Final PDF/email rendering needs comparison with Word and original licensed fonts. No OIs PDFs are unsigned drafts until the inspecting PE completes the real signing/sealing process.

## Storage and access

Photos/audio, notes and exports stay in protected local app storage until explicit synchronization. The backend uses a private data directory with SQLite, media and report files, authenticated by a single-operator bearer token stored in the phone's Keychain. The Render blueprint uses the free plan for testing, with temporary server storage that can be lost on restart/redeployment. Keep original media on the phone/computer and download reports; ongoing use requires durable storage. Client credentials, live inspection content and generated files must not be committed. AI is optional and requires explicit data-sharing confirmation; it never silently processes recordings or finalizes a report.

## Existing report generator and plugin

`report_agent.py`, `templates/`, `examples/`, `plugins/dseny-inspections/`, and `scripts/build_plugin.py` are retained. The plugin archive is `dist/DSENY-Inspection-Plugin.zip`. It bundles workflow instructions, original templates and a Gmail connector declaration; it is not installed in the user's ChatGPT account by writing these files. `CHATGPT_AGENT.md` and `microsoft365-actions.json` remain legacy exploration assets, not the current iOS installation path.

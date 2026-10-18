# DSENY Inspection Reports plugin

Private plugin bundle for manually supplied calendar text, inspection photos, attendee information and confirmed scaffold/shed findings. It combines a workflow skill, the unmodified DOCX masters, Python generation tools, a Windows Word converter and a declaration of the official Gmail app.

## What is actually supported

The package uses the `.codex-plugin/plugin.json`, `skills/` and `.app.json` structure published in OpenAI's official plugin examples:

- https://github.com/openai/plugins
- https://github.com/openai/plugins/tree/main/plugins/gmail

The Gmail connector ID is the same one used by the official Gmail example. Declaring this app is a request for host-provided app availability/authentication; it is **not** a copy of credentials or proof a running session has Gmail tools.

The local CLI's `codex plugin marketplace add` and `codex plugin add` commands are documented by `--help`. These are Codex installation instructions. Availability of an import/private-marketplace flow in a particular ChatGPT product must be verified in that product; this build does not prove arbitrary local plugins can be installed in consumer ChatGPT. No private plugin was published or installed into the user's ChatGPT account.

## Install in a supported local plugin client

From the development repository:

```sh
python scripts/build_plugin.py
```

Extract `dist/DSENY-Inspection-Plugin.zip` to a persistent directory. It contains a complete local marketplace (`.agents/plugins/marketplace.json`) and `plugins/dseny-inspections/`.

For a Codex CLI client with plugin support, use the actual extracted root:

```sh
codex plugin marketplace add /absolute/path/to/extracted-marketplace
codex plugin add dseny-inspections@dseny-local
```

Open a new session in the same supported client and select the installed plugin. Complete Gmail's secure connection when the host offers it. Do not enter passwords or tokens in the plugin files or chat. Do not assume authentication from another app/session propagates. These install commands were verified against the local CLI help, not executed against the user's account/configuration.

## Runtime setup

Plugin installation does not install Python, fonts or Office. Create a venv in a user-writable state directory and install the bundled pinned dependencies. For example, on Linux/macOS:

```sh
python -m venv /your/state/dseny-venv
/your/state/dseny-venv/bin/python -m pip install -r /path/to/plugin/runtime/requirements.txt
```

Use that venv's Python for `scripts/run_report.py`. On Windows use the venv `Scripts/python.exe`. The plugin is read-only application code; keep all input/output and environments outside its installed directory. No daemon, database, API key or independent Gmail OAuth service is required by this design.

Choose a renderer:

- **Windows desktop Word:** `--renderer word`. Requires desktop Microsoft Word, the intended licensed font faces, Windows PowerShell and permission for local COM automation. The script opens DOCX read-only with macros disabled, exports PDF or filtered HTML, closes only its own document and quits the Word instance it created. This branch is not executable/tested in the Linux cloud machine. Run it on the user's Windows machine before calling it verified.
- **LibreOffice:** default `--renderer libreoffice`. Requires a trusted LibreOffice Writer installation on PATH, or `DSENY_OFFICE_BIN` pointing to its binary. The cloud development instance has a local installation at `/workspace/1/.tools/bin/libreoffice`. This development path is not portable or bundled. The repository's `scripts/setup_local_office.py` helper is available for Debian 13 environments, not Windows.

For exact appearance, the renderer must have the original font faces and be checked against Word. Font audit reports missing actual families rather than silently relabeling fallback fonts. Some template theme fonts may require additional verification; this audit alone does not establish exact appearance. HTML email rendering also varies across clients. Current cloud fonts cause awkward wrapping and can create a footer-only PDF page. Do not use the cloud-rendered PDF as a final deliverable until corrected and reviewed. Do not shrink fonts/change widths to mask this.

## Workflow

Invoke the installed plugin and say, for example:

> Prepare separate shed and scaffold reports from this calendar entry. Shed has No OIs. Scaffold has missing toeboards at 4–5 locations; install toeboards at all open platform edges. Paul G. Knecht attended as Corbex competent person and Noor Earpy attended for SCA. Create unsent drafts in my Gmail, leaving missing facts pending.

Paste the calendar text and attach photos. The skill interprets the inputs using ChatGPT's language/vision capabilities; the Python runner does not parse photos or independently reason about safety. It records confirmed facts, references and explicit pending fields. It must not infer No OIs from an empty list, use template alternatives as facts or add calendar attendees as email recipients.

The runner accepts `references/input-example.json`:

```sh
python /path/to/plugin/scripts/run_report.py request.json --output /new/output/directory --renderer libreoffice
```

Outputs:

- DOCX report using the unchanged original master, with site text replaced while retaining styles/table/section properties.
- OIs: report HTML in a local unsent EML, with numbered open items and blank certification. No report attachment.
- No OIs: DOCX, unsigned draft PDF and cover-email EML with the PDF attached.
- `gmail-handoff.json`: actual HTML, attachment filenames/paths/hashes and mailbox information for the host's Gmail tool.
- `gmail-raw.json`: base64url MIME in Gmail API `drafts.create` request shape for a tool that supports raw MIME.
- `manifest.json`: missing facts, font audit, source/photo references, generated output status. `gmail_drafts_created=false` until a host tool actually succeeds; `delivery_ready=false` until content/layout/signature checks are completed.

`gmail-handoff.json` is deliberately connector-neutral, not a promise of a specific Gmail tool signature. The installed host maps it to available draft/upload tools. If attachments require a platform file ID, use the supported upload operation; don't substitute a local path. The runner never accesses Gmail itself, sends mail, archives source messages or changes calendars. Keep To/CC blank for review drafts unless the user supplied and verified recipients. `janhabuildings@gmail.com` is the current user's staging mailbox; it is not the DSENY inspections sending identity.

The No OIs cover does not claim the unsigned PDF is signed and sealed. After the PE supplies the final signed/sealed PDF, the host must verify it belongs to this report, replace the attachment and update the wording. No professional signature generation is implemented.

## Validation and limits

`python -m unittest discover -s tests -v` in the source repository covers the original generator plus the plugin: all four template variants, both inline/attached email workflows, actual Linux HTML/PDF conversion, package completeness/checksums, missing-field reporting, recipient validation and failure without false draft claims. The packaged runner is also executed from a fresh extracted directory, independent of the original source tree.

Not yet verified: host-side plugin installation, Gmail authorization/tools in an installed plugin session, actual Gmail draft writes, connector attachment transport, Windows Word conversion and exact visual fidelity. A test of Gmail in another chat is not a test of this plugin. The plugin has no MCP server or hosted backend to deploy. If a desired client cannot load local skills/scripts/app declarations, its supported plugin distribution/runtime must be supplied before this bundle can run there.

Client data belongs in an external state directory; avoid adding real requests, photos, MIME data, or manifests to the source repository or plugin ZIP. The build includes only fictional examples and original templates.

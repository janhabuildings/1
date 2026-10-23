# JBI Inspections iPhone app

Open **JBIInspections.xcodeproj** directly in Xcode 16 or later. It targets iOS 17+, uses SwiftUI and Apple system frameworks, and has no external Swift packages. The same checked-in source/project is compiled on the Mac; it does not need to be rewritten. `scripts/create_xcode_project.py` deterministically regenerates the project when source files are added.

## First build and installation

1. Copy/clone this repository onto a Mac. Open `ios/JBIInspections.xcodeproj`.
2. In the JBIInspections target, select your Apple development team under Signing & Capabilities. Change `nyc.dseny.JBIInspections` if your signing setup needs another bundle identifier.
3. Choose a simulator for basic UI checks or connect your iPhone, enable Developer Mode if prompted and select it as the run destination. Camera, microphone, speech and Messages must be exercised on a real device.
4. Build and run. No signing credentials are committed. For a simulator command-line build:

   ```sh
   xcodebuild -project ios/JBIInspections.xcodeproj -scheme JBIInspections \
     -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' \
     CODE_SIGNING_ALLOWED=NO build
   ```

5. Deploy/configure the backend using `backend/README.md`. In the app's Settings enter its HTTPS URL and API token, then tap Test connection. The API token is stored in Keychain, not in the app binary.

The current Linux environment has no Xcode, but GitHub macOS build run [39094950491](https://github.com/janhabuildings/1/actions/runs/39094950491) successfully compiled the simulator app from commit `20d8359`. Local Swift syntax and Xcode project/plist checks also passed. This verifies compilation and SwiftUI typechecking, not a signed physical-device build or real-device behavior. Signing, permission prompts, audio behavior, Mail behavior and TestFlight still need validation. App Store screenshots, privacy disclosures and production release assets are not completed.

## Field workflow

- Tap + and open the inspection. Title, project, date, pasted calendar, notes, transcript and reports are saved in the app's Application Support directory.
- Take photos with the camera or import using Photos Picker. Label each with scaffold/shed and its location/observation.
- Record an in-person conversation only after informing participants and meeting applicable consent rules. A visible Recording indicator is shown. Leaving the screen or app stops and saves the recording. Recording interruptions and long recordings require real-device validation.
- Import M4A, WAV, MP3 audio or a UTF-8 TXT transcript using Files. This is how recordings made elsewhere, including supported Apple call recordings, can be brought in. The app cannot capture ordinary phone/WhatsApp call audio or read personal SMS/WhatsApp history.
- On-device English transcription runs only where Apple's recognizer supports it; there is no silent cloud transcription fallback. Review/edit the result. When unavailable, type or import a transcript.
- Extract calendar candidates through the backend, review them and explicitly apply them. This fills draft fields only; it does not infer No OIs or drawing approval. Add actual attendees and measurements in each report.
- Optional AI analysis sends calendar, notes, transcript and up to six photos only after confirmation and only if the backend has `AI_API_KEY`. Suggestions are displayed and are **not** automatically applied. Use Confirm and add as open item only after inspection review. This changes that equipment result to OIs. Add/confirm other report details manually.
- Set each report's result explicitly. A No OIs selection with recorded open items is rejected. Generate review reports after syncing.
- Open/share the returned DOCX, PDF and HTML files. Email draft uses Apple's native Mail composer with HTML and the appropriate shed PDF attachment. Choose an account and save as a draft or send manually. The app does not create a remote Gmail draft through the Gmail API. An account in the standalone Gmail app alone does not configure Apple's Mail composer.
- Share notes, photos or generated files via the iOS share sheet to WhatsApp, Messages or another supported app. A separate Messages composer supports prefilled text. App availability and accepted file types are controlled by iOS/recipient apps.

## Offline and synchronization boundary

Local capture, notes, report editing, imported files and supported on-device transcription do not require the backend. Calendar extraction, AI analysis, code search and document generation currently do. Sync is manual and uploads that inspection and its media. Retry-safe UUID-based PUT and asset IDs prevent duplicate creation after uncertain network writes. Refresh preserves locally unsynced inspections. There is no multi-user conflict resolution; this is a single-operator first version. Remote media from other devices are not automatically downloaded into the local evidence gallery.

Files use iOS data protection and a device-only Keychain credential. Keep phone backups/device security appropriate for client information. This is not a separate end-to-end encrypted multi-user storage system.

## Report fidelity

Original DOCX templates are preserved by the shared generator. Linux PDF rendering still substitutes unavailable font faces and can wrap cells or add a footer-only page. This app does not magically fix those fonts. Outputs remain unsigned review drafts. Final fonts/page breaks, email HTML layout and PE signature/seal must be verified before client delivery. Photos are evidence for reviewed findings and retained as references; this version does not create a formatted photo appendix in the DOCX.

## iPhone development with no local Mac

Render remains the backend. No Windows server or local backend is required. The app defaults to `https://jbi-inspections.onrender.com`; enter the existing Render `INSPECTION_API_TOKEN` in iPhone Settings and save/test the connection. The token stays in Keychain. Render Free may take time to wake up after inactivity.

GitHub Actions **Build iPhone app** compiles the checked-in Xcode project on a GitHub-hosted Mac when iOS source changes are pushed, or on manual dispatch. It uploads an unsigned simulator app and build log. This verifies compilation without renting a Mac; GitHub-hosted macOS minutes are subject to the repository's Actions allowance and billing settings. A simulator app cannot be installed on an actual iPhone.

For installation without your own Mac, the planned distribution route is TestFlight:

1. Enroll in the [Apple Developer Program](https://developer.apple.com/programs/enroll/) if needed (Apple generally charges US$99 per membership year; local pricing and eligibility vary).
2. Register the app's bundle ID and create its App Store Connect record under your own account.
3. Configure distribution signing and provisioning for a cloud device archive. Keep certificates, private keys and App Store Connect API credentials in secure CI secrets, never source code or chat. The manual release-signing workflow is prepared; credentials still need configuring. Follow [TestFlight setup](TESTFLIGHT.md).
4. Complete release assets, including the app icon and required privacy/export-compliance details, and validate an iPhone archive before uploading it to App Store Connect.
5. Install Apple's TestFlight app on the iPhone and accept the invitation after the build is processed. External testing may require Beta App Review; internal testing depends on App Store Connect access. TestFlight builds expire after 90 days.

The iPhone reference search includes **Reviewed sources**, **NYC DOB Chapter 33 · draft**, and **NYC SCA Safety Manual · draft**. Draft results retain their agency, PDF pages, parent-section context and edition warnings, and do not imply effective-date approval. Semantic search additionally requires `AI_API_KEY` in Render, not in the iPhone app.

First physical-device checks: camera permission and capture; microphone consent/recording and app interruption; on-device transcription; offline note/photo persistence; sync after Render wakes up; SF/SH report generation and file downloads; code searches; and HTML Mail draft with the correct PDF attachment. A successful cloud compile alone does not verify these behaviors.

## Photo review with DOB/SCA references

In an inspection's evidence list, turn on **Include photo in AI review** for up to six photographs. Add actual equipment/location notes, then start analysis and confirm data sharing. The backend first observes the selected photos, searches the uploaded DOB and SCA vector libraries, and returns possible deficiencies with exact supporting excerpts, PDF page references and field-confirmation checks. A photo thumbnail appears alongside a linked suggestion. Draft source warnings and missing information are shown separately from findings.

**Confirm and add as open item** is still required. It copies reviewed text, photo references and provisional citation details into that equipment's draft; it never selects No OIs. Edit findings in the report editor before generating the report. Changing a report is a separate user action; analysis alone never changes it. Both observations and applicable source requirements need inspector review. Actual photo-analysis quality and Mail/camera interactions still require field/device validation.

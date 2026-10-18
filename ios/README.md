# JBI Inspections iPhone app — first implementation

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

There is no Xcode/Swift compiler in the current Linux environment. Swift syntax parsing and Xcode project/plist structure are checked here; this is **not** a compiled or device-tested iOS build. Signing, permission prompts, audio behavior, UI typechecking, Mail behavior and TestFlight still need Mac/device validation. App Store screenshots, privacy disclosures and production release assets are not completed.

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

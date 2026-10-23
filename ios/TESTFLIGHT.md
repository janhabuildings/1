# TestFlight setup without owning a Mac

The app compiles on GitHub's macOS runners. The manual **Release iPhone app to TestFlight** workflow signs, archives and uploads it after the following account configuration. Enrollment alone does not supply signing credentials. No Apple credentials are in this repository and no TestFlight upload has been made.

## 1. Create the Apple app identity

In [Certificates, Identifiers & Profiles](https://developer.apple.com/account/resources/identifiers/list), register an explicit App ID:

- Description: JBI Inspections
- Bundle ID: `nyc.dseny.JBIInspections`
- No extra capabilities are needed for the current camera, microphone or reference-search features.

If this bundle ID is unavailable, stop and choose another identifier; update the Xcode generator and release script together before generating profiles. Do not use another organization's registered identity.

In [App Store Connect](https://appstoreconnect.apple.com/), accept pending agreements, then Apps → + → New App. Choose iOS, enter JBI Inspections (or another available display name), English, the registered bundle ID, and your own unique SKU such as `jbi-inspections-ios`. The Apple account owns this record; it is not created through Codex automatically.

## 2. Set signing credentials securely

In [GitHub Actions settings](https://github.com/janhabuildings/1/settings/secrets/actions), configure:

| Setting | Type | Value |
| --- | --- | --- |
| `APPLE_TEAM_ID` | Repository variable | Your 10-character Apple Team ID from developer membership details |
| `APPLE_CERTIFICATE_BASE64` | Repository secret | Base64 of an Apple Distribution certificate exported as a password-protected `.p12`, **including its private key** |
| `APPLE_CERTIFICATE_PASSWORD` | Repository secret | The password for that P12 |
| `APPLE_PROFILE_BASE64` | Repository secret | Base64 of an App Store Connect distribution `.mobileprovision` for this bundle ID/team/certificate |
| `ASC_KEY_ID` | Repository secret | App Store Connect API team key ID |
| `ASC_ISSUER_ID` | Repository secret | Its issuer ID |
| `ASC_PRIVATE_KEY` | Repository secret | Full downloaded `.p8` API key text |

Create the App Store Connect API key under Users and Access → Integrations → App Store Connect API (labels can vary). Use a team key with the App Manager role for this upload workflow, or request the necessary access from your Account Holder. The script expects an issuer ID, so an individual API key is not interchangeable. Never paste passwords, P12 files, private keys or API key text into chat. A public `.cer` alone cannot sign the app; its matching private key is required. Do not revoke existing certificates to make room without understanding which apps use them.

A signing certificate can be requested with a CSR created on Windows using OpenSSL, or on a trusted Mac. The private key must remain under your control; the `.p12` can then be imported into GitHub Secrets. We can walk through that after the app identity is registered. Do not rent a Mac solely to create the CSR.

## 3. Build and upload

The checked-in app icon is a provisional opaque JBI monogram. Info.plist uses build-setting version values so each release attempt gets a distinct build number. No assertion about encryption export exemptions is prefilled; answer Apple's compliance questions for the actual app.

Open GitHub Actions → **Release iPhone app to TestFlight** → Run workflow → main. This is a manual upload action, not an automatic upload on every push. It imports signing material into a temporary keychain, checks the profile's team, bundle, expiry and distribution type, archives the device app, exports an IPA and uploads with Apple's Transporter. Signing files, private key, temporary keychain and IPA are deleted during cleanup; no credential-bearing release archive is uploaded as a GitHub artifact.

This signing/upload workflow cannot be fully verified until your credentials and app record are configured. Simulator compilation does not establish that signing or App Store validation will pass. Check the upload result and App Store Connect processing before assuming a TestFlight build is available.

## 4. Install and test

Install Apple's TestFlight app on the iPhone. After processing and any required export-compliance responses, add yourself as an internal tester if your App Store Connect role permits it. External testers can require Beta App Review. Complete any test information Apple requests. Use the existing Render API token only inside the app's connection settings; never put it into the app binary or public tester notes.

First-device checks include photo selection and permissions, audio recording/interruption, offline evidence persistence, Render synchronization, reference-grounded photo suggestions, separate SF/SH reports, PDF/DOCX downloads and the HTML Mail draft/attachment. GPS and drawing pins discussed in chat are not implemented in this build.

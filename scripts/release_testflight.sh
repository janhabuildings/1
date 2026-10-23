#!/usr/bin/env bash
# Run only on a disposable GitHub macOS runner. No secrets are printed or uploaded as artifacts.
set -euo pipefail
umask 077
for name in APPLE_TEAM_ID APPLE_CERTIFICATE_BASE64 APPLE_CERTIFICATE_PASSWORD APPLE_PROFILE_BASE64 ASC_KEY_ID ASC_ISSUER_ID ASC_PRIVATE_KEY RUNNER_TEMP GITHUB_RUN_NUMBER GITHUB_RUN_ATTEMPT; do
  if [ -z "${!name:-}" ]; then echo "Missing secure release setting: $name"; exit 1; fi
done
release_dir=$(mktemp -d "$RUNNER_TEMP/jbi-release.XXXXXX")
keychain="$release_dir/signing.keychain-db"
profile_path=""
private_key=""
cleanup() {
  security delete-keychain "$keychain" >/dev/null 2>&1 || true
  if [ -n "$profile_path" ]; then rm -f "$profile_path"; fi
  if [ -n "$private_key" ]; then rm -f "$private_key"; fi
  rm -rf "$release_dir"
}
trap cleanup EXIT
export RELEASE_DIR="$release_dir"
python3 - <<'PY'
import base64,os,pathlib
root=pathlib.Path(os.environ['RELEASE_DIR'])
for name,file in [('APPLE_CERTIFICATE_BASE64','certificate.p12'),('APPLE_PROFILE_BASE64','profile.mobileprovision')]:
    (root/file).write_bytes(base64.b64decode(''.join(os.environ[name].split()),validate=True))
(root/'AuthKey.p8').write_text(os.environ['ASC_PRIVATE_KEY'])
PY
password=$(openssl rand -hex 32)
security create-keychain -p "$password" "$keychain"
security set-keychain-settings -lut 21600 "$keychain"
security unlock-keychain -p "$password" "$keychain"
security import "$release_dir/certificate.p12" -P "$APPLE_CERTIFICATE_PASSWORD" -A -t cert -f pkcs12 -k "$keychain" >/dev/null
security set-key-partition-list -S apple-tool:,apple:,codesign: -k "$password" "$keychain" >/dev/null
security list-keychains -d user -s "$keychain" "$HOME/Library/Keychains/login.keychain-db"
security cms -D -i "$release_dir/profile.mobileprovision" > "$release_dir/profile.plist"
python3 - <<'PY'
import datetime,os,pathlib,plistlib,re
root=pathlib.Path(os.environ['RELEASE_DIR']); p=plistlib.loads((root/'profile.plist').read_bytes())
team=os.environ['APPLE_TEAM_ID'];bundle='nyc.dseny.JBIInspections'
if not re.fullmatch(r'[A-Z0-9]{10}',team) or not re.fullmatch(r'[A-Za-z0-9-]+',p['UUID']):
    raise SystemExit('Invalid Team ID or profile UUID')
if p['TeamIdentifier'] != [team] or p['Entitlements']['application-identifier'] != team+'.'+bundle:
    raise SystemExit('Provisioning profile must match your Team ID and nyc.dseny.JBIInspections')
if p.get('ProvisionedDevices') or p.get('ProvisionsAllDevices') or p['Entitlements'].get('get-task-allow'):
    raise SystemExit('Use an App Store Connect distribution profile, not development or ad hoc')
if p['ExpirationDate'] <= datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None):
    raise SystemExit('Provisioning profile has expired')
(root/'profile-uuid').write_text(p['UUID'])
(root/'ExportOptions.plist').write_bytes(plistlib.dumps({'method':'app-store-connect','teamID':team,
    'signingStyle':'manual','signingCertificate':'Apple Distribution',
    'provisioningProfiles':{bundle:p['UUID']}}))
PY
profile_uuid=$(cat "$release_dir/profile-uuid")
profile_dir="$HOME/Library/MobileDevice/Provisioning Profiles"
mkdir -p "$profile_dir"
profile_path="$profile_dir/$profile_uuid.mobileprovision"
if [ -e "$profile_path" ]; then profile_path=""; echo 'Profile already exists on runner; refusing to overwrite'; exit 1; fi
cp "$release_dir/profile.mobileprovision" "$profile_path"
key_dir="$HOME/.appstoreconnect/private_keys"
mkdir -p "$key_dir"
key_target="$key_dir/AuthKey_${ASC_KEY_ID}.p8"
if [ -e "$key_target" ]; then echo 'API key already exists on runner; refusing to overwrite'; exit 1; fi
private_key="$key_target"
cp "$release_dir/AuthKey.p8" "$private_key"
build_number="$GITHUB_RUN_NUMBER.$GITHUB_RUN_ATTEMPT"
xcodebuild -project ios/JBIInspections.xcodeproj -scheme JBIInspections -configuration Release \
  -destination 'generic/platform=iOS' -archivePath "$release_dir/JBI.xcarchive" \
  DEVELOPMENT_TEAM="$APPLE_TEAM_ID" CODE_SIGN_STYLE=Manual CODE_SIGN_IDENTITY='Apple Distribution' \
  PROVISIONING_PROFILE_SPECIFIER="$profile_uuid" CURRENT_PROJECT_VERSION="$build_number" archive
xcodebuild -exportArchive -archivePath "$release_dir/JBI.xcarchive" -exportOptionsPlist "$release_dir/ExportOptions.plist" -exportPath "$release_dir/export"
ipa="$release_dir/export/JBIInspections.ipa"
test -f "$ipa"
xcrun iTMSTransporter -m upload -assetFile "$ipa" -apiKey "$ASC_KEY_ID" -apiIssuer "$ASC_ISSUER_ID"
echo 'Upload finished. Check App Store Connect for processing, compliance questions and tester availability.'

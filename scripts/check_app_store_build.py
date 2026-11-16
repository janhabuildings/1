#!/usr/bin/env python3
"""Read App Store Connect build records; never uploads or modifies an app."""
import base64
import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

HOST = 'https://api.appstoreconnect.apple.com'
BUNDLE = 'nyc.dseny.JBIInspections'


def b64(value):
    return base64.urlsafe_b64encode(value).rstrip(b'=').decode()


def jose_signature(der):
    # P-256 DER signature: SEQUENCE(INTEGER r, INTEGER s).
    if len(der) < 8 or der[0] != 48 or der[1] != len(der) - 2:
        raise ValueError('Invalid signing response')
    pos, values = 2, []
    for _ in range(2):
        if der[pos] != 2:
            raise ValueError('Invalid signature integer')
        size = der[pos + 1]
        value = der[pos + 2:pos + 2 + size]
        if len(value) != size or not size or value[0] & 128:
            raise ValueError('Invalid signature length')
        value = value.lstrip(b'\0')
        if len(value) > 32:
            raise ValueError('Invalid P-256 signature')
        values.append(value.rjust(32, b'\0'))
        pos += size + 2
    if pos != len(der):
        raise ValueError('Unexpected signature data')
    return b''.join(values)


def make_token(key_id, issuer, key):
    now = int(time.time())
    compact = lambda obj: b64(json.dumps(obj, separators=(',', ':')).encode())
    message = compact({'alg': 'ES256', 'kid': key_id, 'typ': 'JWT'}) + '.' + compact(
        {'iss': issuer, 'iat': now - 10, 'exp': now + 600, 'aud': 'appstoreconnect-v1'})
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, 'AuthKey.p8')
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(key)
        signed = subprocess.run(['openssl', 'dgst', '-sha256', '-sign', path],
                                input=message.encode(), capture_output=True, check=False)
        if signed.returncode:
            raise RuntimeError('Unable to sign Apple API request; verify ASC_PRIVATE_KEY')
    return message + '.' + b64(jose_signature(signed.stdout))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def get(token, path, **params):
    url = HOST + path + ('?' + urllib.parse.urlencode(params) if params else '')
    request = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token})
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=45) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        # Avoid logging response bodies or headers, which may reflect credentials.
        raise RuntimeError(f'Apple API returned HTTP {error.code} for {path}') from None


def describe(build, included):
    attrs = build.get('attributes', {})
    relation = build.get('relationships', {}).get('preReleaseVersion', {}).get('data') or {}
    version = included.get(relation.get('id'), {}).get('attributes', {}).get('version', '?')
    return f"Version {version}, build {attrs.get('version', '?')}: {attrs.get('processingState', '?')}; uploaded {attrs.get('uploadedDate', '?')}"


def main():
    required = ['ASC_KEY_ID', 'ASC_ISSUER_ID', 'ASC_PRIVATE_KEY']
    if any(not os.environ.get(name) for name in required):
        raise RuntimeError('Missing existing App Store Connect API secrets')
    target = os.environ.get('BUILD_NUMBER', '19.1')
    token = make_token(*(os.environ[name] for name in required))
    apps = get(token, '/v1/apps', **{'filter[bundleId]': BUNDLE, 'limit': 5})['data']
    if len(apps) != 1:
        raise RuntimeError('Could not uniquely identify JBI app in this Apple account')
    app = apps[0]
    print(f"App: {app['attributes']['name']} ({BUNDLE}); Apple ID {app['id']}")
    result = get(token, '/v1/builds', **{'filter[app]': app['id'], 'filter[version]': target,
                                      'include': 'preReleaseVersion', 'limit': 200})
    included = {item['id']: item for item in result.get('included', [])}
    if result['data']:
        for build in result['data']:
            print(describe(build, included))
    else:
        print(f'Build {target}: NOT FOUND in Apple build records. Processing is unconfirmed.')
    recent = get(token, '/v1/builds', **{'filter[app]': app['id'], 'sort': '-uploadedDate',
                                      'include': 'preReleaseVersion', 'limit': 5})
    included = {item['id']: item for item in recent.get('included', [])}
    print('Most recently uploaded builds:')
    for build in recent['data']:
        print(describe(build, included))
    # Upload records can reveal failures before a processed build exists.
    try:
        uploads = get(token, f"/v1/apps/{app['id']}/buildUploads", limit=10)
        print('Recent Apple upload records (version, build, date, state):')
        for upload in uploads['data']:
            attrs = upload.get('attributes', {})
            safe = {key: attrs[key] for key in ('cfBundleShortVersionString', 'cfBundleVersion',
                    'createdDate', 'state') if key in attrs}
            print(json.dumps(safe, sort_keys=True))
    except RuntimeError as error:
        print(f'Upload-detail lookup unavailable: {error}. Build results above remain valid.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Do not expose signing subprocess output or request headers.
        if isinstance(error, RuntimeError):
            print(str(error))
        else:
            print(f'Build status check failed ({type(error).__name__}); no upload performed.')
        raise SystemExit(1)

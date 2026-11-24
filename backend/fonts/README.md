# Private report-rendering fonts

The October 25 master uses Aptos. Font binaries and encoded font data must stay
out of this public repository. Use the operator-supplied, licensed files only.

Only Aptos regular, bold, italic and bold italic are required by the current
report templates. Include their supplied license when preparing a private ZIP.
Render limits the combined size of secret files to 1 MB; do not package all
Display/Mono/Narrow/Serif/extra-weight fonts for that route. The four-face ZIP
with its license is about 621 KB after Base64 encoding.

## Private secret file

Create a Render Secret File named `aptos-fonts.zip.base64` containing the complete
Base64 ZIP text. Docker reads `/etc/secrets/aptos-fonts.zip.base64`;
`REPORT_FONT_ARCHIVE` can override this local path. Archives must have flat
filenames. Local archive validation accepts up to 8 MB encoded and 16 MB expanded,
while Render's smaller combined secret-file limit still applies.

## Private environment transport

Automation can merge `REPORT_FONT_DATA_PARTS`, `REPORT_FONT_DATA_SHA256` and
`REPORT_FONT_DATA_001` through the declared part count into Render's private
service environment. Each part contains at most 32,768 Base64 characters, avoiding
per-variable process limits; the complete encoded data must be at most 1 MB.
The SHA-256 is of the decoded ZIP. Missing parts or checksum errors reject the
installation. These values are private runtime configuration, never source or logs.
When configured, this transport takes precedence over the secret-file path.

At startup the backend validates the complete archive, installs fonts under
`$XDG_DATA_HOME/fonts/jbi`, refreshes fontconfig, and checks all four Aptos styles.
The image uses `/var/data` for its writable XDG data/cache paths. Fonts are
recreated after restarts and are not web-served or added to the inspection database.

Authenticated `/capabilities` exposes only font status: `report_fonts.ready`,
`missing_faces`, installed family names and resolved face metadata. Startup logs
contain the same status, never the encoded data. The web UI distinguishes missing
styles from a complete installation. Regenerate old PDFs after installing fonts;
previously exported PDF files retain their original embedded fonts.

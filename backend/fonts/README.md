# Private report-rendering fonts

The October 25 master uses Aptos. The supplied license does not grant font
redistribution, and this repository is public. Do not commit font binaries here.
The `.gitignore` excludes them.

Install operator-supplied faces with a private Render **Secret File** named
`aptos-fonts.zip.base64`. Paste the complete Base64 ZIP text prepared for the
operator, not the binary ZIP itself. The archive contains regular, bold, italic,
bold italic and the supplied license. Docker services read it at
`/etc/secrets/aptos-fonts.zip.base64`; `REPORT_FONT_ARCHIVE` optionally overrides
that path.

At startup, `backend/font_assets.py` validates the archive, installs its fonts
under `$XDG_DATA_HOME/fonts/jbi`, and refreshes fontconfig. The Docker image uses
`/var/data` as XDG data home and makes its cache writable by the service user.
Render keeps secret files across deployments, so the font install is recreated
on each restart even on the free plan. The font folder is never web-served.

Check authenticated `/capabilities` → `report_fonts`: installed should be 4,
with family Aptos and no error. Generated report font audit should list Aptos
under requested and have an empty missing list. Missing/invalid setup does not
prevent inspection access; the error is exposed through capabilities instead.

Only the four Aptos faces used by the current templates are necessary. The
uploaded Display/Mono/Narrow/Serif and other weights are not required by the
current template font audit.

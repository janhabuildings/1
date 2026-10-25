# Report rendering fonts

The October 25, 2026 master requests Aptos. Put supplied Aptos TTF/OTF files
(including bold/italic variants used by the master) in this folder before the
Render image is built. Docker installs this folder into fontconfig's standard
font directory. No font files are supplied in the repository yet.

Without these files, the DOCX retains the requested family but LibreOffice
substitutes a locally installed family in PDF/HTML rendering. The report's
font audit lists missing families; it must not be described as an exact match.

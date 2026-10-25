import base64
from io import BytesIO
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile,ZIP_DEFLATED
from backend.font_assets import install_archive,configure_private_fonts


def package(path,entries):
    buffer=BytesIO()
    with ZipFile(buffer,'w',ZIP_DEFLATED) as archive:
        for name,content in entries.items():archive.writestr(name,content)
    path.write_bytes(base64.b64encode(buffer.getvalue()))


class PrivateFonts(unittest.TestCase):
    def test_missing_and_invalid_secret_do_not_break_startup(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);secret=root/'fonts.base64'
            self.assertFalse(install_archive(secret,root/'fonts')['configured'])
            secret.write_text('not base64!')
            with patch.dict(os.environ,{'REPORT_FONT_ARCHIVE':str(secret),'XDG_DATA_HOME':str(root/'data')}):
                result=configure_private_fonts()
            self.assertEqual(result['installed'],0);self.assertIn('Base64',result['error'])

    def test_path_traversal_and_invalid_fonts_are_not_installed(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);secret=root/'fonts.base64';destination=root/'fonts'
            for files in ({'../outside.ttf':b'bad'},{'a.ttf':b'bad'},{'a.py':b'bad'}):
                package(secret,files)
                with self.assertRaises(ValueError):install_archive(secret,destination)
                self.assertFalse((root/'outside.ttf').exists())
                self.assertFalse((destination/'a.ttf').exists())

    @unittest.skipUnless(shutil.which('fc-scan') and shutil.which('fc-match') and shutil.which('fc-cache'),'Fontconfig required')
    def test_valid_operator_font_and_license_install_privately(self):
        candidates=subprocess.check_output(['fc-list','--format','%{file}\n'],text=True).splitlines()
        source=next((Path(name) for name in candidates if Path(name).suffix.lower() in ('.ttf','.otf') and Path(name).read_bytes()[:4] in (b'\x00\x01\x00\x00',b'OTTO')),None)
        if source is None:self.skipTest('A local TrueType/OpenType font is required for this fixture')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);secret=root/'fonts.base64';data=root/'data';destination=data/'fonts/jbi'
            package(secret,{'Operator.ttf':source.read_bytes(),'License.txt':b'Operator-supplied license'})
            with patch.dict(os.environ,{'XDG_DATA_HOME':str(data),'XDG_CACHE_HOME':str(root/'cache')}):
                result=install_archive(secret,destination)
            self.assertEqual(result['installed'],1);self.assertTrue(result['families'])
            self.assertEqual((destination/'Operator.ttf').read_bytes(),source.read_bytes())
            self.assertEqual((destination/'License.txt').read_bytes(),b'Operator-supplied license')

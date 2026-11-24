import base64
import hashlib
from io import BytesIO
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile,ZIP_STORED

from backend.font_assets import install_archive,install_environment,aptos_faces,configure_private_fonts


def archive(payload=b'font fixture'):
    buffer=BytesIO()
    with ZipFile(buffer,'w',compression=ZIP_STORED) as package:package.writestr('Aptos.ttf',b'\x00\x01\x00\x00'+payload)
    return buffer.getvalue()


def successful(command,**kwargs):
    output='Aptos\n' if command[0]=='fc-scan' else ''
    return subprocess.CompletedProcess(command,0,output,'')


class PrivateFonts(unittest.TestCase):
    def test_private_archive_above_old_two_mb_limit_installs(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);file=root/'archive.base64';file.write_bytes(base64.b64encode(archive(b'X'*(2*1024*1024))))
            self.assertGreater(file.stat().st_size,2*1024*1024)
            with patch('backend.font_assets.subprocess.run',side_effect=successful):result=install_archive(file,root/'fonts')
            self.assertEqual(result['installed'],1);self.assertTrue((root/'fonts/Aptos.ttf').is_file())
    def test_env_parts_checksum_and_missing_parts(self):
        packed=archive();encoded=base64.b64encode(packed).decode();half=len(encoded)//2
        env={'REPORT_FONT_DATA_PARTS':'2','REPORT_FONT_DATA_001':encoded[:half],'REPORT_FONT_DATA_002':encoded[half:], 'REPORT_FONT_DATA_SHA256':hashlib.sha256(packed).hexdigest()}
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,env),patch('backend.font_assets.subprocess.run',side_effect=successful):
            self.assertEqual(install_environment(Path(directory)/'fonts')['installed'],1)
            os.environ['REPORT_FONT_DATA_SHA256']='0'*64
            with self.assertRaisesRegex(ValueError,'checksum does not match'):install_environment(Path(directory)/'bad')
            del os.environ['REPORT_FONT_DATA_002']
            with self.assertRaisesRegex(ValueError,'incomplete'):install_environment(Path(directory)/'bad')
    def test_required_faces_reject_silent_substitution_and_missing_bold(self):
        def match(command,**kwargs):
            style=command[-1].split('style=')[-1]
            return subprocess.CompletedProcess(command,0,('Liberation Sans' if style=='Bold' else 'Aptos')+'\n'+style+'\n','')
        with patch('backend.font_assets.subprocess.run',side_effect=match):result=aptos_faces()
        self.assertFalse(result['ready']);self.assertEqual(result['missing_faces'],['Aptos Bold'])
    def test_archive_path_traversal_does_not_write_fonts(self):
        data=BytesIO()
        with ZipFile(data,'w') as package:package.writestr('../Aptos.ttf',b'\x00\x01\x00\x00fixture')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'bad.base64';path.write_bytes(base64.b64encode(data.getvalue()))
            with self.assertRaisesRegex(ValueError,'flat filenames'):install_archive(path,Path(directory)/'fonts')
            self.assertFalse((Path(directory)/'fonts').exists())
    def test_invalid_private_setup_keeps_inspection_access_available(self):
        with patch.dict(os.environ,{'REPORT_FONT_DATA_PARTS':'nope'}),patch('backend.font_assets.aptos_faces',return_value={'ready':False,'missing_faces':['Aptos'],'faces':[]}):
            result=configure_private_fonts()
        self.assertEqual(result['installed'],0);self.assertIn('part count',result['error'])

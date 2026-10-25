"""Install operator-supplied fonts from a private Render secret file, never the public repo."""
import base64
from io import BytesIO
import os
from pathlib import Path
import subprocess
import tempfile
from zipfile import ZipFile,BadZipFile,ZIP_STORED,ZIP_DEFLATED

DEFAULT_ARCHIVE='/etc/secrets/aptos-fonts.zip.base64'


def install_archive(path,font_root):
    path=Path(path);font_root=Path(font_root)
    if not path.is_file():return {'configured':False,'installed':0,'families':[]}
    if path.stat().st_size>2*1024*1024:raise ValueError('Private font archive exceeds 2 MB')
    try:content=base64.b64decode(b''.join(path.read_bytes().split()),validate=True)
    except ValueError as error:raise ValueError('Private font archive must contain only Base64 ZIP data') from error
    try:
        with ZipFile(BytesIO(content)) as package:
            entries=package.infolist();names=[item.filename for item in entries]
            if not entries or len(entries)>40 or len(set(names))!=len(names) or sum(item.file_size for item in entries)>16*1024*1024:
                raise ValueError('Invalid or oversized private font archive')
            if any(item.flag_bits & 1 for item in entries):raise ValueError('Encrypted font archives are unsupported')
            if any(item.compress_type not in (ZIP_STORED,ZIP_DEFLATED) for item in entries):raise ValueError('Use stored or deflated ZIP compression for fonts')
            for name in names:
                if Path(name).name!=name or '\\' in name or name in ('.','..'):
                    raise ValueError('Private font archive must contain flat filenames only')
                if Path(name).suffix.lower() not in ('.ttf','.otf','.rtf','.txt'):
                    raise ValueError('Private font archive contains an unsupported file type')
            font_root.mkdir(parents=True,exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='.font-install-',dir=font_root.parent) as directory:
                staged=Path(directory);families=set();fonts=[]
                for item in entries:
                    data=package.read(item);target=staged/item.filename;target.write_bytes(data)
                    if target.suffix.lower() not in ('.ttf','.otf'):continue
                    if data[:4] not in (b'\x00\x01\x00\x00',b'OTTO'):raise ValueError('Invalid OpenType/TrueType font file')
                    scan=subprocess.run(['fc-scan','--format','%{family}\n',str(target)],capture_output=True,text=True,timeout=10)
                    if scan.returncode or not scan.stdout.strip():raise ValueError('Font metadata could not be read')
                    families.update(line.strip() for line in scan.stdout.splitlines() if line.strip());fonts.append(target)
                if not fonts:raise ValueError('Private font archive contains no font files')
                # Validate the full archive before installing any files.
                for target in staged.iterdir():target.replace(font_root/target.name)
            cached=subprocess.run(['fc-cache','-f',str(font_root)],capture_output=True,text=True,timeout=30)
            if cached.returncode:raise ValueError('Font cache refresh failed')
            return {'configured':True,'installed':len(fonts),'families':sorted(families)}
    except BadZipFile as error:raise ValueError('Private font archive is not a valid ZIP') from error


def configure_private_fonts():
    data_home=Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))
    try:return install_archive(os.environ.get('REPORT_FONT_ARCHIVE',DEFAULT_ARCHIVE),data_home/'fonts/jbi')
    except (ValueError,OSError,subprocess.TimeoutExpired) as error:
        # Font setup must not prevent access to existing inspections; font audit
        # will still mark missing families on generated reports.
        return {'configured':True,'installed':0,'families':[],'error':str(error)}

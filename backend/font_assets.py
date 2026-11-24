"""Install operator-supplied fonts from a private Render secret file, never the public repo."""
import base64
import hashlib
import re
from io import BytesIO
import os
from pathlib import Path
import subprocess
import tempfile
from zipfile import ZipFile,BadZipFile,ZIP_STORED,ZIP_DEFLATED

DEFAULT_ARCHIVE='/etc/secrets/aptos-fonts.zip.base64'
MAX_ARCHIVE_BYTES=8*1024*1024
MAX_ENV_BYTES=1024*1024


def install_archive(path,font_root):
    path=Path(path);font_root=Path(font_root)
    if not path.is_file():return {'configured':False,'installed':0,'families':[]}
    if path.stat().st_size>MAX_ARCHIVE_BYTES:raise ValueError('Private font archive exceeds 8 MB')
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


def aptos_faces():
    faces=[]
    for style in ('Regular','Bold','Italic','Bold Italic'):
        matched=subprocess.run(['fc-match','-f','%{family}\n%{style}\n','Aptos:style='+style],capture_output=True,text=True,timeout=10)
        lines=matched.stdout.splitlines()
        family=lines[0] if lines else ''
        actual=lines[1] if len(lines)>1 else ''
        names={name.strip().casefold() for name in family.split(',')}
        styles={name.strip().casefold() for name in actual.split(',')}
        valid=not matched.returncode and 'aptos' in names and (style.casefold() in styles or (style=='Regular' and 'book' in styles))
        faces.append({'requested':'Aptos '+style,'family':family,'style':actual,'matched':bool(valid)})
    return {'ready':all(face['matched'] for face in faces),'missing_faces':[face['requested'] for face in faces if not face['matched']], 'faces':faces}


def install_environment(font_root):
    raw=os.environ.get('REPORT_FONT_DATA_PARTS','')
    if not re.fullmatch(r'[1-9][0-9]?',raw) or not 1<=int(raw)<=64:
        raise ValueError('Private font data part count is invalid')
    parts=[]
    for index in range(1,int(raw)+1):
        value=os.environ.get(f'REPORT_FONT_DATA_{index:03d}','')
        if not value or len(value)>32768:raise ValueError('Private font data is incomplete or a part is oversized')
        parts.append(value)
    encoded=''.join(parts).encode('ascii')
    if len(encoded)>MAX_ENV_BYTES:raise ValueError('Private environment font data exceeds 1 MB')
    expected=os.environ.get('REPORT_FONT_DATA_SHA256','')
    if not re.fullmatch(r'[a-f0-9]{64}',expected):raise ValueError('Private font data checksum is missing')
    try:content=base64.b64decode(encoded,validate=True)
    except ValueError as error:raise ValueError('Private font data must be Base64 ZIP data') from error
    if hashlib.sha256(content).hexdigest()!=expected:raise ValueError('Private font data checksum does not match')
    with tempfile.TemporaryDirectory(prefix='private-font-data-') as directory:
        path=Path(directory)/'fonts.base64';path.write_bytes(encoded);path.chmod(0o600)
        return install_archive(path,font_root)


def configure_private_fonts():
    data_home=Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))
    source='private_environment' if os.environ.get('REPORT_FONT_DATA_PARTS') else 'private_secret_file'
    try:
        result=install_environment(data_home/'fonts/jbi') if source=='private_environment' else install_archive(os.environ.get('REPORT_FONT_ARCHIVE',DEFAULT_ARCHIVE),data_home/'fonts/jbi')
    except (ValueError,OSError,subprocess.TimeoutExpired) as error:
        result={'configured':True,'installed':0,'families':[],'error':str(error)}
    result['source']=source
    try:result.update(aptos_faces())
    except (OSError,subprocess.TimeoutExpired):result.update(ready=False,missing_faces=['Aptos regular/bold/italic/bold italic'],faces=[])
    return result

"""Install Debian's authenticated LibreOffice packages into .tools without root."""
import os
from pathlib import Path
import shutil
import subprocess

base = Path(__file__).resolve().parents[1]
tools = base / '.tools'
apt = tools / 'apt'
root = tools / 'office'
for folder in (apt/'lists/partial', apt/'cache/archives/partial',root,tools/'bin'):
    folder.mkdir(parents=True, exist_ok=True)
if 'ID=debian' not in Path('/etc/os-release').read_text() or 'VERSION_CODENAME=trixie' not in Path('/etc/os-release').read_text():
    raise SystemExit('This helper targets Debian 13 only. Install LibreOffice Writer with your platform package manager.')
(apt/'config').write_text(f'''Dir::Etc::parts "-";
Dir::Etc::main "-";
Dir::Etc::sourcelist "{apt}/sources.list";
Dir::Etc::sourceparts "-";
Dir::State::lists "{apt}/lists";
Dir::Cache "{apt}/cache";
APT::Get::List-Cleanup "0";
''')
(apt/'sources.list').write_text('deb [signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] https://deb.debian.org/debian trixie main\n')
env=dict(os.environ,APT_CONFIG=str(apt/'config'))
subprocess.run(['apt-get','update'],env=env,check=True)
subprocess.run(['apt-get','-o','Debug::NoLocking=1','install','--download-only','-y','--no-install-recommends','libreoffice-writer'],env=env,check=True)
for package in (apt/'cache/archives').glob('*.deb'):
    subprocess.run(['dpkg-deb','-x',str(package),str(root)],check=True)
program = root/'usr/lib/libreoffice/program'
for path in root.rglob('*'):
    if path.is_symlink():
        dest=path.readlink()
        if dest.is_absolute() and (root/str(dest).lstrip('/')).exists():
            path.unlink()
            path.symlink_to(root/str(dest).lstrip('/'))
# Debian normally creates this configuration during package post-install.
registry=root/'usr/lib/libreoffice/share/registry/main.xcd'
if registry.is_symlink(): registry.unlink()
shutil.copy2(registry.parent.parent/'.registry/main.xcd',registry)
fundamental=program/'fundamentalrc'
fundamental.write_text(fundamental.read_text().replace('file:///usr/lib/libreoffice',program.parent.as_uri()))
# UNO can resolve its boot ini relative to the symlinked library directory.
(root/'usr/lib/x86_64-linux-gnu/unorc').write_text((program/'unorc').read_text().replace('${ORIGIN}',program.as_uri()))
wrapper=tools/'bin/libreoffice'
# Paths use shell quoting, not JSON quoting.
from shlex import quote
wrapper.write_text('#!/bin/sh\nexport LD_LIBRARY_PATH='+quote(str(program)+':'+str(root/'usr/lib/x86_64-linux-gnu'))+'${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}\nexport XDG_CACHE_HOME='+quote(str(tools/'cache'))+'\nexec '+quote(str(program/'soffice'))+' "$@"\n')
wrapper.chmod(0o755)
subprocess.run([str(wrapper),'--headless','--version'],check=True)
print('Add to PATH for this session: '+str(tools/'bin'))

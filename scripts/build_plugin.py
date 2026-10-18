"""Build a self-contained official-format plugin and local marketplace bundle."""
from pathlib import Path
import hashlib
import json
import shutil
from zipfile import ZipFile, ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]
NAME='dseny-inspections'
PLUGIN=ROOT/'plugins'/NAME

def build(destination=None):
    runtime=PLUGIN/'runtime'
    runtime.mkdir(exist_ok=True)
    for name in ('report_agent.py','requirements.txt'):
        shutil.copy2(ROOT/name,runtime/name)
    (runtime/'templates').mkdir(exist_ok=True)
    for path in (ROOT/'templates').glob('*.docx'):
        shutil.copy2(path,runtime/'templates'/path.name)
    checksums={str(path.relative_to(PLUGIN)):hashlib.sha256(path.read_bytes()).hexdigest()
               for path in sorted(runtime.rglob('*')) if path.is_file() and '__pycache__' not in path.parts}
    (PLUGIN/'checksums.json').write_text(json.dumps(checksums,indent=2)+'\n')
    dist=Path(destination) if destination else ROOT/'dist'
    dist.mkdir(parents=True,exist_ok=True)
    package=dist/'DSENY-Inspection-Plugin.zip'
    with ZipFile(package,'w',ZIP_DEFLATED) as archive:
        for path in sorted(PLUGIN.rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts:
                archive.write(path,Path('plugins')/NAME/path.relative_to(PLUGIN))
        marketplace={'name':'dseny-local','interface':{'displayName':'DSENY private plugins'},
          'plugins':[{'name':NAME,'source':{'source':'local','path':'./plugins/'+NAME},
                      'policy':{'installation':'AVAILABLE','authentication':'ON_INSTALL'},'category':'Productivity'}]}
        archive.writestr('.agents/plugins/marketplace.json',json.dumps(marketplace,indent=2))
        archive.writestr('INSTALL.txt',(PLUGIN/'README.md').read_text())
    print(package)
    return package

if __name__=='__main__': build()

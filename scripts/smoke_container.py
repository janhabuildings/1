"""Validate the built image with private HTTP calls, then remove only our container/volume."""
import argparse
import os
import secrets
import subprocess
import uuid

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--image',default='jbi-inspections:local')
parser.add_argument('--docker-config')
parser.add_argument('--memory',default='512m')
args=parser.parse_args()
docker=['docker']+(['--config',args.docker_config] if args.docker_config else [])
name='jbi-smoke-'+uuid.uuid4().hex[:12]
volume=name+'-data'
env=dict(os.environ,INSPECTION_API_TOKEN=secrets.token_urlsafe(32))
check=r'''
import json,os,time,urllib.request
base='http://127.0.0.1:8000'
print('Container check: waiting for backend',flush=True)
for _ in range(100):
 try:
  with urllib.request.urlopen(base+'/health',timeout=1) as r:
   if json.load(r)['status']=='ok': break
 except OSError: time.sleep(.1)
else: raise RuntimeError('Container did not become ready')
with urllib.request.urlopen(base+'/',timeout=10) as response:
 assert b'JBI Inspection Workspace' in response.read()
 assert response.headers['Cache-Control']=='no-store'
with urllib.request.urlopen(base+'/web/app.js',timeout=10) as response:
 assert os.environ['INSPECTION_API_TOKEN'].encode() not in response.read()
headers={'Authorization':'Bearer '+os.environ['INSPECTION_API_TOKEN'],'Content-Type':'application/json'}
def call(path,obj=None):
 req=urllib.request.Request(base+path,headers=headers,data=json.dumps(obj).encode() if obj is not None else None)
 with urllib.request.urlopen(req,timeout=120) as response: return json.load(response)
print('Container check: creating inspection',flush=True)
fixture=json.load(open('/app/plugins/dseny-inspections/references/input-example.json'))
record=call('/inspections',{'title':'Container fixture','inspection_date':'2026-10-15','reports':fixture['reports']})
print('Container check: generating reports',flush=True)
result=call('/inspections/'+record['id']+'/reports',{})
assert all(r['status']=='local_draft_generated' for r in result['reports']),result['reports']
pdf=next(a for a in result['artifacts'] if a['mime']=='application/pdf')
with urllib.request.urlopen(urllib.request.Request(base+'/artifacts/'+pdf['id'],headers=headers),timeout=10) as response:
 assert response.read().startswith(b'%PDF-')
assert os.getuid()==10001
print('Container smoke passed: non-root startup, writable volume, authenticated inspection creation, real HTML/PDF generation and protected PDF download.')
'''
try:
 subprocess.run(docker+['run','--detach','--name',name,'--memory',args.memory,'--env','INSPECTION_API_TOKEN',
                        '--mount',f'type=volume,src={volume},dst=/var/data',args.image],env=env,check=True,capture_output=True,text=True)
 completed=subprocess.run(docker+['exec','-i',name,'python','-'],input=check,text=True)
 if completed.returncode:
  subprocess.run(docker+['logs','--tail','30',name])
  subprocess.run(docker+['inspect','--format','{{json .State}}',name])
  raise RuntimeError('Container smoke failed with exit '+str(completed.returncode))
finally:
 subprocess.run(docker+['rm','--force',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 subprocess.run(docker+['volume','rm',volume],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

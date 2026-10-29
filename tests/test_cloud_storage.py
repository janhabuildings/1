import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

import httpx
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.core import Settings
from backend.cloud_storage import CloudStorage,CloudStorageError

TOKEN='fixture-cloud-token-not-a-real-secret'
HEADERS={'Authorization':'Bearer '+TOKEN}

class MemoryGateway:
    def __init__(self):
        self.revision=0;self.last='';self.rows={};self.files={};self.blobs={};self.gc=set();self.reject=False;self.lose_commit_response=False
    def handle(self,request):
        if request.headers.get('Authorization')!='Bearer '+TOKEN:return httpx.Response(401)
        path=request.url.path
        if path=='/status':return httpx.Response(200,json={'version':1,'revision':self.revision,'last_commit':self.last})
        if path=='/state':
            kind=request.url.params['kind'];after=request.url.params.get('after','');source=self.rows if kind=='rows' else self.files
            items=[dict(key=k,value=v) if kind=='rows' else dict(path=k,**v) for k,v in sorted(source.items()) if k>after][:20]
            return httpx.Response(200,json={'items':items})
        if self.reject:return httpx.Response(503,json={'error':'fixture outage'})
        if path.startswith('/blobs/'):
            key=path.split('/')[-1];checksum=key.split('-')[0]
            if request.method=='PUT':
                assert hashlib.sha256(request.content).hexdigest()==checksum
                self.blobs[key]=request.content;return httpx.Response(200,json={'stored':True})
            if key not in self.blobs:return httpx.Response(404)
            return httpx.Response(200,content=self.blobs[key])
        if path=='/gc':
            used={v['sha']+'-'+v['object'] for v in self.files.values()}
            for checksum in self.gc-used:self.blobs.pop(checksum,None)
            self.gc.clear();return httpx.Response(200,json={'pending':0})
        if path=='/commit':
            data=json.loads(request.content)
            if data['commit_id']==self.last:return httpx.Response(200,json={'revision':self.revision})
            if data['expected']!=self.revision:return httpx.Response(409)
            for key in data['deletes']:self.rows.pop(key,None)
            for row in data['rows']:self.rows[row['key']]=row['value']
            for key in data['removed_files']:
                if key in self.files:self.gc.add(self.files[key]['sha']+'-'+self.files.pop(key)['object'])
            for file in data['files']:
                if file['path'] in self.files:self.gc.add(self.files[file['path']]['sha']+'-'+self.files[file['path']]['object'])
                assert file['sha']+'-'+file['object'] in self.blobs
                self.files[file['path']]={k:file[k] for k in ('sha','size','object')}
            self.revision+=1;self.last=data['commit_id']
            if self.lose_commit_response:
                self.lose_commit_response=False;raise httpx.ReadError('fixture lost response')
            return httpx.Response(200,json={'revision':self.revision})
        return httpx.Response(404)
    def cloud(self,store,token):
        client=httpx.Client(base_url='https://fixture.test/',headers=HEADERS,transport=httpx.MockTransport(self.handle))
        return CloudStorage(store,'https://fixture.test',token,client=client)

class DurableStorage(unittest.TestCase):
    def setUp(self):self.gateway=MemoryGateway();self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def app(self,name):
        with patch('backend.cloud_storage.CloudStorage.from_env',side_effect=self.gateway.cloud):
            return create_app(Settings(self.base/name,TOKEN))
    def save(self,client,identity=None,title='Cloud visit'):
        identity=identity or str(uuid.uuid4())
        response=client.put('/inspections/'+identity,headers=HEADERS,json={'title':title,'inspection_date':'2026-10-28','attendees':[{'name':'Inspector draft','company':'Example','title':'PE'}]})
        return identity,response

    def test_records_media_and_generated_files_reopen_from_an_empty_new_server(self):
        first=self.app('first')
        with TestClient(first) as client:
            identity,response=self.save(client);self.assertEqual(response.status_code,200)
            image=b'\xff\xd8\xff fixture photo'
            media=client.post('/inspections/'+identity+'/media?kind=photo&filename=photo.jpg',headers={**HEADERS,'Content-Type':'image/jpeg'},content=image)
            self.assertEqual(media.status_code,201);media_id=media.json()['id']
            path=first.state.store.root/'reports'/'run'/'SF'/'report.pdf';path.parent.mkdir(parents=True);path.write_bytes(b'%PDF-fixture')
            artifact=str(uuid.uuid4())
            with first.state.store.connect() as db:db.execute('INSERT INTO artifacts VALUES (?,?,?,?,?)',(artifact,identity,path.name,'application/pdf',str(path)))
            _,response=self.save(client,identity);self.assertEqual(response.status_code,200)
        second=self.app('second')
        with TestClient(second) as client:
            record=client.get('/inspections/'+identity,headers=HEADERS).json()
            self.assertEqual(record['title'],'Cloud visit');self.assertEqual(record['attendees'][0]['name'],'Inspector draft')
            self.assertEqual(client.get('/media/'+media_id,headers=HEADERS).content,image)
            self.assertEqual(client.get('/artifacts/'+artifact,headers=HEADERS).content,b'%PDF-fixture')
            self.assertEqual(client.get('/capabilities',headers=HEADERS).json()['storage'],'cloudflare')
            self.assertEqual(client.get('/inspections',headers={}).status_code,401)

    def test_cloud_failure_is_not_reported_as_saved_and_retry_is_idempotent(self):
        app=self.app('failure')
        with TestClient(app) as client:
            self.gateway.reject=True
            identity,response=self.save(client);self.assertEqual(response.status_code,503)
            self.assertFalse(any('"table":"inspections"' in v for v in self.gateway.rows.values()))
            self.gateway.reject=False;self.gateway.lose_commit_response=True
            _,response=self.save(client,identity);self.assertEqual(response.status_code,200)
            self.assertEqual(len([v for v in self.gateway.rows.values() if json.loads(v)['table']=='inspections']),1)

    def test_delete_removes_photo_from_r2_and_stays_deleted_after_restart(self):
        app=self.app('delete')
        with TestClient(app) as client:
            identity,_=self.save(client);image=b'\xff\xd8\xff cloud delete fixture'
            result=client.post('/inspections/'+identity+'/media?kind=photo&filename=photo.jpg',headers={**HEADERS,'Content-Type':'image/jpeg'},content=image)
            media_id=result.json()['id'];checksum=hashlib.sha256(image).hexdigest()
            self.assertTrue(any(key.startswith(checksum+'-') for key in self.gateway.blobs))
            self.assertEqual(client.delete('/media/'+media_id,headers=HEADERS).status_code,200)
            self.assertFalse(any(key.startswith(checksum+'-') for key in self.gateway.blobs))
        with TestClient(self.app('delete-restored')) as client:
            self.assertEqual(client.get('/inspections/'+identity+'/media',headers=HEADERS).json(),[])
            self.assertEqual(client.get('/media/'+media_id,headers=HEADERS).status_code,404)

    def test_stale_server_cannot_overwrite_newer_saved_record(self):
        first=self.app('a');second=self.app('b')
        with TestClient(first) as a,TestClient(second) as b:
            identity,response=self.save(a,title='Newer saved value');self.assertEqual(response.status_code,200)
            _,response=self.save(b,identity,title='Stale overwrite');self.assertEqual(response.status_code,409)
            self.assertEqual(b.get('/inspections/'+identity,headers=HEADERS).json()['title'],'Newer saved value')

    def test_invalid_cloud_url_and_restore_path_are_rejected(self):
        app=self.app('paths');cloud=app.state.cloud
        for path in ['../escape','/tmp/outside']:
            with self.assertRaises(CloudStorageError):cloud.path(path)
        with self.assertRaises(CloudStorageError):CloudStorage(app.state.store,'http://not-https.test',TOKEN)

    def test_unmodified_media_is_not_rehashed_on_every_edit(self):
        app=self.app('hash-cache')
        with TestClient(app) as client:
            identity,_=self.save(client);image=b'\xff\xd8\xff cached image'
            media=client.post('/inspections/'+identity+'/media?kind=photo&filename=photo.jpg',headers={**HEADERS,'Content-Type':'image/jpeg'},content=image).json()
            real_read=Path.read_bytes;seen=[]
            def read(path):
                seen.append(path)
                return real_read(path)
            with patch.object(Path,'read_bytes',read):
                _,result=self.save(client,identity,title='Metadata edit')
            self.assertEqual(result.status_code,200)
            self.assertFalse(any(path.parent.name=='media' for path in seen))

    def test_multiple_pages_of_records_restore(self):
        with TestClient(self.app('many')) as client:
            for i in range(25):
                _,response=self.save(client,title='Visit '+str(i));self.assertEqual(response.status_code,200)
        with TestClient(self.app('many-restored')) as client:
            self.assertEqual(len(client.get('/inspections',headers=HEADERS).json()),25)

"""Permissions across accounts, evidence, exports, stamps and durable restore."""
import json
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid
from PIL import Image
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.core import Settings
from tests.test_cloud_storage import MemoryGateway,TOKEN

OWNER={'Authorization':'Bearer '+TOKEN}

def headers(key):return {'Authorization':'Bearer '+key}

class WorkspaceAccess(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.app=create_app(Settings(Path(self.temp.name),TOKEN))
        self.client=TestClient(self.app);self.client.__enter__();self.addCleanup(self.client.__exit__,None,None,None)
        self.a=self.user('Alice');self.b=self.user('Bob')
    def user(self,name,role='inspector'):
        response=self.client.post('/workspace/users',headers=OWNER,json={'name':name,'email':name.lower()+'@example.com','role':role})
        self.assertEqual(response.status_code,201,response.text);return response.json()
    def create(self,who=OWNER):
        response=self.client.post('/inspections',headers=who,json={'title':'Sample inspection','inspection_date':'2026-11-24'})
        self.assertEqual(response.status_code,201,response.text);return response.json()
    def assign(self,record,*users):
        return self.client.put('/inspections/'+record['id']+'/assignments',headers=OWNER,json={'assigned_user_ids':[u['id'] for u in users]})
    def test_legacy_records_remain_admin_only_until_assigned(self):
        record=self.create()
        with self.app.state.store.connect() as db:db.execute('DELETE FROM inspection_access')
        self.assertEqual(self.client.get('/inspections',headers=headers(self.a['access_key'])).json(),[])
        self.assertEqual(self.client.get('/inspections/'+record['id'],headers=headers(self.a['access_key'])).status_code,404)
        self.assertEqual(self.assign(record,self.a).status_code,200)
        self.assertEqual(len(self.client.get('/inspections',headers=headers(self.a['access_key'])).json()),1)
        self.assertEqual(len(self.client.get('/inspections',headers=OWNER).json()),1)
    def test_creation_and_assignments_cannot_be_forged(self):
        record=self.create(headers(self.a['access_key']))
        for method in ('get','put','delete'):
            response=getattr(self.client,method)('/inspections/'+record['id'],headers=headers(self.b['access_key']),**({'json':record} if method=='put' else {}))
            self.assertEqual(response.status_code,404)
        self.assertEqual(self.client.put('/inspections/'+record['id']+'/assignments',headers=headers(self.a['access_key']),json={'assigned_user_ids':[self.b['id']]}).status_code,403)
        self.assertEqual(self.assign(record,self.a,self.b).status_code,200)
        self.assertEqual(self.client.get('/inspections/'+record['id'],headers=headers(self.b['access_key'])).status_code,200)
    def test_stale_updates_conflict_and_reassignment_revokes_access(self):
        record=self.create(headers(self.a['access_key']));self.assign(record,self.a,self.b)
        first=self.client.put('/inspections/'+record['id'],headers=headers(self.a['access_key']),json={**record,'notes':'Alice edit'})
        self.assertEqual(first.status_code,200,first.text)
        self.assertEqual(self.client.put('/inspections/'+record['id'],headers=headers(self.b['access_key']),json={**record,'notes':'Stale edit'}).status_code,409)
        self.assertEqual(self.client.get('/inspections/'+record['id'],headers=OWNER).json()['notes'],'Alice edit')
        self.assertEqual(self.assign(record,self.b).status_code,200)
        state=self.client.get('/sync/deletions',headers=headers(self.a['access_key'])).json()
        self.assertEqual(state['revoked_inspections'],[record['id']])
        self.assertEqual(self.client.get('/inspections/'+record['id']+'/media',headers=headers(self.a['access_key'])).status_code,404)
        self.assign(record,self.a)
        self.assertEqual(self.client.get('/sync/deletions',headers=headers(self.a['access_key'])).json()['revoked_inspections'],[])
    def test_direct_file_ids_and_mutations_are_authorized(self):
        record=self.create(headers(self.a['access_key']));a=headers(self.a['access_key']);b=headers(self.b['access_key'])
        photo=self.client.post('/inspections/'+record['id']+'/media?kind=photo',headers={**a,'Content-Type':'image/jpeg'},content=b'\xff\xd8\xff sample').json()
        path=self.app.state.store.root/'reports'/'sample.pdf';path.write_bytes(b'%PDF-test');identity=str(uuid.uuid4())
        with self.app.state.store.connect() as db:db.execute('INSERT INTO artifacts VALUES (?,?,?,?,?)',(identity,record['id'],'sample.pdf','application/pdf',str(path)))
        for root,identity in [('media',photo['id']),('artifacts',identity)]:
            self.assertEqual(self.client.get('/'+root+'/'+identity,headers=b).status_code,404)
            self.assertEqual(self.client.delete('/'+root+'/'+identity,headers=b).status_code,404)
            self.assertEqual(self.client.get('/'+root+'/'+identity,headers=a).status_code,200)
        self.assertEqual(self.client.post('/templates',headers=b).status_code,403)
        self.assertEqual(self.client.post('/saved-rows/import-history',headers=b).status_code,403)
    def test_keys_are_hashed_rotatable_revocable_and_not_in_lists(self):
        a=headers(self.a['access_key'])
        self.assertEqual(self.client.get('/workspace/users',headers=a).status_code,403)
        listing=self.client.get('/workspace/users',headers=OWNER).text
        self.assertNotIn('access_key',listing);self.assertNotIn('key_hash',listing)
        self.assertNotIn(self.a['access_key'],self.app.state.store.database.read_bytes().decode(errors='ignore'))
        replacement=self.client.patch('/workspace/users/'+self.a['id'],headers=OWNER,json={'rotate_key':True}).json()
        self.assertEqual(self.client.get('/workspace/me',headers=a).status_code,401)
        a=headers(replacement['access_key']);self.assertEqual(self.client.get('/workspace/me',headers=a).status_code,200)
        self.client.patch('/workspace/users/'+self.a['id'],headers=OWNER,json={'active':False})
        self.assertEqual(self.client.get('/workspace/me',headers=a).status_code,401)
        events=self.client.get('/workspace/audit',headers=OWNER).text;self.assertNotIn(replacement['access_key'],events)
    def test_stamps_are_private_even_to_other_admins(self):
        image=BytesIO();Image.new('RGB',(8,8),'white').save(image,format='PNG')
        def upload(who):return self.client.post('/signing-assets?owner=Sample%20Engineer',headers={**who,'Content-Type':'image/png'},content=image.getvalue())
        a=headers(self.a['access_key']);b=headers(self.b['access_key']);asset=upload(a).json()
        self.assertEqual(self.client.get('/signing-assets',headers=b).json(),[])
        self.assertEqual(self.client.get('/signing-assets',headers=OWNER).json(),[])
        self.assertEqual(self.client.delete('/signing-assets/'+asset['id'],headers=OWNER).status_code,404)
        other=upload(b).json();self.assertNotEqual(other['id'],asset['id'])
        self.assertEqual(upload(a).json()['id'],asset['id'])
        self.assertEqual(self.client.delete('/signing-assets/'+asset['id'],headers=a).status_code,200)
    def test_shared_suggestions_visible_to_company_users(self):
        a=headers(self.a['access_key']);b=headers(self.b['access_key'])
        response=self.client.post('/saved-rows',headers=a,json={'kind':'company','company':'Sample Company'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertIn('Sample Company',self.client.get('/saved-rows',headers=b).text)

class WorkspaceCloud(unittest.TestCase):
    def test_users_assignments_and_key_revocation_survive_cloud_restore(self):
        gateway=MemoryGateway()
        with tempfile.TemporaryDirectory() as folder,patch('backend.cloud_storage.CloudStorage.from_env',side_effect=gateway.cloud):
            with TestClient(create_app(Settings(Path(folder)/'one',TOKEN))) as client:
                user=client.post('/workspace/users',headers=OWNER,json={'name':'Inspector','email':'inspector@example.com'}).json()
                record=client.post('/inspections',headers=headers(user['access_key']),json={'title':'Cloud inspection','inspection_date':'2026-11-24'}).json()
            with TestClient(create_app(Settings(Path(folder)/'two',TOKEN))) as client:
                self.assertEqual(client.get('/inspections',headers=headers(user['access_key'])).json()[0]['id'],record['id'])
                client.patch('/workspace/users/'+user['id'],headers=OWNER,json={'active':False})
            with TestClient(create_app(Settings(Path(folder)/'three',TOKEN))) as client:
                self.assertEqual(client.get('/workspace/me',headers=headers(user['access_key'])).status_code,401)
                self.assertEqual(len(client.get('/inspections',headers=OWNER).json()),1)

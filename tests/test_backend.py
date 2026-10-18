from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, AsyncMock

from fastapi.testclient import TestClient
from backend.app import create_app
from backend.core import Settings,Store,calendar_candidates,put_code,search_codes,validate_code

ROOT=Path(__file__).resolve().parents[1]
TOKEN='test-only-token-not-a-real-credential'
HEADERS={'Authorization':'Bearer '+TOKEN}

class Backend(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.app=create_app(Settings(Path(self.temp.name),TOKEN,office_bin=str(ROOT/'.tools/bin/libreoffice')))
        self.client=TestClient(self.app)
    def tearDown(self): self.client.close();self.temp.cleanup()
    def inspection(self):
        response=self.client.post('/inspections',headers=HEADERS,json={'title':'Test inspection','project':'TEST',
                           'inspection_date':'2026-10-15','notes':'Fixture only'})
        self.assertEqual(response.status_code,201)
        return response.json()
    def test_auth_and_missing_configuration(self):
        self.assertEqual(self.client.get('/health').status_code,200)
        self.assertEqual(self.client.get('/inspections').status_code,401)
        self.assertEqual(self.client.get('/inspections',headers={'Authorization':'Bearer incorrect'}).status_code,401)
        with tempfile.TemporaryDirectory() as tmp,TestClient(create_app(Settings(Path(tmp),''))) as client:
            self.assertEqual(client.get('/inspections').status_code,503)
    def test_offline_first_put_is_idempotent_and_persistent(self):
        import uuid
        identity=str(uuid.uuid4())
        payload={'title':'Offline visit','inspection_date':'2026-10-15','transcript':'Inspector notes'}
        for _ in range(2):
            r=self.client.put('/inspections/'+identity,headers=HEADERS,json=payload)
            self.assertEqual(r.status_code,200)
        self.assertEqual(len(self.client.get('/inspections',headers=HEADERS).json()),1)
        self.assertEqual(Store(Path(self.temp.name)).get(identity)['transcript'],'Inspector notes')
        self.assertEqual(self.client.put('/inspections/not-a-uuid',headers=HEADERS,json=payload).status_code,422)
    def test_media_roundtrip_dedup_and_ownership(self):
        import uuid
        inspection=self.inspection();asset=str(uuid.uuid4());data=b'\xff\xd8\xffTEST FIXTURE'
        headers=dict(HEADERS,**{'Content-Type':'image/jpeg','X-Asset-ID':asset})
        for _ in range(2):
            response=self.client.post('/inspections/'+inspection['id']+'/media?kind=photo&filename=../../picture.jpg',headers=headers,content=data)
            self.assertEqual(response.status_code,201)
        listed=self.client.get('/inspections/'+inspection['id']+'/media',headers=HEADERS).json()
        self.assertEqual(len(listed),1);self.assertEqual(listed[0]['filename'],'picture.jpg')
        self.assertEqual(self.client.get('/media/'+asset,headers=HEADERS).content,data)
        self.assertEqual(self.client.get('/media/'+asset).status_code,401)
        second=self.inspection()
        self.assertEqual(self.client.post('/inspections/'+second['id']+'/media?kind=photo',headers=headers,content=data).status_code,409)
        self.assertEqual(self.client.post('/inspections/'+inspection['id']+'/media?kind=photo',headers=headers,content=b'not a photo').status_code,415)
        updated=self.client.put('/media/'+asset,headers=HEADERS,json={'note':'North facade','equipment':'SF'})
        self.assertEqual(updated.status_code,200)
        self.assertEqual(self.client.get('/inspections/'+inspection['id']+'/media',headers=HEADERS).json()[0]['equipment'],'SF')
    def test_calendar_does_not_infer_result(self):
        text='''2026-10-15 TEST (ALT) Sidewalk Shed-VII-Inspection-No OIs
2026-10-15 TEST (ALT) Supported Scaffold-VIII-Inspection-OIs
Client:
Fixture Contractor
Project:
TEST
Request date:
10/08/2026
Inspected on:
10/15/2026
Permit#:
M00981440-I1 SH
M00981443-I1 SF
'''
        result=self.client.post('/calendar/extract',headers=HEADERS,json={'text':text}).json()
        self.assertEqual(result['fields']['inspection_date'],'2026-10-15')
        self.assertEqual(result['equipment'][0]['permit'],'M00981440-I1')
        self.assertEqual(result['equipment'][1]['inspection_code'],'VIII')
        self.assertFalse(result['confirmed'])
        self.assertNotIn('status',result['equipment'][0])
    def test_ai_requires_consent_and_configuration(self):
        item=self.inspection()
        path='/inspections/'+item['id']+'/analyze'
        self.assertEqual(self.client.post(path,headers=HEADERS,json={}).status_code,422)
        self.assertEqual(self.client.post(path,headers=HEADERS,json={'consent':True}).status_code,503)
        caps=self.client.get('/capabilities',headers=HEADERS).json()
        self.assertFalse(caps['gmail_direct_drafting'])
    def test_ai_suggestions_are_review_only_and_unknown_photo_refs_removed(self):
        import httpx
        self.app.state.settings.ai_key='fixture-only-not-a-key'
        item=self.inspection()
        put_code(self.app.state.store,{'id':'test-reference','agency':'OSHA','section':'TEST-FIXTURE',
            'title':'Test reference','text':'SYNTHETIC fixture only; not a regulation.',
            'url':'https://www.osha.gov/laws-regs','effective_from':'2026-01-01','verified':True})
        provider=AsyncMock()
        provider.__aenter__.return_value=provider
        provider.post.return_value=httpx.Response(200,request=httpx.Request('POST','https://api.openai.com/v1/chat/completions'),
          json={'choices':[{'message':{'content':json.dumps({'suggested_findings':[{'equipment':'SF',
               'observation':'Test observation','location':'North','suggested_action':'Test action','photo_id':'not-provided',
               'references':[{'reference_id':'invented','quote':'unsupported'},
                             {'reference_id':'test-reference','quote':'SYNTHETIC fixture only'}]}]})}}]})
        with patch('backend.app.httpx.AsyncClient',return_value=provider):
            result=self.client.post('/inspections/'+item['id']+'/analyze',headers=HEADERS,json={'consent':True})
        self.assertEqual(result.status_code,200,result.text)
        self.assertFalse(result.json()['applied_to_report'])
        self.assertIsNone(result.json()['suggestions']['suggested_findings'][0]['photo_id'])
        citations=result.json()['suggestions']['suggested_findings'][0]['references']
        self.assertEqual(len(citations),1)
        self.assertEqual(citations[0]['section'],'TEST-FIXTURE')
        self.assertEqual(citations[0]['url'],'https://www.osha.gov/laws-regs')
        self.assertEqual(self.client.get('/inspections/'+item['id'],headers=HEADERS).json()['reports'],[])

    def test_invalid_nested_report_is_rejected(self):
        item=self.inspection();item['reports']=[{'equipment':'SF','attendees':123}]
        self.assertEqual(self.client.put('/inspections/'+item['id'],headers=HEADERS,json=item).status_code,422)

    def test_report_exports_real_files_and_enforces_auth(self):
        if not (ROOT/'.tools/bin/libreoffice').is_file(): self.skipTest('LibreOffice not available')
        fixture=json.loads((ROOT/'plugins/dseny-inspections/references/input-example.json').read_text())
        item=self.inspection();item['reports']=fixture['reports']
        self.client.put('/inspections/'+item['id'],headers=HEADERS,json=item)
        response=self.client.post('/inspections/'+item['id']+'/reports',headers=HEADERS,json={})
        self.assertEqual(response.status_code,200,response.text)
        body=response.json();self.assertFalse(body['mailbox_drafts_created'])
        self.assertTrue(all(r['status']=='local_draft_generated' for r in body['reports']))
        pdf=next(a for a in body['artifacts'] if a['mime']=='application/pdf')
        self.assertEqual(pdf['equipment'],'SH')
        self.assertTrue(self.client.get('/artifacts/'+pdf['id'],headers=HEADERS).content.startswith(b'%PDF-'))
        self.assertEqual(self.client.get('/artifacts/'+pdf['id']).status_code,401)

class ReferenceIndex(unittest.TestCase):
    def record(self,**updates):
        # Synthetic test fixtures, never distributed as actual regulatory text.
        value={'agency':'OSHA','section':'TEST-FIXTURE','title':'Test scaffold reference',
               'text':'SYNTHETIC TEST ONLY: scaffold platform edge toeboard fixture.',
               'url':'https://www.osha.gov/laws-regs','effective_from':'2026-01-01',
               'verified':True,'embedding':[1.0,0.0],'model':'test-model'}
        value.update(updates);return value
    def test_hybrid_versioned_verified_retrieval_and_portability(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp)
            put_code(store,self.record())
            put_code(store,self.record(id='future',effective_from='2027-01-01'))
            put_code(store,self.record(id='unverified',verified=False))
            put_code(store,self.record(id='expired',effective_from='2025-01-01',effective_to='2025-12-31'))
            results=search_codes(store,'toeboard','2026-10-15',[1.0,0.0],'test-model')
            self.assertEqual(len(results),1)
            self.assertEqual(results[0]['retrieval'],'hybrid')
            self.assertNotIn('embedding',results[0])
            self.assertIn('digest',results[0])
            self.assertEqual(search_codes(Store(tmp),'toeboard','2026-10-15')[0]['retrieval'],'keyword')
            self.assertEqual(search_codes(store,'no lexical overlap','2026-10-15',[1.0,0.0],'different-model'),[])
    def test_portable_index_merge_does_not_replace_inspections(self):
        import argparse,asyncio
        from backend.ingest_codes import run
        with tempfile.TemporaryDirectory() as source,tempfile.TemporaryDirectory() as dest:
            put_code(Store(source),self.record())
            target=Store(dest);target.save({'id':'retain-me','title':'Existing inspection'})
            args=argparse.Namespace(input=None,index=Path(source)/'inspections.sqlite3',data_dir=Path(dest),embed=False,require_verified=True)
            asyncio.run(run(args))
            self.assertEqual(target.get('retain-me')['title'],'Existing inspection')
            self.assertEqual(len(search_codes(target,'toeboard','2026-10-15')),1)

    def test_invalid_sources_dates_and_vectors_rejected(self):
        for changes in [{'url':'https://osha.gov.attacker.example/code'}, {'effective_to':'2025-01-01'},
                        {'embedding':[float('nan')]},{'agency':'unknown'}]:
            with self.subTest(changes=changes),self.assertRaises(ValueError): validate_code(self.record(**changes))

if __name__=='__main__': unittest.main()

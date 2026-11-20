import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock,patch
import httpx
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.core import Settings

class SavedDrafting(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.app=create_app(Settings(Path(self.temp.name),'fixture-token',ai_key='fixture-key'))
        self.client=TestClient(self.app);self.headers={'Authorization':'Bearer fixture-token'}
    def tearDown(self):self.client.close();self.temp.cleanup()
    def save(self,**row):
        result=self.client.post('/saved-rows',headers=self.headers,json=row);self.assertEqual(result.status_code,200,result.text);return result.json()
    def test_saved_rows_auth_dedupe_update_delete_and_restart(self):
        self.assertEqual(self.client.get('/saved-rows').status_code,401)
        row=self.save(kind='attendee',name='Jane Smith',company='ACME',title='Safety Inspector')
        again=self.save(kind='attendee',name='jane smith',company='acme',title='safety inspector');self.assertEqual(row['id'],again['id'])
        self.assertEqual(self.client.post('/saved-rows',headers=self.headers,json={'kind':'open_item'}).status_code,422)
        with TestClient(create_app(Settings(Path(self.temp.name),'fixture-token'))) as client:self.assertEqual(len(client.get('/saved-rows',headers=self.headers).json()),1)
        self.client.delete('/saved-rows/'+row['id'],headers=self.headers);self.assertEqual(self.client.get('/saved-rows',headers=self.headers).json(),[])
    def analyze(self,text,draft):
        item=self.client.post('/inspections',headers=self.headers,json={'title':'Fixture','inspection_date':'2026-11-20','transcript':text}).json()
        path='/inspections/'+item['id']+'/transcript-draft'
        self.assertEqual(self.client.post(path,headers=self.headers,json={}).status_code,422)
        provider=AsyncMock();provider.__aenter__.return_value=provider
        provider.post.return_value=httpx.Response(200,request=httpx.Request('POST','https://api.openai.com/v1/chat/completions'),json={'choices':[{'message':{'content':json.dumps(draft)}}]})
        with patch('backend.app.httpx.AsyncClient',return_value=provider):result=self.client.post(path,headers=self.headers,json={'consent':True})
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(self.client.get('/inspections/'+item['id'],headers=self.headers).json()['reports'],[])
        self.assertFalse(result.json()['applied_to_report']);return result.json()['draft']
    def test_exact_attendee_match_fills_missing_saved_fields_and_removes_fabricated_quote(self):
        saved=self.save(kind='attendee',name='Jane Smith',company='ACME',title='Safety Inspector')
        draft=self.analyze('Jane Smith is here.',{'attendees':[{'name':'Jane Smith','source_quote':'Jane Smith'}], 'facts':[{'field':'client','value':'Fake','source_quote':'never said'}]})
        person=draft['attendees'][0];self.assertEqual(person['company'],'ACME');self.assertEqual(person['matched_saved_id'],saved['id']);self.assertEqual(draft['facts'],[])
    def test_fuzzy_match_suggests_without_silently_filling_and_ambiguous_exact_stays_unmatched(self):
        self.save(kind='attendee',name='Jane Smith',company='ACME');self.save(kind='attendee',name='Jane Smith',company='Other')
        result=self.analyze('Jane Smith and Jaine Smith.',{'attendees':[{'name':'Jane Smith','source_quote':'Jane Smith'},{'name':'Jaine Smith','source_quote':'Jaine Smith'}]})
        for row in result['attendees']:self.assertIsNone(row['matched_saved_id']);self.assertEqual(row['company'],'');self.assertEqual(len(row['saved_matches']),2)
    def test_open_items_match_only_compatible_equipment(self):
        saved=self.save(kind='open_item',equipment='SH',location='North',action='Replace warped panel')
        result=self.analyze('Replace warped panel.',{'open_items':[{'equipment':'unknown','action':'Replace warped panel','source_quote':'Replace warped panel'},{'equipment':'SF','action':'Replace warped panel','source_quote':'Replace warped panel'}]})
        first,other=result['open_items'];self.assertEqual(first['matched_saved_id'],saved['id']);self.assertEqual(first['equipment'],'SH');self.assertEqual(first['location'],'North');self.assertEqual(other['saved_matches'],[])

    def test_company_values_are_separate_and_do_not_store_linked_attendee_cells(self):
        attendee=self.save(kind='attendee',name='Jane Smith',company='ACME',title='Safety Inspector')
        self.assertEqual([row['kind'] for row in self.client.get('/saved-rows',headers=self.headers).json()],['attendee'])
        company=self.save(kind='company',company='ACME',name='Must not be retained',title='PE',equipment='SH',action='Ignore')
        self.assertNotEqual(company['id'],attendee['id'])
        for key in ('name','title','equipment','location','action'):self.assertEqual(company[key],'')
        duplicate=self.save(kind='company',company=' acme ');self.assertEqual(company['id'],duplicate['id'])
        self.client.delete('/saved-rows/'+company['id'],headers=self.headers)
        self.assertEqual(self.client.get('/saved-rows',headers=self.headers).json(),[attendee])

    def test_coded_draft_works_without_ai_key_consent_or_provider_request(self):
        self.app.state.settings.ai_key=''
        saved=self.save(kind='attendee',name='Jane Smith',company='ACME',title='Safety Inspector')
        item=self.client.post('/inspections',headers=self.headers,json={'title':'Coded fixture','inspection_date':'2026-11-20',
            'transcript':'Attendee: Jane Smith. Equipment: Scaffold. Location: North. Action: Install pins.'}).json()
        path='/inspections/'+item['id']+'/transcript-draft/rules'
        self.assertEqual(self.client.post(path).status_code,401)
        with patch('backend.app.httpx.AsyncClient',side_effect=AssertionError('No AI request allowed')):
            result=self.client.post(path,headers=self.headers)
        self.assertEqual(result.status_code,200,result.text);draft=result.json()['draft']
        self.assertEqual(result.json()['method'],'rules');self.assertFalse(result.json()['applied_to_report'])
        self.assertEqual(draft['attendees'][0]['matched_saved_id'],saved['id']);self.assertEqual(draft['attendees'][0]['company'],'ACME')
        self.assertEqual(draft['open_items'][0]['equipment'],'SF')
        self.assertEqual(self.client.get('/inspections/'+item['id'],headers=self.headers).json()['reports'],[])

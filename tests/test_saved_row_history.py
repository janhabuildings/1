import json
from pathlib import Path
import tempfile
import unittest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.core import Store,Settings
from backend.saved_row_history import import_history

HEADERS={'Authorization':'Bearer fixture-token'}
class SavedRowHistory(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def seed(self):
        store=Store(self.root)
        person={'name':'Jane Smith','company':'ACME','title':'Safety Inspector'}
        record={'id':'inspection','title':'Historic visit','inspection_date':'2026-11-20','attendees':[person,{}],
                'reports':[{'equipment':'SH','attendees':[dict(person,name=' Jane  Smith '),{'name':'Report engineer','company':'Example','title':'PE'}],
                            'open_items':[{'location':'North','action':'Replace panel'},{'location':'[Pending confirmation]','action':''}]},
                           {'equipment':'SF','attendees':[person],'open_items':[{'location':'North','action':'Replace panel'}]}]}
        store.save(record);return record
    def test_startup_imports_all_sources_deduplicates_and_preserves_reports(self):
        original=self.seed();app=create_app(Settings(self.root,'fixture-token'))
        with TestClient(app) as client:
            rows=client.get('/saved-rows',headers=HEADERS).json()
            self.assertEqual(len(rows),6)
            self.assertEqual(sum(row['kind']=='attendee' for row in rows),2)
            self.assertEqual({row['equipment'] for row in rows if row['kind']=='open_item'},{'SH','SF'})
            self.assertEqual(app.state.store.get('inspection'),original)
            again=client.post('/saved-rows/import-history',headers=HEADERS).json()
            self.assertEqual(again['attendees_added']+again['open_items_added'],0)
            self.assertEqual(client.post('/saved-rows/import-history').status_code,401)
    def test_deleted_import_stays_deleted_after_restart_but_explicit_import_can_restore(self):
        self.seed()
        with TestClient(create_app(Settings(self.root,'fixture-token'))) as client:
            identity=next(row['id'] for row in client.get('/saved-rows',headers=HEADERS).json() if row['kind']=='attendee')
            client.delete('/saved-rows/'+identity,headers=HEADERS)
        with TestClient(create_app(Settings(self.root,'fixture-token'))) as client:
            self.assertEqual(len(client.get('/saved-rows',headers=HEADERS).json()),5)
            result=client.post('/saved-rows/import-history',headers=HEADERS).json()
            self.assertEqual(result['attendees_added']+result['open_items_added'],1)
    def test_import_preserves_existing_library_spelling_and_partial_rows(self):
        self.seed();app=create_app(Settings(self.root,'fixture-token'))
        with TestClient(app) as client:
            rows=client.get('/saved-rows',headers=HEADERS).json();saved=next(row for row in rows if row['name']=='Jane Smith')
            before=dict(saved)
            result=client.post('/saved-rows/import-history',headers=HEADERS).json()
            self.assertEqual(result['attendees_added'],0)
            self.assertIn(before,client.get('/saved-rows',headers=HEADERS).json())
            app.state.store.save({'id':'partial','attendees':[{'name':'','company':'New agency','title':'New role'}],'reports':[]})
            result=client.post('/saved-rows/import-history',headers=HEADERS).json()
            self.assertEqual(result['attendees_added'],1)

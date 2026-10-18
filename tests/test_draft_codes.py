from pathlib import Path
import tempfile
import unittest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.core import Settings, Store, search_codes
from backend.draft_codes import load, search


class DraftCodesTests(unittest.TestCase):
    def test_uploaded_artifact_and_real_toeboard_retrieval(self):
        data=load()
        self.assertEqual((len(data['records']),data['dimensions']),(951,1536))
        matches=search('toeboard scaffold')
        self.assertTrue(any(r['section'].startswith('3314') for r in matches))
        self.assertTrue(all(r['source_pages'] and r['verified'] is False for r in matches))
        vector=list(data['records'][0]['embedding'])
        self.assertTrue(search('chapter', vector, data['model']))
        with self.assertRaises(ValueError): search('chapter',vector,'different-model')

    def test_sca_vectors_and_library_isolation(self):
        data=load('sca-manual')
        self.assertEqual((len(data['records']),data['dimensions']),(293,1536))
        matches=search('scaffold toeboard',library='sca-manual')
        self.assertTrue(any(r['section']=='11.2' for r in matches))
        self.assertTrue(all(r['agency']=='NYC SCA' for r in matches))
        self.assertTrue(all(r['agency']=='NYC DOB' for r in search('scaffold')))
        vector=list(data['records'][20]['embedding'])
        self.assertTrue(search('scaffold',vector,data['model'],library='sca-manual'))
        with self.assertRaises(ValueError): search('scaffold',library='../outside')

    def test_protected_preview_excluded_from_reviewed_index(self):
        with tempfile.TemporaryDirectory() as directory:
            settings=Settings(Path(directory),'fixture-token')
            with TestClient(create_app(settings)) as client:
                body={'query':'scaffold toeboard','on_date':'2026-10-18'}
                self.assertEqual(client.post('/codes/draft/search',json=body).status_code,401)
                headers={'Authorization':'Bearer fixture-token'}
                response=client.post('/codes/draft/search',headers=headers,json=body)
                self.assertEqual(response.status_code,200)
                self.assertFalse(response.json()['verified'])
                self.assertTrue(response.json()['results'])
                self.assertEqual(search_codes(Store(settings.data_dir),'scaffold','2026-10-18'),[])
                body['library']='sca-manual'
                response=client.post('/codes/draft/search',headers=headers,json=body)
                self.assertEqual(response.status_code,200)
                self.assertIn('2025',response.json()['notice'])
                self.assertTrue(all(r['agency']=='NYC SCA' for r in response.json()['results']))
                body['library']='unknown'
                self.assertEqual(client.post('/codes/draft/search',headers=headers,json=body).status_code,422)
                body['library']='sca-manual'
                body['semantic']=True
                self.assertEqual(client.post('/codes/draft/search',headers=headers,json=body).status_code,503)

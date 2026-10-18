import json as jsonlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
import httpx
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.core import Settings
from backend.draft_codes import load


class PhotoReferenceAnalysis(unittest.TestCase):
    def test_photo_to_vectors_to_validated_citations_without_report_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            settings=Settings(Path(directory),'fixture-token',ai_key='fixture-key')
            app=create_app(settings)
            headers={'Authorization':'Bearer fixture-token'}
            with TestClient(app) as client:
                inspection=client.post('/inspections',headers=headers,json={
                    'title':'Fixture inspection','project':'TEST','inspection_date':'2026-10-18','notes':''}).json()
                identity=inspection['id']
                photo=client.post(f'/inspections/{identity}/media?kind=photo&filename=fixture.png',
                    headers=dict(headers,**{'Content-Type':'image/png'}),content=b'\x89PNG\r\n\x1a\nfixture').json()['id']
                posted=[]
                provider=AsyncMock()
                provider.__aenter__.return_value=provider

                async def post(url,headers,json):
                    posted.append(json)
                    source=jsonlib.loads(json['messages'][1]['content'][0]['text'])
                    if len(posted)==1:
                        self.assertTrue(any(c['type']=='image_url' for c in json['messages'][1]['content']))
                        payload={'suggested_findings':[{'equipment':'SF','observation':'Possible missing toeboard at platform edge',
                            'location':'North platform','photo_id':photo,'uncertainties':['Confirm platform edge is exposed']}],
                            'missing_information':['Confirm platform height']}
                    else:
                        refs=source['retrieved_references']
                        self.assertTrue(any(r['agency']=='NYC DOB' for r in refs))
                        sca=next(r for r in refs if r['agency']=='NYC SCA')
                        payload={'suggested_findings':[{'equipment':'SF','observation':'Possible missing toeboard',
                            'location':'North platform','photo_id':photo,'suggested_action':'Inspector to confirm and correct edge protection',
                            'uncertainties':['Confirm exposed edge'], 'references':[
                                {'reference_id':sca['id'],'quote':sca['text'][:80]},
                                {'reference_id':sca['id'],'quote':'INVENTED RULE TEXT'},
                                {'reference_id':'draft:invented','quote':'unsupported'}]}]}
                    return httpx.Response(200,request=httpx.Request('POST',url),
                        json={'choices':[{'message':{'content':jsonlib.dumps(payload)}}]})

                provider.post.side_effect=post
                vector=next(r['embedding'] for r in load('sca-manual')['records'] if r['chunk']['section']=='11.2')
                with patch('backend.app.httpx.AsyncClient',return_value=provider), patch(
                    'backend.photo_references.embed',new=AsyncMock(return_value=list(vector))) as embedding:
                    result=client.post(f'/inspections/{identity}/analyze',headers=headers,
                        json={'consent':True,'media_ids':[photo]})
                self.assertEqual(result.status_code,200,result.text)
                body=result.json()
                finding=body['suggestions']['suggested_findings'][0]
                self.assertEqual(finding['photo_id'],photo)
                self.assertEqual(len(finding['references']),1)
                citation=finding['references'][0]
                self.assertEqual(citation['agency'],'NYC SCA')
                self.assertFalse(citation['verified'])
                self.assertTrue(citation['source_pages'])
                self.assertTrue(citation['source_sha256'])
                self.assertIsNone(citation['url'])
                self.assertTrue(finding['uncertainties'])
                self.assertIn('Confirm platform height',body['suggestions']['missing_information'])
                self.assertFalse(body['applied_to_report'])
                self.assertEqual(client.get(f'/inspections/{identity}',headers=headers).json()['reports'],[])
                self.assertIn('missing toeboard',embedding.call_args.args[1])
                self.assertEqual(len(posted),2)

    def test_retrieval_failure_returns_uncited_review_suggestions(self):
        with tempfile.TemporaryDirectory() as directory:
            with TestClient(create_app(Settings(Path(directory),'fixture-token',ai_key='fixture-key'))) as client:
                headers={'Authorization':'Bearer fixture-token'}
                identity=client.post('/inspections',headers=headers,json={'title':'Fixture',
                    'project':'TEST','inspection_date':'2026-10-18'}).json()['id']
                provider=AsyncMock();provider.__aenter__.return_value=provider
                provider.post.return_value=httpx.Response(200,request=httpx.Request('POST','https://api.openai.com/v1/chat/completions'),
                    json={'choices':[{'message':{'content':'{"suggested_findings": []}'}}]})
                with patch('backend.app.httpx.AsyncClient',return_value=provider),patch(
                    'backend.photo_references.retrieve',new=AsyncMock(side_effect=ValueError('provider fixture failure'))):
                    response=client.post(f'/inspections/{identity}/analyze',headers=headers,json={'consent':True})
                self.assertEqual(response.status_code,200,response.text)
                self.assertEqual(response.json()['retrieved_references'],[])
                self.assertTrue(any('retrieval failed' in w for w in response.json()['suggestions']['warnings']))

import asyncio
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import httpx
from backend.core import Settings
from backend.embed_staged import build


class DraftEmbeddingTests(unittest.TestCase):
    def test_failure_checkpoint_resume_and_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'source.pdf').write_bytes(b'fixture pdf')
            manifest = {'sha256': hashlib.sha256(b'fixture pdf').hexdigest(),
                        'source_url_verified': False, 'effective_dates_verified': False}
            (root/'manifest.json').write_text(json.dumps(manifest))
            chunks = [{'id': str(i), 'text': f'section {i}', 'source_pages': [i+1],
                       'verified': False, 'effective_from': None, 'parent_sections': ['3301']}
                      for i in range(3)]
            (root/'chunks.review.json').write_text(json.dumps(chunks))
            output = root/'vectors.json'
            settings = Settings(root/'unused-active-db', 'token', ai_key='fixture-key')
            calls = []

            def handler(request):
                texts = json.loads(request.content)['input']
                calls.append(texts)
                if len(calls) == 2:
                    return httpx.Response(429)
                return httpx.Response(200, json={'data': [
                    {'index': i, 'embedding': [1.0, 0.5]} for i in reversed(range(len(texts)))]})

            transport = httpx.MockTransport(handler)
            with self.assertRaisesRegex(ValueError, 'HTTP 429'):
                asyncio.run(build(root, output, settings, 2, transport))
            self.assertEqual(len(json.loads(output.read_text())['records']), 2)
            result = asyncio.run(build(root, output, settings, 2, transport))
            self.assertEqual(calls[-1], ['section 2'])
            self.assertTrue(result['complete'])
            self.assertFalse(result['active_index_updated'])
            self.assertEqual(result['records'][2]['chunk'], chunks[2])
            self.assertFalse(settings.data_dir.exists())
            settings.embedding_model = 'different-model'
            with self.assertRaisesRegex(ValueError, 'different source or model'):
                asyncio.run(build(root, output, settings, 2, transport))

    def test_missing_key_does_not_create_vectors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'source.pdf').write_bytes(b'pdf')
            (root/'manifest.json').write_text(json.dumps({'sha256': hashlib.sha256(b'pdf').hexdigest()}))
            (root/'chunks.review.json').write_text(json.dumps([{'id': '1', 'text': 'code'}]))
            with self.assertRaisesRegex(ValueError, 'AI_API_KEY'):
                asyncio.run(build(root, root/'out.json', Settings(root, 'token')))
            self.assertFalse((root/'out.json').exists())

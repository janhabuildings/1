import re
from pathlib import Path
import unittest
from pypdf import PdfReader
from backend.stage_sca import segment
from backend.stage_pdf import retrieval_chunks


class SCAManualStaging(unittest.TestCase):
    def test_uploaded_manual_full_coverage_and_chapters(self):
        source=Path(__file__).resolve().parents[1]/'code_library/sources/sca-safety-manual-january-2026.pdf'
        pages=[(i+1,p.extract_text() or '') for i,p in enumerate(PdfReader(source).pages)]
        records=segment(pages)
        self.assertEqual(len(pages),155)
        self.assertEqual([r['section'] for r in records if r['section'].isdigit()],[str(i) for i in range(1,22)])
        self.assertEqual(re.sub(r'\s+','',''.join(t for _,t in pages)),
                         re.sub(r'\s+','',''.join(r['text'] for r in records)))
        chunks=[c for c in retrieval_chunks(records) if c['section']!='front-matter']
        self.assertEqual(len(chunks),293)
        self.assertTrue(any(c['section']=='11.2' for c in chunks))
        for chunk in chunks:
            self.assertTrue(chunk['source_pages'])
            self.assertLessEqual(len(chunk['text']),6000)
            self.assertFalse(chunk['verified'])

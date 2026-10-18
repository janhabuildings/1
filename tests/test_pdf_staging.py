import unittest
from backend.stage_pdf import segment_pages,retrieval_chunks

class PDFStaging(unittest.TestCase):
    def test_sections_keep_exceptions_continuations_and_parents(self):
        pages=[(1,'Amendment note\nSECTION BC 3314\nSCAFFOLDS\n3314.1 Scope. Text.\nException: retained.\n3314.1.1 Detail. First page'),
               (2,'Continuation on next page.\n3314.2 Other. Another clause.\n')]
        records=segment_pages(pages)
        detail=next(r for r in records if r['section']=='3314.1.1')
        self.assertEqual(detail['source_pages'],[1,2])
        self.assertEqual(detail['parent_sections'],['3314','3314.1'])
        self.assertIn('First page\nContinuation on next page',detail['text'])
        parent=next(r for r in records if r['section']=='3314.1')
        self.assertIn('Exception: retained.',parent['text'])
        self.assertFalse(parent['verified'])
        self.assertIsNone(parent['effective_from'])
        self.assertEqual(''.join(r['text'] for r in records).replace('\n',''),''.join(t for _,t in pages).replace('\n',''))
    def test_bounded_chunks_retain_offsets_and_page_traceability(self):
        records=segment_pages([(1,'3314.1 Scope.\n'+'Word '*2500),(2,' Continued.\n')])
        chunks=retrieval_chunks(records)
        self.assertGreater(len(chunks),1)
        covered=set()
        for c in chunks:
            self.assertLessEqual(len(c['text']),6000)
            self.assertEqual(c['text'],records[0]['text'][c['character_start']:c['character_end']])
            self.assertTrue(c['source_pages'])
            self.assertTrue(c['not_ready_for_ingestion'])
            covered.update(range(c['character_start'],c['character_end']))
        self.assertEqual(len(covered),len(records[0]['text']))

if __name__=='__main__': unittest.main()

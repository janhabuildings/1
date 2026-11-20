import json
from pathlib import Path
import unittest
from backend.transcript_rules import extract

CASES=json.loads((Path(__file__).resolve().parents[1]/'ios/Tests/coded-transcript-cases.json').read_text())
class TranscriptRules(unittest.TestCase):
    def test_shared_extraction_corpus(self):
        for case in CASES:
            with self.subTest(case=case['name']):
                result=extract(case['text'],case['library'])
                for kind in ('attendees','open_items','facts'):
                    self.assertEqual(len(result[kind]),len(case[kind]),result)
                    for actual,expected in zip(result[kind],case[kind]):
                        self.assertIn(actual['source_quote'],case['text'])
                        for key,value in expected.items():
                            if key=='saved_match_ids':self.assertEqual([row['id'] for row in actual['saved_matches']],value)
                            else:self.assertEqual(actual.get(key),value)
    def test_invalid_dates_and_long_values_do_not_fill(self):
        draft=extract('Request date: 2026-02-30.\nClient: '+('X'*1001))
        self.assertEqual(draft['facts'],[])

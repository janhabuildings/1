from pathlib import Path
import plistlib
import unittest
from xml.etree import ElementTree

ROOT=Path(__file__).resolve().parents[1]/'ios'

class IOSProject(unittest.TestCase):
    def test_project_source_references_and_permissions(self):
        from openstep_parser import OpenStepDecoder
        with (ROOT/'JBIInspections.xcodeproj/project.pbxproj').open() as file:
            project=OpenStepDecoder.ParseFromFile(file)
        objects=project['objects']
        refs=[o['path'] for o in objects.values() if o.get('isa')=='PBXFileReference' and o.get('path','').endswith('.swift')]
        self.assertEqual(set(refs),{p.name for p in (ROOT/'JBIInspections').glob('*.swift')})
        for ref in refs: self.assertTrue((ROOT/'JBIInspections'/ref).is_file())
        info=plistlib.loads((ROOT/'JBIInspections/Info.plist').read_bytes())
        for key in ['NSCameraUsageDescription','NSMicrophoneUsageDescription','NSSpeechRecognitionUsageDescription']:
            self.assertTrue(info[key])
        self.assertNotIn('NSAllowsArbitraryLoads',info['NSAppTransportSecurity'])
        tree=ElementTree.parse(ROOT/'JBIInspections.xcodeproj/xcshareddata/xcschemes/JBIInspections.xcscheme')
        self.assertEqual(tree.getroot().tag,'Scheme')
    def test_attendee_options_cover_the_original_templates(self):
        import json,re
        from docx import Document
        from report_agent import physical_cells
        expected_roles=set();expected_companies=set()
        for path in (ROOT.parent/'templates').glob('*.docx'):
            for table in Document(path).tables:
                if not any('Company Agency' in c.text for c in physical_cells(table.rows[0])):continue
                for row in list(table.rows)[1:]:
                    cells=physical_cells(row)
                    if len(cells)<4:continue
                    if cells[2].text.strip():expected_companies.add(cells[2].text.strip())
                    if cells[3].text.strip():expected_roles.add(cells[3].text.strip())
        source=(ROOT/'JBIInspections/ReportEditor.swift').read_text()
        for field,expected in [('roles',expected_roles),('companies',expected_companies)]:
            values=json.loads(re.search(r'static let '+field+r' = (\[[^\n]+\])',source).group(1))
            self.assertEqual(set(values),expected)

    def test_corrective_action_catalog_matches_original_templates_and_web(self):
        import json
        from scripts.build_action_options import extract_actions
        expected=extract_actions()
        source=(ROOT.parent/'backend/web/action-options.js').read_text().split('const actionSuggestions = ',1)[1].strip().removesuffix(';')
        self.assertEqual(json.loads(source),expected)
        swift=(ROOT/'JBIInspections/CorrectionOptions.swift').read_text()
        for values in expected.values():
            for value in values:self.assertIn(json.dumps(value,ensure_ascii=False),swift)
        self.assertTrue(expected['SF']);self.assertTrue(expected['SH'])
        self.assertNotIn('CUSTOM VERBIAGE',str(expected))

    def test_swift_syntax(self):
        # Parsing is not Apple SDK typechecking or a successful Xcode build.
        from tree_sitter import Language,Parser
        import tree_sitter_swift
        parser=Parser(Language(tree_sitter_swift.language()))
        for path in (ROOT/'JBIInspections').glob('*.swift'):
            with self.subTest(file=path.name):
                root=parser.parse(path.read_bytes()).root_node
                self.assertFalse(root.has_error,str(root))

if __name__=='__main__': unittest.main()

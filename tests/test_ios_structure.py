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

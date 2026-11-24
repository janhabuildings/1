import unittest
import tempfile
from pathlib import Path
from zipfile import ZipFile
from lxml import etree
import report_agent as reports
from backend.templates import sample_report

class ReportEmailPagination(unittest.TestCase):
    def test_calendar_wording_preserved(self):
        body='Dear Client,\n\nEQ inspection report, signed and sealed, provided here. There are no open items.\nSee attached; please print & keep at the jobsite.'
        source='DELETE INSTRUCTIONS\nIF NO OPEN ITEM REPORT:\n\n'+body+'\n\n+=+=+=+=+\nIF OPEN ITEM REPORT:\nDear Client\nWrong alternate.'
        self.assertEqual(reports.no_open_items_email(source),body)
        self.assertIsNone(reports.no_open_items_email('No open items.'))
        self.assertIsNone(reports.no_open_items_email(source+'\nIF NO OPEN ITEM REPORT:\nDear Client, there are no open items. Different.'))

    def test_all_templates_have_dynamic_centered_page_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            for equipment in ('SF','SH','OT'):
                for status in ('OIs','No OIs'):
                    output=Path(folder)/(equipment+status+'.docx')
                    reports.fill_report(sample_report(equipment+'-'+status),output,draft=True)
                    reports.number_report_pages(output)
                    with ZipFile(output) as package:
                        footer=etree.fromstring(package.read('word/jbi-page-footer.xml'))
                        self.assertEqual(footer.xpath('//w:instrText/text()',namespaces=reports.NS),[' PAGE ',' NUMPAGES '])
                        self.assertEqual(footer.xpath('//w:jc/@w:val',namespaces=reports.NS),['center'])
                        self.assertEqual(footer.xpath('//w:t/text()',namespaces=reports.NS),['1',' of ','1'])
                        document=etree.fromstring(package.read('word/document.xml'))
                        self.assertEqual(len(document.findall('.//'+reports.W+'footerReference')),3)
                        settings=etree.fromstring(package.read('word/settings.xml'))
                        self.assertEqual(settings.find(reports.W+'updateFields').get(reports.W+'val'),'true')

    def test_calendar_cover_used_in_plain_and_html_for_every_equipment(self):
        from tests.test_plugin import runner
        from unittest.mock import patch
        from email.parser import BytesParser
        from email import policy
        from lxml.html import fromstring
        body='Dear Client,\n\nThere are no open items. Please print & keep <this> report.\nExact calendar wording.'
        def convert(docx,folder,kind,renderer):
            result=folder/'sample.pdf';result.write_bytes(b'%PDF-sample');return result
        for equipment in ('SF','SH','OT'):
            with tempfile.TemporaryDirectory() as folder,patch.object(runner,'office_convert',side_effect=convert):
                result=runner.generate({'mailbox':{'account':'inspector@example.com'},'reports':[sample_report(equipment+'-No OIs')],
                                        'calendar_text':'IF NO OPEN ITEM REPORT:\n'+body+'\n+=+=+=+=+\nIF OPEN ITEM REPORT:\nWrong wording'},Path(folder)/'out')
                entry=result['reports'][0]
                self.assertEqual(entry['email_wording_source'],'calendar')
                msg=BytesParser(policy=policy.default).parsebytes(Path(entry['eml']).read_bytes())
                self.assertEqual(msg.get_body(preferencelist=('plain',)).get_content().replace('\r\n','\n').rstrip(),body)
                html=msg.get_body(preferencelist=('html',)).get_content()
                self.assertIn('Please print &amp; keep &lt;this&gt; report.',html)
                self.assertNotIn('Wrong wording',html)
                self.assertNotIn('Regards',html)

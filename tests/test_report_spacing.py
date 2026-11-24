from pathlib import Path
import tempfile
import unittest
from docx import Document
from lxml import html
import report_agent
from backend.templates import sample_report
from tests.test_plugin import runner

PREFIX='JBI_ReportGap_'
BASE={'BeforeLetterhead','AfterLetterhead','AfterTitle','AfterSection3'}

class ReportSpacing(unittest.TestCase):
    def check_gaps(self,doc,expected):
        markers=doc.element.body.xpath('.//w:bookmarkStart[starts-with(@w:name,"JBI_ReportGap_")]')
        self.assertEqual({node.get(report_agent.W+'name').removeprefix(PREFIX) for node in markers},expected)
        self.assertEqual(len(markers),len(expected))
        for marker in markers:
            paragraph=marker.getparent();spacing=paragraph.find(report_agent.W+'pPr/'+report_agent.W+'spacing')
            self.assertEqual(spacing.get(report_agent.W+'line'),'220');self.assertEqual(spacing.get(report_agent.W+'lineRule'),'exact')
            self.assertEqual(spacing.get(report_agent.W+'before'),'0');self.assertEqual(spacing.get(report_agent.W+'after'),'0')
    def test_one_line_landmarks_across_all_six_variants_and_no_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            for equipment in ('SF','SH','OT'):
                for status in ('OIs','No OIs'):
                    with self.subTest(equipment=equipment,status=status):
                        data=sample_report(equipment+'-'+status);path=Path(directory)/(equipment+status+'.docx')
                        report_agent.fill_report(data,path,draft=True);doc=Document(path)
                        expected=BASE|({'BeforeSection5'} if status=='OIs' else set());self.check_gaps(doc,expected)
                        cells=[[cell.text for row in table.rows for cell in report_agent.physical_cells(row)] for table in doc.tables]
                        paragraphs=[paragraph.text for paragraph in doc.paragraphs if paragraph.text.strip()]
                        report_agent.space_report_sections(doc.element.body);self.check_gaps(doc,expected)
                        self.assertEqual(cells,[[cell.text for row in table.rows for cell in report_agent.physical_cells(row)] for table in doc.tables])
                        self.assertEqual(paragraphs,[paragraph.text for paragraph in doc.paragraphs if paragraph.text.strip()])
    def test_placeholder_master_uses_the_same_spacing_without_losing_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);master=Document();master.add_table(rows=1,cols=1).cell(0,0).text='DSENY Engineering Services PC'
            master.add_paragraph('Title: {{project}}');master.add_table(rows=1,cols=1).cell(0,0).text='Section 3 Location'
            master.add_paragraph('Observed conditions');master.add_table(rows=1,cols=1).cell(0,0).text='Open item table'
            master.add_paragraph('Section 5, Client certification');master.save(root/'master.docx')
            data=sample_report('SH-OIs');report_agent.fill_report(data,root/'report.docx',template=root/'master.docx',template_mode='placeholders',draft=True)
            doc=Document(root/'report.docx');self.check_gaps(doc,BASE|{'BeforeSection5'})
            self.assertIn('Title: '+data['project'],[paragraph.text for paragraph in doc.paragraphs])
    def test_email_landmarks_override_mail_client_default_margins(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'report.html';path.write_text('<html><body><p style="margin:20pt;line-height:200%"><a name="JBI_ReportGap_AfterTitle"></a>&nbsp;</p><p>Keep these words</p></body></html>')
            result=html.fromstring(runner.email_html(path))
            gap=result.xpath('//p[@data-report-gap]')[0]
            for declaration in ('margin:0;','line-height:11pt;','height:11pt;','mso-line-height-rule:exactly;'):self.assertIn(declaration,gap.get('style'))
            self.assertEqual(result.xpath('//p')[1].text_content(),'Keep these words')

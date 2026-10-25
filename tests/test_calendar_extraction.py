import unittest
from backend.core import calendar_candidates


class CalendarExtraction(unittest.TestCase):
    def test_inline_wrapped_contact_address_and_equipment_permits(self):
        value = calendar_candidates('''2026-10-24 PS87Q Supported Scaffold-II-Inspection-OIs
CLIENT: Example Contractor
Project:\nPS87Q
Requested by: Example Contact
Example Construction
Site Address: 123 Example Street
Queens, NY 11111
Request date: 10.14.2026
Inspected on:\t10.24.2026
Permit#:\nQ123456-I1 SF
PE Drawings on site?: Yes
Drawings DOB/SCA approved?: No
''')
        self.assertEqual(value['fields']['requested_by'], 'Example Contact Example Construction')
        self.assertEqual(value['fields']['address'], '123 Example Street Queens, NY 11111')
        self.assertEqual(value['fields']['request_date'], '2026-10-14')
        self.assertEqual(value['fields']['inspection_date'], '2026-10-24')
        self.assertEqual(value['fields']['drawings_on_site'], 'Yes')
        self.assertEqual(value['fields']['drawings_approved'], 'No')
        self.assertEqual(value['equipment'][0]['permit'], 'Q123456-I1')
        self.assertNotIn('status', value['equipment'][0])

    def test_tab_separated_labels_and_unknown_headers(self):
        fields = calendar_candidates('Requested by\tExample Contact\nAddress\t123 Example Street\nAttendees:\nSomeone\nInspection date: 2026-10-24')['fields']
        self.assertEqual(fields['requested_by'], 'Example Contact')
        self.assertEqual(fields['address'], '123 Example Street')
        self.assertEqual(fields['inspection_date'], '2026-10-24')

    def test_questions_alternatives_and_instruction_are_not_answers(self):
        fields = calendar_candidates('PE Drawings on site?:\nDrawings DOB/SCA approved?: Yes / No\nRequest by:\nAddress:\nSection 2 Attendees\nExample Person')['fields']
        self.assertNotIn('drawings_on_site', fields)
        self.assertNotIn('drawings_approved', fields)
        self.assertNotIn('requested_by', fields)
        self.assertNotIn('address', fields)

    def test_single_permit_only_assigned_when_equipment_is_unambiguous(self):
        text = '2026-10-24 TEST Supported Scaffold-I-Inspection-OIs\nPermit number: Q123456-I1'
        self.assertEqual(calendar_candidates(text)['equipment'][0]['permit'], 'Q123456-I1')
        mixed = calendar_candidates(text+'\n2026-10-24 TEST Sidewalk Shed-I-Inspection-No OIs')
        self.assertTrue(all('permit' not in row for row in mixed['equipment']))

    def test_invalid_dates_and_placeholders_not_copied(self):
        fields = calendar_candidates('Inspection date: 02/30/2026\nRequested by: [Pending confirmation]\nAddress: TBD')['fields']
        self.assertEqual(fields, {})

    def test_outlook_multi_column_calendar_with_template_alternatives(self):
        value = calendar_candidates("""Requested DATE BY COMPANY
Contact Person: PENDING
STEPS:
3. Inspector/PE to answer whether approved drawings were on site.
2026-05-11 PS87Q Supported Scaffold-I-Inspection-OIs
2026-05-11 PS87Q Supported Scaffold-I-Inspection-No OIs
Section 1 Description: retained to perform an inspection.
Client:\tApollon\tProject:\tPS87Q
Request date:\t05.06.2026\tInspected on:\t05.11.2026\tRequest by:\tMarcin Bolesta,
Apollon Group
Product Inspected:\tSUPPORTED SCAFFOLD
Permit#:\tQ01248704\tContractor is responsible for ensuring all permits are kept current.
Address:\t67-54 80 Street Qns NY
PE Drawings on site?\tYes | NA | No
Drawings DOB/SCA approved?\tYes | NA | No
Section 2\tAttendees Names\tCompany Agency\tTitle
Dominic Stiller\tDSENY Engineering Services PC\tPE
Section 3 Shed Specific Location:
Section 3 Scaffold Specific Location
""")
        self.assertEqual(value['fields']['client'], 'Apollon')
        self.assertEqual(value['fields']['project'], 'PS87Q')
        self.assertEqual(value['fields']['request_date'], '2026-05-06')
        self.assertEqual(value['fields']['inspection_date'], '2026-05-11')
        self.assertEqual(value['fields']['requested_by'], 'Marcin Bolesta, Apollon Group')
        self.assertEqual(value['fields']['address'], '67-54 80 Street Qns NY')
        self.assertEqual(value['equipment'][0]['permit'], 'Q01248704')
        self.assertNotIn('drawings_on_site', value['fields'])
        self.assertNotIn('drawings_approved', value['fields'])
        self.assertEqual(len(value['equipment']), 1)
        self.assertNotIn('status', value['equipment'][0])

    def test_calendar_title_choices_keep_order_and_do_not_infer_outcome(self):
        first='2026-05-11 PS87Q Supported Scaffold-I-Inspection-OIs'
        second='2026-05-11 PS87Q Supported Scaffold-I-Inspection-No OIs'
        other='2026-05-11 PS87Q Fall Protection-II-Inspection-OIs'
        value=calendar_candidates(first+'\n'+second+'\n'+first+'\n'+other+'\nYYYY-MM-MM Project Product-RMN#-Inspection-OIs')
        self.assertEqual(value['titles'], [first,second,other])
        self.assertNotIn('status',value['equipment'][0])
        self.assertFalse(value['confirmed'])
        self.assertEqual(calendar_candidates('No subject supplied')['titles'], [])

    def test_flattened_calendar_row_and_project_from_subject(self):
        fields=calendar_candidates('Client: AEC Project: IS561K\nRequest date: 05.05.2026 Inspected on: 10.24.2026 Request by: Example Person\nSite Address: 400 Empire Boulevard')['fields']
        self.assertEqual(fields['project'],'IS561K')
        self.assertEqual(fields['client'],'AEC')
        self.assertEqual(fields['requested_by'],'Example Person')
        self.assertEqual(fields['address'],'400 Empire Boulevard')
        self.assertEqual(calendar_candidates('2026-10-24 IS561K Sidewalk Shed-I-Inspection-No OIs')['fields']['project'],'IS561K')
        mixed=calendar_candidates('2026-10-24 ONE Sidewalk Shed-I-Inspection-OIs\n2026-10-24 TWO Supported Scaffold-I-Inspection-OIs')
        self.assertNotIn('project',mixed['fields'])
        self.assertEqual(calendar_candidates('2026-10-24 IS561K Fall Protection-I-Inspection-OIs')['fields']['project'],'IS561K')
        same_kind=calendar_candidates('2026-10-24 ONE Supported Scaffold-I-Inspection-OIs\n2026-10-24 TWO Supported Scaffold-I-Inspection-No OIs')
        self.assertNotIn('project',same_kind['fields'])

    def test_shoring_subjects_cert_of_use_and_unused_equipment_template_sections(self):
        from pathlib import Path
        value=calendar_candidates((Path(__file__).parent/'fixtures/shoring_calendar.txt').read_text())
        self.assertEqual(value['fields']['client'],'Keltech')
        self.assertEqual(value['fields']['project'],'G Washington HS')
        self.assertEqual(len(value['titles']),4)
        self.assertEqual([r['equipment'] for r in value['equipment']],['OT'])
        self.assertNotIn('inspection_code',value['equipment'][0])
        self.assertNotIn('other_name',value['equipment'][0])
        self.assertEqual([r['inspection_code'] for r in value['report_subjects']],['V','V','VI','VI'])
        self.assertEqual(value['report_subjects'][2]['other_name'],'Field House Interior Shoring')
        self.assertNotIn('permit',value['fields'])
        self.assertNotIn('drawings_on_site',value['fields'])
        self.assertNotIn('status',str(value['equipment']))
        self.assertNotIn('locations',value['equipment'][0])
        self.assertFalse(value['confirmed'])

    def test_pe_cert_of_use_subject_is_a_title_choice_not_a_confirmed_result(self):
        text='2026-10-25 PS87Q Supported Scaffold-I-Inspection - PE CERT OF USE'
        result=calendar_candidates(text)
        self.assertEqual(result['titles'],[text])
        self.assertEqual(result['equipment'][0]['inspection_code'],'I')
        self.assertFalse(result['confirmed'])
        self.assertNotIn('status',result['equipment'][0])

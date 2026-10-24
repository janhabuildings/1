from pathlib import Path
import importlib.util
import shutil
import socket
import tempfile
import threading
import time
import unittest

import uvicorn
from backend.app import create_app
from backend.core import Settings

ROOT=Path(__file__).resolve().parents[1]

@unittest.skipUnless(importlib.util.find_spec('playwright'),'Playwright is required for browser checks')
class WebWorkflow(unittest.TestCase):
    def setUp(self):
        from playwright.sync_api import sync_playwright
        self.temp=tempfile.TemporaryDirectory()
        self.app=create_app(Settings(Path(self.temp.name),'fixture-browser-token',office_bin=str(ROOT/'.tools/bin/libreoffice')))
        sock=socket.socket();sock.bind(('127.0.0.1',0));self.port=sock.getsockname()[1]
        self.server=uvicorn.Server(uvicorn.Config(self.app,host='127.0.0.1',port=self.port,log_level='error',access_log=False))
        self.thread=threading.Thread(target=lambda:self.server.run(sockets=[sock]),daemon=True);self.thread.start()
        for _ in range(100):
            if self.server.started: break
            time.sleep(.02)
        self.playwright=sync_playwright().start()
        try: self.browser=self.playwright.chromium.launch(executable_path=shutil.which('chromium'),headless=True)
        except Exception as error:
            self.playwright.stop();self.server.should_exit=True;self.thread.join(10);self.temp.cleanup()
            self.skipTest('A working Chromium installation is required: '+str(error).splitlines()[0])
        self.page=self.browser.new_page(viewport={'width':1440,'height':1000},accept_downloads=True)
        self.errors=[];self.page.on('pageerror',lambda error:self.errors.append(str(error)))
        self.page.set_default_timeout(15000)
        self.page.goto(f'http://127.0.0.1:{self.port}/')
    def tearDown(self):
        self.page.close();self.browser.close();self.playwright.stop()
        self.server.should_exit=True;self.thread.join(10);self.temp.cleanup()
    def connect(self):
        self.page.locator('#token').fill('fixture-browser-token')
        self.page.get_by_role('button',name='Connect',exact=True).click()
        self.page.locator('#workspace').wait_for(state='visible')
        from playwright.sync_api import expect
        expect(self.page.locator('#save')).to_be_enabled()
    def test_login_rejects_bad_token_without_exposing_inspection_data(self):
        self.page.locator('#token').fill('incorrect-token')
        self.page.get_by_role('button',name='Connect',exact=True).click()
        from playwright.sync_api import expect
        expect(self.page.locator('#status')).to_contain_text('Authentication required')
        self.assertTrue(self.page.locator('#workspace').is_hidden())
        self.connect()
        self.assertEqual(self.page.locator('#token').input_value(),'')
        self.assertEqual(self.page.evaluate('localStorage.length'),0)
        self.assertEqual(self.page.evaluate('sessionStorage.length'),0)
        self.assertEqual(self.errors,[])
    def test_manual_inspection_upload_reports_download_and_empty_library(self):
        from playwright.sync_api import expect
        self.connect()
        self.page.locator('#title').fill('Browser fixture visit')
        self.page.locator('#project').fill('BROWSER-TEST')
        self.page.locator('#inspection_date').fill('2026-10-15')
        self.page.locator('#request_date').fill('2026-10-08')
        self.page.locator('#client').fill('Fixture contractor')
        self.page.locator('#add-attendee').click()
        self.page.get_by_placeholder('Name',exact=True).fill('Fixture Inspector')
        self.page.get_by_placeholder('Company / agency').fill('DSENY Engineering Services PC')
        self.page.get_by_placeholder('Role · PE for inspecting engineer').fill('PE')
        self.page.locator('#save').click()
        expect(self.page.locator('#save-state')).to_contain_text('Saved')
        expect(self.page.locator('#save')).to_be_enabled()
        self.assertEqual(len(self.app.state.store.list()),1)
        self.page.locator('[data-tab=evidence]').click()
        import base64
        image=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jGzQAAAAASUVORK5CYII=')
        self.page.locator('#upload').set_input_files({'name':'fixture.png','mimeType':'image/png','buffer':image})
        self.page.locator('.media-card').wait_for()
        from playwright.sync_api import expect
        expect(self.page.locator('#save')).to_be_enabled()
        self.page.locator('.media-card select').select_option('SF')
        self.page.get_by_label('Location / observation',exact=True).fill('North facade, bay 2')
        self.page.get_by_role('button',name='Save evidence label').click()
        from playwright.sync_api import expect
        expect(self.page.locator('#save')).to_be_enabled()
        self.page.locator('[data-tab=reports]').click()
        self.page.locator('#add-SF').click();self.page.locator('#add-SH').click()
        cards=self.page.locator('.report-card')
        cards.nth(0).get_by_label('Inspection result',exact=True).select_option('OIs')
        cards.nth(1).get_by_label('Inspection result',exact=True).select_option('No OIs')
        cards.nth(0).get_by_role('button',name='+ Add open item').click()
        cards.nth(0).get_by_label('Location / occurrence',exact=True).fill('North facade, bay 2')
        cards.nth(0).get_by_label('Corrective action',exact=True).fill('Install missing toeboard at the open platform edge.')
        if (ROOT/'.tools/bin/libreoffice').exists():
            self.page.locator('#generate').click()
            self.page.get_by_role('button',name='Download PDF',exact=True).wait_for(timeout=60000)
            expect(self.page.locator('#generate')).to_be_enabled()
            with self.page.expect_download() as download:
                self.page.get_by_role('button',name='Download PDF',exact=True).click()
            path=download.value.path()
            self.assertTrue(Path(path).read_bytes().startswith(b'%PDF-'))
            self.assertIn('no professional signature',self.page.locator('#generated').inner_text().lower())
        self.page.screenshot(path='/tmp/jbi-browser-workspace.png',full_page=True)
        self.page.locator('[data-tab=library]').click()
        self.page.locator('#code-query').fill('toeboard')
        self.page.locator('#search').click()
        expect(self.page.locator('#code-results')).to_contain_text('No matching sections found')
        self.page.locator('#draft-codes').check()
        self.page.locator('#code-query').fill('toeboard scaffold')
        self.page.locator('#search').click()
        expect(self.page.locator('#code-results')).to_contain_text('DRAFT · PDF pages')
        expect(self.page.locator('#code-results')).to_contain_text('3314')
        self.page.locator('#draft-library').select_option('sca-manual')
        self.page.locator('#search').click()
        expect(self.page.locator('#code-results')).to_contain_text('NYC SCA')
        expect(self.page.locator('#code-results')).to_contain_text('11.2')
        expect(self.page.locator('#code-results')).to_contain_text('2025')
        self.assertEqual(self.errors,[])
        self.assertEqual(self.page.evaluate('localStorage.length'),0)
    def test_delete_evidence_and_inspection_controls(self):
        from playwright.sync_api import expect
        from tests.test_report_updates import test_image
        self.connect()
        self.page.locator('#title').fill('Delete fixture')
        self.page.locator('#save').click()
        expect(self.page.locator('#save-state')).to_contain_text('Saved')
        identity=self.app.state.store.list()[0]['id']
        self.page.locator('[data-tab=evidence]').click()
        image=Path(self.temp.name)/'delete-image.png';image.write_bytes(test_image())
        self.page.locator('#upload').set_input_files(str(image))
        expect(self.page.locator('#media-list')).to_contain_text('Delete evidence')
        self.page.once('dialog',lambda dialog:dialog.accept())
        self.page.get_by_role('button',name='Delete evidence',exact=True).click()
        expect(self.page.locator('#media-empty')).to_be_visible()
        self.page.locator('[data-tab=inspection]').click()
        self.page.once('dialog',lambda dialog:dialog.accept())
        self.page.locator('#delete-inspection').click()
        expect(self.page.locator('#save-state')).to_contain_text('New inspection')
        self.assertEqual(self.app.state.store.list(),[])
        from backend.lifecycle import deletions
        self.assertIn(identity,deletions(self.app.state.store)['inspections'])
        self.assertEqual(self.errors,[])

    def test_other_unknown_name_is_saved_without_scaffold_dimensions(self):
        from playwright.sync_api import expect
        self.connect()
        self.page.locator('[data-tab=reports]').click()
        self.page.locator('#add-OT').click()
        card=self.page.locator('.report-card')
        expect(card.get_by_role('heading',name='Other',exact=True)).to_be_visible()
        expect(card.get_by_label('Item name (for unknown / custom)',exact=True)).to_be_visible()
        card.get_by_label('Item name (for unknown / custom)',exact=True).fill('Temporary debris screen')
        card.get_by_label('Description / inspection scope',exact=True).fill('North elevation')
        expect(card.get_by_label('Horizontal tie spacing',exact=True)).to_have_count(0)
        self.page.locator('#save').click()
        expect(self.page.locator('#save-state')).to_contain_text('Saved')
        record=self.app.state.store.list()[0]['reports'][0]
        self.assertEqual(record['equipment'],'OT')
        self.assertEqual(record['site']['other_name'],'Temporary debris screen')
        self.assertEqual(record['site']['details'],'North elevation')
        self.assertEqual(self.errors,[])

    def test_template_upload_mapping_preview_and_activation(self):
        from playwright.sync_api import expect
        from tests.test_templates import placeholder_doc
        self.connect()
        self.page.locator('[data-tab=templates]').click()
        expect(self.page.locator('#template-versions')).to_contain_text('Original DSENY template')
        self.page.locator('#template-mode').select_option('placeholders')
        self.page.locator('#template-label').fill('Browser template')
        source=Path(self.temp.name)/'browser-template.docx';source.write_bytes(placeholder_doc(alias=True))
        self.page.locator('#template-file').set_input_files(str(source))
        self.page.locator('#template-upload').click()
        card=self.page.locator('[data-template-version]').filter(has=self.page.get_by_role('heading',name='Browser template',exact=True))
        expect(card).to_contain_text('Map unsupported fields: school_name')
        card.locator('summary').click()
        card.get_by_label('{{school_name}} receives',exact=True).select_option('project')
        card.get_by_role('button',name='Save mapping as new version',exact=True).click()
        revised=self.page.locator('[data-template-version]').filter(has=self.page.get_by_role('heading',name='Browser template (mapping)',exact=True))
        expect(revised).to_be_visible()
        revised.get_by_role('button',name='Generate sample',exact=True).click()
        expect(self.page.locator('#template-preview')).to_contain_text('Sample generated.',timeout=60000)
        expect(self.page.locator('#template-preview').get_by_role('button',name='Download sample DOCX',exact=True)).to_be_visible()
        revised.get_by_role('checkbox').check()
        revised.get_by_role('button',name='Activate this version',exact=True).click()
        expect(self.page.locator('#template-versions')).to_contain_text('Browser template (mapping) · ACTIVE')
        self.assertEqual(self.errors,[])

    def test_template_choice_dropdowns_preserve_custom_and_selected_values(self):
        from playwright.sync_api import expect
        self.connect()
        self.page.locator('[data-tab=reports]').click()
        self.page.locator('#add-SF').click()
        tie=self.page.get_by_label('Tie type',exact=True)
        dunnage=self.page.get_by_label('Dunnage type',exact=True)
        self.assertEqual(tie.input_value(), '')
        self.assertEqual(dunnage.input_value(), '')
        tie.select_option('Concrete Wall Anchor')
        dunnage.select_option('__custom__')
        self.page.get_by_label('Dunnage type · custom description',exact=True).fill('Timber pads on sleepers')
        self.page.locator('#save').click()
        expect(self.page.locator('#save-state')).to_contain_text('Saved')
        record=self.app.state.store.list()[0]
        saved=self.app.state.store.get(record['id'])
        self.assertEqual(saved['reports'][0]['site']['tie_type'], 'Concrete Wall Anchor')
        self.assertEqual(saved['reports'][0]['site']['dunnage_type'], 'Timber pads on sleepers')
        self.page.locator('#add-SH').click()  # Re-render must preserve custom values.
        self.assertEqual(self.page.get_by_label('Dunnage type · custom description',exact=True).input_value(), 'Timber pads on sleepers')
        self.assertEqual(self.errors, [])

    def test_calendar_candidates_do_not_choose_a_report_outcome(self):
        self.connect()
        self.page.locator('#calendar_text').fill('2026-10-15 TEST Supported Scaffold-VIII-Inspection-No OIs\nClient:\nCalendar Fixture\nProject:\nTEST\nRequested by:\tExample Contact\nExample Company\nAddress:\t123 Example Street\nPermit#:\tM00981443-I1 SF\nPE Drawings on site?\tYes | NA | No\nInspected on:\n10/15/2026\nM00981443-I1 SF')
        self.page.locator('#extract').click()
        self.page.locator('#calendar-candidates').wait_for(state='visible')
        from playwright.sync_api import expect
        expect(self.page.locator('#extract')).to_be_enabled()
        self.page.once('dialog',lambda dialog:dialog.accept())
        self.page.locator('#apply-calendar').click()
        self.assertEqual(self.page.locator('#client').input_value(),'Calendar Fixture')
        self.assertEqual(self.page.locator('#requested_by').input_value(),'Example Contact Example Company')
        self.assertEqual(self.page.locator('#address').input_value(),'123 Example Street')
        self.page.locator('[data-tab=reports]').click()
        self.assertEqual(self.page.locator('.report-card').get_by_label('Inspection result',exact=True).input_value(),'')
        self.assertEqual(self.errors,[])

if __name__=='__main__': unittest.main()

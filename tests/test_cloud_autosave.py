"""Exercise autosave against a real authenticated backend in Chromium."""
import unittest
from playwright.sync_api import expect
import test_web_interface as workflow
from unittest.mock import patch
from test_cloud_storage import MemoryGateway

class CloudAutosave(unittest.TestCase):
    def setUp(self):
        self.gateway=MemoryGateway()
        self.cloud_patch=patch('backend.cloud_storage.CloudStorage.from_env',side_effect=self.gateway.cloud)
        self.cloud_patch.start()
        try:workflow.WebWorkflow.setUp(self)
        except BaseException:self.cloud_patch.stop();raise
    def tearDown(self):
        try:workflow.WebWorkflow.tearDown(self)
        finally:self.cloud_patch.stop()
    connect=workflow.WebWorkflow.connect

    def test_automatic_save_reopen_and_attendees_before_report(self):
        self.connect()
        self.page.locator('#title').fill('Cloud draft')
        self.page.locator('#add-attendee').click()
        self.page.get_by_placeholder('Name',exact=True).fill('Inspector saved before report')
        expect(self.page.locator('#save-state')).to_contain_text('Saved ·')
        record=self.app.state.store.list()[0]
        self.assertEqual(record['attendees'][0]['name'],'Inspector saved before report')
        self.page.reload();self.connect()
        self.page.locator('#saved').select_option(record['id'])
        expect(self.page.locator('#title')).to_have_value('Cloud draft')
        expect(self.page.get_by_placeholder('Name',exact=True)).to_have_value('Inspector saved before report')
        self.assertEqual(self.errors,[])

    def test_edits_during_save_are_saved_in_order(self):
        self.connect()
        self.page.evaluate('''() => {
          const original=window.fetch; window.saveStarted=false;
          window.fetch=async(...args)=>{
            const response=await original(...args);
            if(args[1]?.method==='PUT'&&String(args[0]).startsWith('/inspections/')){
              window.saveStarted=true; await new Promise(resolve=>setTimeout(resolve,1800));
            }
            return response;
          };
        }''')
        self.page.locator('#title').fill('First edit')
        self.page.wait_for_function('() => window.saveStarted')
        self.page.locator('#title').fill('Newer edit during save')
        expect(self.page.locator('#save-state')).to_contain_text('Saved ·',timeout=15000)
        self.assertEqual(len(self.app.state.store.list()),1)
        self.assertEqual(self.app.state.store.list()[0]['title'],'Newer edit during save')

    def test_failed_save_retries_without_clearing_draft(self):
        self.connect()
        self.page.route('**/inspections/*',lambda route:route.abort(),times=1)
        self.page.locator('#title').fill('Retried draft')
        expect(self.page.locator('#save-state')).to_contain_text('Not saved')
        expect(self.page.locator('#title')).to_have_value('Retried draft')
        self.page.evaluate("window.dispatchEvent(new Event('online'))")
        expect(self.page.locator('#save-state')).to_contain_text('Saved ·')
        self.assertEqual(self.app.state.store.list()[0]['title'],'Retried draft')

    def test_new_inspection_flushes_pending_edit(self):
        self.connect()
        self.page.locator('#title').fill('Save before new')
        self.page.locator('#new').click()
        expect(self.page.locator('#title')).to_have_value('')
        self.assertEqual(self.app.state.store.list()[0]['title'],'Save before new')

    def test_manual_save_conflict_pauses_automatic_overwrite(self):
        self.connect();self.page.locator('#title').fill('Previously saved')
        expect(self.page.locator('#save-state')).to_contain_text('Saved ·')
        self.page.locator('#title').fill('Conflicting local draft')
        self.gateway.revision+=1
        self.page.locator('#save').click()
        expect(self.page.locator('#status')).to_contain_text('Refresh saved')
        self.assertTrue(self.page.evaluate('() => state.saveConflict'))
        self.page.evaluate("window.dispatchEvent(new Event('online'))")
        self.page.wait_for_timeout(1500)
        self.assertEqual(self.app.state.store.list()[0]['title'],'Previously saved')
        expect(self.page.locator('#title')).to_have_value('Conflicting local draft')

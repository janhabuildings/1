import unittest
from tests import test_web_interface as workflow

class WorkspaceBrowser(unittest.TestCase):
    setUp=workflow.WebWorkflow.setUp
    tearDown=workflow.WebWorkflow.tearDown
    connect=workflow.WebWorkflow.connect
    def test_admin_creates_user_and_inspector_sees_only_assigned_records(self):
        from playwright.sync_api import expect
        self.connect()
        self.page.locator('#workspace-admin summary').click()
        self.page.locator('#workspace-user-name').fill('Field Inspector')
        self.page.locator('#workspace-user-email').fill('field@example.com')
        self.page.get_by_role('button',name='Create account',exact=True).click()
        expect(self.page.locator('#workspace-key-box')).to_be_visible()
        key=self.page.locator('#workspace-key').input_value();self.assertTrue(key.startswith('jbi_'))
        self.page.locator('#workspace-key-dismiss').click()
        expect(self.page.locator('#workspace-key')).to_have_value('')
        self.page.locator('#disconnect').click()
        self.page.locator('#token').fill(key)
        self.page.get_by_role('button',name='Connect',exact=True).click()
        expect(self.page.locator('#workspace')).to_be_visible()
        expect(self.page.locator('#workspace-admin')).to_be_hidden()
        expect(self.page.locator('[data-tab=templates]')).to_be_hidden()
        expect(self.page.locator('#connection-state')).to_contain_text('Field Inspector')
        self.page.locator('#title').fill('Inspector field visit')
        self.page.locator('#save').click()
        expect(self.page.locator('#save-state')).to_contain_text('Saved')
        identity=self.page.evaluate('state.id')
        self.page.locator('#disconnect').click()
        self.page.locator('#token').fill('fixture-browser-token')
        self.page.get_by_role('button',name='Connect',exact=True).click()
        expect(self.page.locator('#workspace')).to_be_visible()
        self.page.locator('#saved').select_option(identity)
        expect(self.page.locator('#save-state')).to_contain_text('Loaded saved inspection')
        self.page.locator('#workspace-admin summary').click()
        expect(self.page.locator('#workspace-assignment input:checked')).to_have_count(1)
        self.page.locator('#workspace-assignment input:checked').uncheck()
        self.page.get_by_role('button',name='Save assignments',exact=True).click()
        expect(self.page.locator('#status')).to_contain_text('assignments saved')
        self.page.locator('#disconnect').click()
        self.page.locator('#token').fill(key)
        self.page.get_by_role('button',name='Connect',exact=True).click()
        expect(self.page.locator('#workspace')).to_be_visible()
        expect(self.page.locator('#saved option')).to_have_count(1)
        self.assertEqual(self.page.evaluate('localStorage.length'),0)
        self.assertEqual(self.errors,[])

import { test, describe } from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';

import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC_DIR = path.resolve(__dirname, '..');

describe('Finance Hub UI Usability & Responsive Navigation Contract Tests', () => {
  const headerContent = fs.readFileSync(path.join(SRC_DIR, 'components/CommandHeader.vue'), 'utf-8');
  const settingsModalContent = fs.readFileSync(path.join(SRC_DIR, 'components/AppSettingsModal.vue'), 'utf-8');
  const manageModalContent = fs.readFileSync(path.join(SRC_DIR, 'components/ManageAccountsCategoriesModal.vue'), 'utf-8');
  const importModalContent = fs.readFileSync(path.join(SRC_DIR, 'components/UnifiedImportModal.vue'), 'utf-8');
  const appContent = fs.readFileSync(path.join(SRC_DIR, 'App.vue'), 'utf-8');

  test('1. One unified Add Transaction action', () => {
    // Separate standalone + Import and + Record buttons are replaced
    assert.strictEqual(headerContent.includes('<span>+ Import</span>'), false, 'Separate + Import button should be removed from top-level header');
    assert.strictEqual(headerContent.includes('<span>+ Record</span>'), false, 'Separate + Record button should be removed from top-level header');

    // Button renamed from "+ Add Transaction" to "+ Transaction"
    assert.ok(headerContent.includes('+ Transaction'), 'Button must be labeled "+ Transaction"');
    assert.ok(headerContent.includes('isAddTxChooserOpen'), 'Chooser toggle state must exist');

    // Chooser options: Enter manually (E) and Import a file or screenshot (I)
    assert.ok(headerContent.includes('Enter manually'), 'Chooser must include "Enter manually"');
    assert.ok(headerContent.includes('Import a file or screenshot'), 'Chooser must include "Import a file or screenshot"');
    assert.ok(headerContent.includes("chooseAction('record')"), 'Action must emit record transaction');
    assert.ok(headerContent.includes("chooseAction('import')"), 'Action must emit import');

    // Chooser width constraint and multiline text wrapping
    assert.ok(headerContent.includes('whitespace-normal'), 'Chooser container must explicitly allow multiline text wrapping');
    assert.ok(headerContent.includes('break-words'), 'Descriptions must be constrained with break-words');
  });

  test('2. Reorganize header controls and settings preferences', () => {
    // Visible v2.0 label is removed
    assert.strictEqual(headerContent.includes('v2.0'), false, 'Visible v2.0 badge must be removed from header');

    // Settings and Help icon buttons are present
    assert.ok(headerContent.includes('aria-label="Application Settings"'), 'Settings icon button must have accessible label');
    assert.ok(headerContent.includes('aria-label="Keyboard shortcuts and help"'), 'Help icon button must have accessible label');

    // Manage Accounts & Categories removed from navigation bar to reduce crowding
    assert.strictEqual(headerContent.includes('<span>Manage Accounts & Categories</span>'), false, 'Manage Accounts & Categories button must be removed from header navigation');
    assert.strictEqual(headerContent.includes('<span>+ Add Account</span>'), false, 'Standalone + Add Account button must not be in header');
    
    // Help shortcuts retain N shortcut for Manage accounts & categories
    assert.ok(headerContent.includes('<dt>Manage accounts & categories</dt>'), 'Help shortcuts must retain entry for Manage accounts & categories');
    assert.ok(appContent.includes("e.key === 'n' || e.key === 'N'"), 'Keyboard shortcut N must open manage modal');

    // App title setting with autosave and no separate Save button
    assert.strictEqual(settingsModalContent.includes('Save Title'), false, 'Separate Save Title button must be removed');
    assert.ok(settingsModalContent.includes('onTitleInput'), 'Title input must trigger autosave on input');
    assert.ok(settingsModalContent.includes('onTitleBlur'), 'Title input must trigger autosave on blur');
    assert.ok(settingsModalContent.includes("titleStatus === 'saved'"), 'Subtle saved indicator must exist');
    assert.ok(settingsModalContent.includes("titleStatus === 'saving'"), 'Subtle saving indicator must exist');

    // Settings cards fully clickable with role="button" and accessible keyboard handling
    assert.ok(settingsModalContent.includes('role="button"'), 'Interactive settings cards must use role="button"');
    assert.ok(settingsModalContent.includes('tabindex="0"'), 'Interactive settings cards must be keyboard focusable');
    assert.ok(settingsModalContent.includes('stealthStore.toggleStealth()'), 'Stealth Mode card must toggle stealthStore');
    assert.ok(settingsModalContent.includes('handleOpenManage'), 'Manage Accounts & Categories card must handle opening manage');

    // Category management is removed from Settings modal
    assert.strictEqual(settingsModalContent.includes('activeTab === \'categories\''), false, 'Category management tab must be removed from SettingsModal');
    assert.strictEqual(settingsModalContent.includes('DeleteCategoryModal'), false, 'DeleteCategoryModal must not be in SettingsModal');

    // Manage Accounts & Categories is accessible from Settings modal
    assert.ok(settingsModalContent.includes('Manage Accounts & Categories'), 'SettingsModal must have an action for Manage Accounts & Categories');
    assert.ok(appContent.includes('@open-manage="handleOpenManageFromSettings"'), 'App.vue must cleanly open manage modal when emitted from settings');

    // Two-option segmented theme control (Light mode vs Dark mode)
    assert.ok(settingsModalContent.includes('role="radiogroup"'), 'Theme control must use accessible radiogroup');
    assert.ok(settingsModalContent.includes('Light mode'), 'Theme control must display Light mode');
    assert.ok(settingsModalContent.includes('Dark mode'), 'Theme control must display Dark mode');
    assert.ok(settingsModalContent.includes('themeStore.setTheme(false)'), 'Theme control must set light mode directly');
    assert.ok(settingsModalContent.includes('themeStore.setTheme(true)'), 'Theme control must set dark mode directly');

    // Show or hide header date and time setting
    assert.ok(settingsModalContent.includes('Header Date & Time'), 'Settings must include Header Date & Time toggle card');
    assert.ok(settingsModalContent.includes('toggleDateTimeDisplay'), 'Settings must toggle date/time display');
    assert.ok(appContent.includes('updateShowDateTime'), 'App.vue must manage showDateTime preference');
    assert.ok(appContent.includes("localStorage.getItem('showDateTime')"), 'showDateTime preference must be persisted');
    assert.ok(headerContent.includes('v-if="showDateTime"'), 'Header must use v-if="showDateTime" to remove element completely from layout');
  });

  test('3. Manage Accounts & Categories area', () => {
    // Modal exists and has Accounts and Categories tabs
    assert.ok(manageModalContent.includes('Manage Accounts & Categories'), 'Manage modal must have proper title');
    assert.ok(manageModalContent.includes("activeTab = 'accounts'"), 'Must have Accounts tab');
    assert.ok(manageModalContent.includes("activeTab = 'categories'"), 'Must have Categories tab');

    // Accounts management capabilities
    assert.ok(manageModalContent.includes('isAddAccountOpen = true'), 'Must support adding accounts');
    assert.ok(manageModalContent.includes('openEditAccount'), 'Must support editing accounts');
    assert.ok(manageModalContent.includes('handleArchiveAccount'), 'Must support archiving accounts');
    assert.ok(manageModalContent.includes('handleReactivateAccount'), 'Must support reactivating accounts');
    assert.ok(manageModalContent.includes('openDeleteAccount'), 'Must support protected permanent account deletion');
    assert.ok(manageModalContent.includes('DeleteAccountModal'), 'Must integrate DeleteAccountModal with cascade safeguards');

    // Categories management capabilities
    assert.ok(manageModalContent.includes('openCreateCategory'), 'Must support adding categories');
    assert.ok(manageModalContent.includes('openEditCategory'), 'Must support editing categories');
    assert.ok(manageModalContent.includes('promptArchiveCategory'), 'Must support archiving categories');
    assert.ok(manageModalContent.includes('handleReactivateCategory'), 'Must support reactivating categories');
    assert.ok(manageModalContent.includes('openDeleteCategory'), 'Must support protected category deletion');
    assert.ok(manageModalContent.includes('DeleteCategoryModal'), 'Must integrate DeleteCategoryModal with reassignment protections');

    // Wired into App.vue
    assert.ok(appContent.includes('ManageAccountsCategoriesModal'), 'App.vue must mount ManageAccountsCategoriesModal');
    assert.ok(appContent.includes('isManageModalOpen'), 'App.vue must track isManageModalOpen');
  });

  test('4. Responsive header and navigation', () => {
    // Desktop navigation
    assert.ok(headerContent.includes('hidden md:flex'), 'Desktop navigation tabs must be hidden on narrow viewports');
    assert.ok(headerContent.includes('to="/portfolios"'), 'Navigation must include Portfolios');
    assert.ok(headerContent.includes('to="/analysis"'), 'Navigation must include Analysis');
    assert.ok(headerContent.includes('to="/ledger"'), 'Navigation must include Ledger');
    assert.ok(headerContent.includes('to="/queue"'), 'Navigation must include Queue');

    // Mobile / narrow screen navigation dropdown
    assert.ok(headerContent.includes('md:hidden nav-dropdown-container'), 'Responsive navigation menu dropdown container must exist');
    assert.ok(headerContent.includes('isNavMenuOpen'), 'Responsive navigation toggle state must exist');
    assert.ok(headerContent.includes('activeNavLabel'), 'Responsive navigation must display active section label');
  });

  test('5. Duplicate exclusion in the import pop-up', () => {
    // Exclude as duplicate button exists with clear advisory text
    assert.ok(importModalContent.includes('Exclude as duplicate'), 'Must have explicit Exclude as duplicate action');
    assert.ok(importModalContent.includes('Matches an existing ledger transaction'), 'Must have clear helper text explaining exclusion');
    assert.ok(importModalContent.includes('excludeAsDuplicate'), 'Must define excludeAsDuplicate handler');

    // Discards from review queue via API
    assert.ok(importModalContent.includes('api.discardStagingItem'), 'Exclusion must call api.discardStagingItem to remove from queue');
    assert.ok(importModalContent.includes('stagingStore.fetchCount()'), 'Exclusion must refresh pending queue counter');
    assert.ok(importModalContent.includes('reviewItems.value.splice(idx, 1)'), 'Exclusion must visibly remove item from current candidate list');
  });
});

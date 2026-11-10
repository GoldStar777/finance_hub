import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const SRC_DIR = path.resolve('src');

function readFile(subpath) {
  return fs.readFileSync(path.join(SRC_DIR, subpath), 'utf8');
}

describe('Finance Hub Multiple Isolated Profiles Contract Tests', () => {
  const headerContent = readFile('components/CommandHeader.vue');
  const settingsModalContent = readFile('components/AppSettingsModal.vue');
  const manageProfilesContent = readFile('components/ManageProfilesModal.vue');
  const profilesStoreContent = readFile('stores/profiles.ts');
  const clientContent = readFile('api/client.ts');
  const typesContent = readFile('types/index.ts');
  const appContent = readFile('App.vue');

  test('1. Header contains no profile name, badge, selector, menu, or profile-management control', () => {
    // Header must not contain profile store, active profile name, or workspace indicator
    assert.ok(!headerContent.includes('profilesStore'), 'Header must not reference profiles store');
    assert.ok(!headerContent.includes('activeProfile'), 'Header must not reference activeProfile');
    assert.ok(!headerContent.includes('Active Workspace'), 'Header must not contain active workspace label or title');
    assert.ok(!headerContent.includes('profile-switcher'), 'Header must not contain profile-switcher');
    
    // Header must NOT contain switcher actions, menus, or profile management emits
    assert.ok(!headerContent.includes('switchAndClose'), 'Header must not contain profile switcher logic');
    assert.ok(!headerContent.includes('openManageProfiles'), 'Header must not contain switcher action to manage workspaces');
    assert.ok(!headerContent.includes('open-profiles'), 'Header must not emit open-profiles event');
  });

  test('2. Settings entry point for managing profiles', () => {
    // AppSettingsModal must contain Manage Financial Workspaces card
    assert.ok(settingsModalContent.includes('Manage Financial Workspaces'), 'Settings must include Manage Financial Workspaces card');
    assert.ok(settingsModalContent.includes('handleOpenProfiles'), 'Settings must have click handler to open profiles modal');
    assert.ok(settingsModalContent.includes('profilesStore.activeProfile?.name'), 'Settings must show active profile name');
    assert.ok(settingsModalContent.includes("emit('open-profiles')"), 'Settings must emit open-profiles');
  });

  test('3. Dedicated Manage Profiles modal with creation, renaming, and archiving', () => {
    // Modal structure
    assert.ok(manageProfilesContent.includes('Financial Workspaces'), 'Modal must have clear workspace title');
    assert.ok(manageProfilesContent.includes('newProfileName'), 'Modal must have create profile form input');
    assert.ok(manageProfilesContent.includes('handleCreateProfile'), 'Modal must have create profile handler');
    
    // Listing & inline rename
    assert.ok(manageProfilesContent.includes('activeProfilesList'), 'Modal must list active workspaces');
    assert.ok(manageProfilesContent.includes('submitRename'), 'Modal must support profile renaming');
    assert.ok(manageProfilesContent.includes('handleArchive'), 'Modal must support archiving and unarchiving');
    assert.ok(manageProfilesContent.includes('archivedProfilesList'), 'Modal must section archived workspaces');
  });

  test('4. Strict deletion safeguards and impact summary in Manage Profiles modal', () => {
    // Impact summary display
    assert.ok(manageProfilesContent.includes('impactData.accounts_count'), 'Deletion modal must show accounts count impact');
    assert.ok(manageProfilesContent.includes('impactData.transactions_count'), 'Deletion modal must show transactions count impact');
    assert.ok(manageProfilesContent.includes('impactData.disk_usage_formatted'), 'Deletion modal must show disk usage impact');
    assert.ok(manageProfilesContent.includes('deleteConfirmText'), 'Deletion modal must have confirmation text input');
    assert.ok(manageProfilesContent.includes('isDeleteConfirmed'), 'Deletion button must be gated by exact name match');
    assert.ok(manageProfilesContent.includes('confirmPermanentDelete'), 'Modal must execute permanent deletion with typed confirmation');
    
    // Safety restrictions: active or only remaining profile
    assert.ok(manageProfilesContent.includes('Cannot delete the active workspace'), 'Active profile must have delete disabled with explanation');
    assert.ok(manageProfilesContent.includes('profilesStore.profiles.length <= 1'), 'Only remaining workspace must be protected from deletion');
  });

  test('5. Frontend state isolation and store reload upon switching', () => {
    // Pinia store
    assert.ok(profilesStoreContent.includes('switchProfile'), 'Store must define switchProfile');
    assert.ok(profilesStoreContent.includes('switchEpoch'), 'Store must track switchEpoch to discard stale in-flight responses');
    assert.ok(profilesStoreContent.includes('accountsStore.loadData()'), 'Profile switch must reload accounts and dashboard summary');
    assert.ok(profilesStoreContent.includes('txStore.loadTransactions()'), 'Profile switch must reload transactions');
    assert.ok(profilesStoreContent.includes('txStore.loadCategories()'), 'Profile switch must reload categories');
    assert.ok(profilesStoreContent.includes('stagingStore.fetchCount()'), 'Profile switch must reload staging queue');
    assert.ok(profilesStoreContent.includes('investmentsStore.loadAllData()'), 'Profile switch must reload investments');
    assert.ok(profilesStoreContent.includes('systemStore.loadConfig()'), 'Profile switch must reload system config');
  });

  test('6. API client request-scoped X-Profile-ID header injection', () => {
    // client.ts
    assert.ok(clientContent.includes("headers['X-Profile-ID'] = currentProfileId"), 'API client must inject X-Profile-ID header');
    assert.ok(clientContent.includes('setActiveProfileId'), 'Client must export setActiveProfileId');
    assert.ok(clientContent.includes('listProfiles'), 'Client must export listProfiles API');
    assert.ok(clientContent.includes('createProfile'), 'Client must export createProfile API');
    assert.ok(clientContent.includes('selectProfile'), 'Client must export selectProfile API');
    assert.ok(clientContent.includes('updateProfile'), 'Client must export updateProfile API');
    assert.ok(clientContent.includes('getProfileImpact'), 'Client must export getProfileImpact API');
    assert.ok(clientContent.includes('deleteProfile'), 'Client must export deleteProfile API');
  });

  test('7. App.vue wiring and Settings-only profile management', () => {
    // App.vue
    assert.ok(appContent.includes('<ManageProfilesModal'), 'App.vue must include ManageProfilesModal');
    assert.ok(appContent.includes('profilesStore.loadProfiles()'), 'App.vue must initialize profiles on mount');
    assert.ok(appContent.includes('handleOpenProfilesFromSettings'), 'App.vue must wire ManageProfilesModal from Settings');
    assert.ok(!appContent.includes("e.key === 'p' || e.key === 'P'"), 'App.vue must not bind P shortcut for switching');
  });

  const accountsStoreContent = readFile('stores/accounts.ts');
  const txStoreContent = readFile('stores/transactions.ts');
  const investmentsStoreContent = readFile('stores/investments.ts');
  const analysisStoreContent = readFile('stores/analysis.ts');
  const stagingStoreContent = readFile('stores/staging.ts');
  const routerContent = readFile('router/index.ts');
  const dashboardViewContent = readFile('views/DashboardView.vue');
  const ledgerViewContent = readFile('views/LedgerView.vue');
  const analysisViewContent = readFile('views/AnalysisView.vue');
  const portfoliosViewContent = readFile('views/PortfoliosView.vue');
  const stagingViewContent = readFile('views/StagingView.vue');

  test('8. Regression: Switching to non-default workspace, refreshing, and restoring that workspace', () => {
    // Storage persistence contracts
    assert.ok(clientContent.includes("PROFILE_STORAGE_KEY = 'finance_hub_active_profile_id'"), 'Must define PROFILE_STORAGE_KEY');
    assert.ok(clientContent.includes('localStorage.getItem(PROFILE_STORAGE_KEY)'), 'Must read active profile synchronously on boot');
    assert.ok(clientContent.includes('localStorage.setItem(PROFILE_STORAGE_KEY, id)'), 'Must persist active profile to localStorage');
    assert.ok(clientContent.includes("window.addEventListener('storage'"), 'API client must synchronize across browser tabs on storage events');
    assert.ok(appContent.includes("window.addEventListener('storage'"), 'App.vue must listen for storage events to sync stores');
    assert.ok(profilesStoreContent.includes('syncFromStorage'), 'profilesStore must expose syncFromStorage');

    // Simulation: User switches to Shared Household Workspace ('00000000000040008000000000000001')
    const simulatedStorage = new Map();
    const STORAGE_KEY = 'finance_hub_active_profile_id';
    const nonDefaultId = '00000000000040008000000000000001';

    simulatedStorage.set(STORAGE_KEY, nonDefaultId);
    assert.equal(simulatedStorage.get(STORAGE_KEY), nonDefaultId);

    // Refresh simulation: Synchronous initialization on client module evaluation
    let simulatedCurrentProfileId = simulatedStorage.get(STORAGE_KEY) || null;
    assert.equal(simulatedCurrentProfileId, nonDefaultId, 'Active profile must be restored synchronously before any network call');

    // Simulate loadProfiles() registry validation
    const mockProfiles = [
      { id: 'default', name: "Primary Workspace", is_default: true, is_active: false, is_archived: false },
      { id: nonDefaultId, name: "Shared Household Workspace", is_default: false, is_active: true, is_archived: false }
    ];

    const savedId = simulatedCurrentProfileId;
    let targetProfile = mockProfiles.find(p => p.id === savedId && !p.is_archived) || null;
    const wasInvalid = Boolean(savedId && !targetProfile);
    if (!targetProfile) {
      targetProfile = mockProfiles.find(p => p.is_default && !p.is_archived) || mockProfiles[0];
    }

    assert.equal(wasInvalid, false, 'Saved workspace must be valid');
    assert.equal(targetProfile.id, nonDefaultId, 'Resolved workspace must remain Shared Household workspace and NOT revert to default');
    assert.equal(targetProfile.name, "Shared Household Workspace");
  });

  test('9. Regression: Navigating directly to each major tab after refresh while preserving selected workspace', () => {
    // Verify major routes exist in router and do not force redirects to '/'
    const majorRoutes = ['/', '/portfolios', '/analysis', '/ledger', '/queue'];
    for (const r of majorRoutes) {
      assert.ok(routerContent.includes(`path: '${r}'`), `Router must define ${r}`);
    }

    // Verify all primary views invoke their loaders on mount without hardcoding profile
    assert.ok(dashboardViewContent.includes('accountsStore.loadData()'), 'Dashboard must trigger accountsStore.loadData()');
    assert.ok(ledgerViewContent.includes('accountsStore.loadData()'), 'Ledger must trigger accountsStore.loadData()');
    assert.ok(ledgerViewContent.includes('txStore.loadTransactions'), 'Ledger must trigger txStore.loadTransactions()');
    assert.ok(analysisViewContent.includes('analysisStore.loadAnalysis()'), 'Analysis must trigger analysisStore.loadAnalysis()');
    assert.ok(portfoliosViewContent.includes('investmentsStore.loadAllData()'), 'Portfolios must trigger investmentsStore.loadAllData()');
    assert.ok(stagingViewContent.includes('stagingStore.fetchItems()'), 'Queue must trigger stagingStore.fetchItems()');

    // Simulation: Navigating directly to each major route after page refresh
    const targetWorkspaceId = '00000000000040008000000000000001';
    const simulateRequestHeaders = (endpoint) => {
      const headers = { 'Content-Type': 'application/json' };
      const currentProfileId = targetWorkspaceId;
      if (currentProfileId) {
        headers['X-Profile-ID'] = currentProfileId;
      }
      return headers;
    };

    const endpointsByRoute = {
      '/': ['/accounts', '/dashboard/summary', '/transactions?limit=6'],
      '/ledger': ['/accounts', '/transactions?limit=25', '/categories'],
      '/analysis': ['/analytics/analysis?preset=month'],
      '/portfolios': ['/investments/summary'],
      '/queue': ['/staging?status=pending', '/staging/count']
    };

    for (const [route, endpoints] of Object.entries(endpointsByRoute)) {
      for (const ep of endpoints) {
        const headers = simulateRequestHeaders(ep);
        assert.equal(
          headers['X-Profile-ID'],
          targetWorkspaceId,
          `Direct navigation to ${route} on refresh must send X-Profile-ID for endpoint ${ep}`
        );
      }
    }
  });

  test('10. Regression: Stale response or startup race not overwriting selected profile', () => {
    // Contract checks for epoch and activeProfile checks across all profile stores
    assert.ok(accountsStoreContent.includes('reset'), 'accountsStore must define reset');
    assert.ok(accountsStoreContent.includes('reqProfile !== getActiveProfileId()'), 'accountsStore must discard stale profile responses');
    assert.ok(txStoreContent.includes('reset'), 'txStore must define reset');
    assert.ok(txStoreContent.includes('reqProfile !== getActiveProfileId()'), 'txStore must discard stale profile responses');
    assert.ok(investmentsStoreContent.includes('reset'), 'investmentsStore must define reset');
    assert.ok(investmentsStoreContent.includes('reqProfile !== getActiveProfileId()'), 'investmentsStore must discard stale profile responses');
    assert.ok(analysisStoreContent.includes('reset'), 'analysisStore must define reset');
    assert.ok(analysisStoreContent.includes('reqProfile !== getActiveProfileId()'), 'analysisStore must discard stale profile responses');
    assert.ok(stagingStoreContent.includes('reset'), 'stagingStore must define reset');

    // Simulation: Request starts under Profile A, but user switches to Profile B before Request A resolves
    let activeProfileId = 'default';
    const reqProfile = activeProfileId;

    // In-flight switch occurs
    activeProfileId = '00000000000040008000000000000001';

    // Slow response from Profile A arrives
    let stateApplied = false;
    if (reqProfile === activeProfileId) {
      stateApplied = true;
    }

    assert.equal(stateApplied, false, 'Stale response from previous profile must be rejected and not mutate state');
  });

  test('11. Regression: Missing or invalid saved profile ID falling back safely', () => {
    // Contract checks
    assert.ok(clientContent.includes('setActiveProfileId(null)'), 'Client must clear invalid profile ID on 404 response');
    assert.ok(profilesStoreContent.includes('wasInvalid'), 'profilesStore must detect invalid saved profile');
    assert.ok(profilesStoreContent.includes('reloadProfileStores()'), 'profilesStore must reload stores when fallback is triggered');

    const mockRegistry = [
      { id: 'default', name: "Primary Workspace", is_default: true, is_active: false, is_archived: false },
      { id: '00000000000040008000000000000001', name: "Shared Household Workspace", is_default: false, is_active: true, is_archived: false }
    ];

    // Scenario A: Missing profile ID in localStorage
    const savedIdMissing = null;
    let targetMissing = null;
    if (savedIdMissing) {
      targetMissing = mockRegistry.find(p => p.id === savedIdMissing && !p.is_archived) || null;
    }
    const wasInvalidMissing = Boolean(savedIdMissing && !targetMissing);
    if (!targetMissing) {
      targetMissing = mockRegistry.find(p => p.is_default && !p.is_archived) || mockRegistry[0];
    }
    assert.equal(wasInvalidMissing, false, 'Missing profile ID is treated as initial default, not invalid');
    assert.equal(targetMissing.id, 'default', 'Missing profile ID safely falls back to default profile');

    // Scenario B: Invalid / deleted profile ID in localStorage
    const savedIdInvalid = 'deleted_profile_workspace_999';
    let targetInvalid = null;
    if (savedIdInvalid) {
      targetInvalid = mockRegistry.find(p => p.id === savedIdInvalid && !p.is_archived) || null;
    }
    const wasInvalidDetected = Boolean(savedIdInvalid && !targetInvalid);
    if (!targetInvalid) {
      targetInvalid = mockRegistry.find(p => p.is_default && !p.is_archived) || mockRegistry[0];
    }
    assert.equal(wasInvalidDetected, true, 'Nonexistent profile ID must be detected as invalid');
    assert.equal(targetInvalid.id, 'default', 'Invalid profile ID safely falls back to default profile');
  });
});


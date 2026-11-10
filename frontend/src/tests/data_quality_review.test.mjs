import { test, describe, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { registerHooks } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';

const SRC_DIR = path.resolve('src');

function readFile(subpath) {
  return fs.readFileSync(path.join(SRC_DIR, subpath), 'utf8');
}

registerHooks({
  resolve(specifier, context, nextResolve) {
    if (
      (specifier.startsWith('./') || specifier.startsWith('../')) &&
      !specifier.endsWith('.ts') &&
      !specifier.endsWith('.js') &&
      !specifier.endsWith('.mjs')
    ) {
      const parentDir = context.parentURL
        ? path.dirname(fileURLToPath(context.parentURL))
        : process.cwd();
      const tsCandidate = path.resolve(parentDir, `${specifier}.ts`);
      if (fs.existsSync(tsCandidate)) {
        return nextResolve(pathToFileURL(tsCandidate).href, context);
      }
    }
    return nextResolve(specifier, context);
  },
});

function installMockBrowserGlobals() {
  const storageMap = new Map();
  const mockLocalStorage = {
    getItem: (k) => (storageMap.has(k) ? storageMap.get(k) : null),
    setItem: (k, v) => storageMap.set(k, String(v)),
    removeItem: (k) => storageMap.delete(k),
    clear: () => storageMap.clear(),
  };
  globalThis.window = {
    localStorage: mockLocalStorage,
    addEventListener: () => {},
    URL: {
      createObjectURL: () => 'blob:mock',
      revokeObjectURL: () => {},
    },
  };
  globalThis.localStorage = mockLocalStorage;
  globalThis.document = {
    createElement: () => ({ href: '', download: '', click: () => {} }),
    body: { appendChild: () => {}, removeChild: () => {} },
  };
  return { storageMap };
}

function jsonResp(data, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: 'OK',
    headers: { get: (name) => (String(name).toLowerCase() === 'content-type' ? 'application/json' : null) },
    json: async () => data,
  };
}

describe('Finance Hub Data Quality & Review Area Suite', () => {
  beforeEach(() => {
    installMockBrowserGlobals();
  });

  test('1. Runtime Pinia reviewStore: filtering, safe actions, dismiss/restore, and profile switch race protection', async () => {
    const requests = [];
    let delayProfileAResolve = null;

    globalThis.fetch = async (url, init = {}) => {
      const u = String(url);
      requests.push({
        url: u,
        method: init.method || 'GET',
        headers: init.headers || {},
        body: init.body ? JSON.parse(init.body) : null,
      });

      if (u.includes('/review/findings') && init.headers?.['X-Profile-ID'] === 'default' && u.includes('finding_type=uncategorised')) {
        return new Promise((resolve) => {
          delayProfileAResolve = () =>
            resolve(
              jsonResp({
                profile_id: 'default',
                app_timezone: 'Europe/London',
                base_currency: 'GBP',
                confidence_settings: { category: 'balanced', account: 'balanced' },
                summary: { total_active: 99, dismissed_count: 0, by_type: { uncategorised: 99 }, by_severity: {}, scanned_transactions_count: 10, scanned_staging_count: 0 },
                filtered_count: 1,
                findings: [{ id: 'stale_a', finding_type: 'uncategorised', severity: 'suggestion', confidence: 'medium', title: 'Stale Alpha', summary: 'Should be ignored', reasons: [], source: 'ledger', subtype: 'missing_category', record_kind: 'ledger', can_dismiss: true, is_dismissed: false }],
              })
            );
        });
      }

      if (u.includes('/review/findings')) {
        const pid = init.headers?.['X-Profile-ID'] || 'default';
        return jsonResp({
          profile_id: pid,
          app_timezone: 'Europe/London',
          base_currency: 'GBP',
          confidence_settings: { category: 'balanced', account: 'balanced' },
          summary: {
            total_active: 2,
            dismissed_count: 1,
            by_type: { uncategorised: 1, potential_duplicate: 1 },
            by_severity: { suggestion: 1, review: 1, integrity: 0 },
            scanned_transactions_count: 12,
            scanned_staging_count: 1,
          },
          filtered_count: 2,
          findings: [
            {
              id: 'dq_uncat_tx_10',
              finding_type: 'uncategorised',
              severity: 'suggestion',
              confidence: 'high',
              title: 'Uncategorised expense',
              summary: 'Needs category',
              reasons: ['No category assigned'],
              source: 'ledger',
              subtype: 'missing_category',
              record_kind: 'ledger',
              transaction_id: 10,
              can_dismiss: true,
              is_dismissed: false,
              suggested_action: 'assign_category',
              ledger_url: '/ledger?date_preset=all&category_id=uncategorized',
            },
            {
              id: 'dup_ledger_ledger_20_21',
              finding_type: 'potential_duplicate',
              severity: 'review',
              confidence: 'high',
              title: 'Possible duplicate',
              summary: 'Dup pair',
              reasons: ['Exact amount'],
              source: 'ledger',
              subtype: 'ledger_ledger',
              record_kind: 'ledger',
              transaction_id: 21,
              can_dismiss: true,
              is_dismissed: false,
              suggested_action: 'delete_duplicate_ledger',
            },
          ],
        });
      }

      if (u.includes('/transactions/suggestions')) {
        return jsonResp({ duplicate_suggestions: [], transfer_suggestions: [], summary: { duplicates_count: 0, transfers_count: 0 } });
      }
      if (u.includes('/staging/count')) {
        return jsonResp({ pending_count: 0 });
      }
      if (u.includes('/transactions/deleted/summary')) {
        return jsonResp({ total_deleted: 1, total_pence: 500, formatted_total: '£5.00', transfers_count: 0, receipts_count: 0 });
      }
      if (u.includes('/transactions/bulk-delete')) {
        return jsonResp({ deleted_count: 1, batch_id: 'batch_dq_1', affected_transfers_count: 0, affected_receipts_count: 0, affected_ids: [21], message: 'Deleted 1' });
      }
      if (u.includes('/transactions/10')) {
        return jsonResp({ id: 10 });
      }
      if (u.includes('/transactions')) {
        return jsonResp({ items: [], total: 0, limit: 25, offset: 0 });
      }
      if (u.includes('/review/dismiss') || u.includes('/review/restore-dismissed')) {
        return jsonResp({ success: true, restored_count: 1 });
      }
      return jsonResp([]);
    };

    const { createPinia, setActivePinia } = await import('pinia');
    setActivePinia(createPinia());

    const { setActiveProfileId } = await import(pathToFileURL(path.join(SRC_DIR, 'api/client.ts')).href);
    const { useReviewStore } = await import(pathToFileURL(path.join(SRC_DIR, 'stores/review.ts')).href);

    setActiveProfileId('default');
    const reviewStore = useReviewStore();
    await reviewStore.loadFindings();

    assert.equal(reviewStore.activeCount, 2);
    assert.equal(reviewStore.selectedFinding?.id, 'dq_uncat_tx_10');

    // Explicit category assignment calls PUT /transactions/10 and refreshes
    await reviewStore.assignCategory(10, 3);
    const putCall = requests.find((r) => r.method === 'PUT' && r.url.endsWith('/transactions/10'));
    assert.ok(putCall, 'assignCategory must call PUT /api/transactions/{id}');
    assert.deepEqual(putCall.body, { category_id: 3 });

    // Confirm ledger duplicate soft delete calls POST /transactions/bulk-delete cleanly
    await reviewStore.confirmSoftDeleteLedgerDuplicate(21);
    const delCall = requests.find((r) => r.method === 'POST' && r.url.endsWith('/transactions/bulk-delete'));
    assert.ok(delCall, 'confirmSoftDeleteLedgerDuplicate must use recoverable bulk-delete');
    assert.deepEqual(delCall.body, { transaction_ids: [21] });

    // Dismiss & restore roundtrip
    await reviewStore.dismissFinding('dq_uncat_tx_10');
    const dismCall = requests.find((r) => r.method === 'POST' && r.url.endsWith('/review/dismiss'));
    assert.deepEqual(dismCall.body, { finding_id: 'dq_uncat_tx_10' });

    await reviewStore.restoreDismissed('dq_uncat_tx_10');
    const restCall = requests.find((r) => r.method === 'POST' && r.url.endsWith('/review/restore-dismissed'));
    assert.deepEqual(restCall.body, { finding_id: 'dq_uncat_tx_10', restore_all: false });

    // Workspace switch while Profile A request is in-flight drops stale Profile A payload
    reviewStore.selectedFindingType = 'uncategorised';
    const stalePromise = reviewStore.loadFindings();
    setActiveProfileId('workspace_b');
    reviewStore.reset();
    await reviewStore.loadFindings();
    delayProfileAResolve?.();
    await stalePromise;

    assert.equal(reviewStore.report?.profile_id, 'workspace_b', 'Stale workspace response must never overwrite active profile report');
    assert.equal(reviewStore.selectedFindingType, 'all', 'reset() must restore filters cleanly on workspace switch');
  });

  test('2. UI Navigation, Routes, Preserved Drilldown Links, Confirmation Modals & Undo Contracts', () => {
    const router = readFile('router/index.ts');
    const header = readFile('components/CommandHeader.vue');
    const profiles = readFile('stores/profiles.ts');
    const view = readFile('views/DataQualityView.vue');
    const ledger = readFile('views/LedgerView.vue');
    const staging = readFile('views/StagingView.vue');

    // Routes & header nav (desktop + mobile)
    assert.ok(router.includes("path: '/review'"), 'Router must expose /review route');
    assert.ok(router.includes("path: '/data-quality'"), 'Router must redirect /data-quality -> /review');
    assert.ok(header.includes('to="/review"'), 'Header must expose Review navigation link');
    assert.ok(header.includes('data-testid="header-review-badge"'), 'Header must surface active review count badge');

    // Profile switch resets & reloads review store
    assert.ok(profiles.includes('reviewStore.reset?.()'), 'Profile switch must reset review store');
    assert.ok(profiles.includes('reviewStore.loadFindings()'), 'Profile switch must reload active profile findings');

    // DataQualityView calm review UX, filters, detail view, confirmations & reversible dismiss
    for (const marker of [
      'data-testid="review-summary-cards"',
      'data-testid="review-category-cards"',
      'data-testid="review-filters-bar"',
      'data-testid="review-search-input"',
      'data-testid="review-type-select"',
      'data-testid="review-severity-select"',
      'data-testid="review-account-select"',
      'data-testid="review-category-select"',
      'data-testid="review-loading-state"',
      'data-testid="review-empty-state"',
      'data-testid="review-findings-list"',
      'data-testid="review-detail-panel"',
      'data-testid="review-detail-reasons"',
      'data-testid="review-assign-category-select"',
      'data-testid="review-assign-account-select"',
      'data-testid="review-open-ledger-link"',
      'data-testid="review-open-queue-link"',
      'data-testid="review-dismiss-btn"',
      'data-testid="review-restore-btn"',
      'data-testid="toggle-dismissed-btn"',
      'data-testid="restore-all-dismissed-btn"',
      'data-testid="review-confirm-modal"',
      'data-testid="review-confirm-execute-btn"',
      'data-testid="review-undo-toast"',
    ]) {
      assert.ok(view.includes(marker), `DataQualityView must include ${marker}`);
    }

    // Ledger and Queue deep-link preservation safeguards
    assert.ok(
      ledger.includes('hasExplicitQuery') && ledger.includes('txStore.filters.q = \'\''),
      'LedgerView.syncFiltersFromRoute must reset omitted Ledger-only filters on explicit deep links'
    );
    assert.ok(
      staging.includes('applyQueueRouteParams') && staging.includes('queue-open-review-link'),
      'StagingView must honor deep-link query params (?tab, ?item_id, ?status) and link to /review'
    );
  });
});

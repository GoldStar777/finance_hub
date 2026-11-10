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

// Resolve extensionless local .ts imports cleanly for native Node test execution
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

describe('Finance Hub Repeat Transaction Entry Suite', () => {
  beforeEach(() => {
    installMockBrowserGlobals();
  });

  test('1. Runtime repeatDates helper: frequencies, month-end clamping, leap-year & validation', async () => {
    const {
      generateRepeatPreview,
      suggestDefaultEndDate,
      createSubmissionKey,
      formatDateInTimeZone,
      MAX_REPEAT_OCCURRENCES,
    } = await import(pathToFileURL(path.join(SRC_DIR, 'utils/repeatDates.ts')).href);

    // Weekly and biweekly across year boundary
    const weekly = generateRepeatPreview({
      firstDate: '2026-12-25',
      frequency: 'weekly',
      endMode: 'count',
      occurrenceCount: 3,
      todayLocalIso: '2027-01-01',
      minCount: 2,
    });
    assert.deepEqual(
      weekly.dates.map((d) => [d.date, d.status]),
      [
        ['2026-12-25', 'past'],
        ['2027-01-01', 'today'],
        ['2027-01-08', 'planned'],
      ]
    );

    const biweekly = generateRepeatPreview({
      firstDate: '2026-11-01',
      frequency: 'biweekly',
      endMode: 'end_date',
      lastDate: '2026-12-01',
      todayLocalIso: '2026-11-10',
      minCount: 1,
    });
    assert.deepEqual(
      biweekly.dates.map((d) => d.date),
      ['2026-11-01', '2026-11-15', '2026-11-29']
    );

    // Profile timezone formatting produces YYYY-MM-DD cleanly
    const fixedInstant = new Date('2026-03-29T23:30:00.000Z');
    assert.equal(formatDateInTimeZone(fixedInstant, 'Europe/London'), '2026-03-30');
    assert.equal(formatDateInTimeZone(fixedInstant, 'America/New_York'), '2026-03-29');

    // Month-end 31st stays anchored to 31 on return to March & May
    const monthly31 = generateRepeatPreview({
      firstDate: '2026-01-31',
      frequency: 'monthly',
      endMode: 'count',
      occurrenceCount: 5,
      todayLocalIso: '2026-03-15',
      minCount: 2,
    });
    assert.equal(monthly31.error, null);
    assert.equal(monthly31.totalCount, 5);
    assert.deepEqual(
      monthly31.dates.map((d) => d.date),
      ['2026-01-31', '2026-02-28', '2026-03-31', '2026-04-30', '2026-05-31']
    );
    assert.equal(monthly31.dates[1].isClamped, true);
    assert.equal(monthly31.dates[2].isClamped, false);
    assert.equal(monthly31.dates[3].isClamped, true);
    assert.equal(monthly31.activeCount, 2);   // Jan 31, Feb 28 (<= 2026-03-15)
    assert.equal(monthly31.plannedCount, 3);  // Mar 31, Apr 30, May 31 (> 2026-03-15)

    // Leap year Feb 29 -> non-leap Feb 28 -> next leap year Feb 29
    const leapYearly = generateRepeatPreview({
      firstDate: '2024-02-29',
      frequency: 'yearly',
      endMode: 'count',
      occurrenceCount: 5,
      todayLocalIso: '2026-01-01',
      minCount: 2,
    });
    assert.deepEqual(
      leapYearly.dates.map((d) => d.date),
      ['2024-02-29', '2025-02-28', '2026-02-28', '2027-02-28', '2028-02-29']
    );
    assert.equal(leapYearly.dates[1].clampReason, 'Leap-day adjusted (29 -> 28 Feb)');
    assert.equal(leapYearly.dates[4].isClamped, false);

    // Quarterly & biweekly in end-date mode
    const quarterly = generateRepeatPreview({
      firstDate: '2025-11-30',
      frequency: 'quarterly',
      endMode: 'end_date',
      lastDate: '2026-08-30',
      todayLocalIso: '2026-05-30',
      minCount: 1,
    });
    assert.deepEqual(
      quarterly.dates.map((d) => d.date),
      ['2025-11-30', '2026-02-28', '2026-05-30', '2026-08-30']
    );
    assert.equal(quarterly.dates[2].status, 'today');
    assert.equal(quarterly.dates[3].status, 'planned');

    // End-date earlier than start date returns explicit error
    const badRange = generateRepeatPreview({
      firstDate: '2026-05-10',
      frequency: 'weekly',
      endMode: 'end_date',
      lastDate: '2026-05-01',
      todayLocalIso: '2026-05-01',
      minCount: 1,
    });
    assert.ok(badRange.error && badRange.error.includes('earlier'));

    // Excessive count triggers explicit cap error
    const tooMany = generateRepeatPreview({
      firstDate: '2026-01-01',
      frequency: 'weekly',
      endMode: 'count',
      occurrenceCount: MAX_REPEAT_OCCURRENCES + 1,
      todayLocalIso: '2026-01-01',
      minCount: 2,
    });
    assert.ok(tooMany.error && tooMany.error.includes(String(MAX_REPEAT_OCCURRENCES)));

    // Helper sanity
    assert.equal(suggestDefaultEndDate('2026-01-31', 'monthly', 3), '2026-03-31');
    const key1 = createSubmissionKey();
    const key2 = createSubmissionKey();
    assert.ok(key1.startsWith('repreq_'));
    assert.notEqual(key1, key2);
  });

  test('2. Runtime Pinia store: createRepeatTransactions sends Idempotency-Key & refreshes state cleanly', async () => {
    const requests = [];
    const jsonResp = (data, status = 200) => ({
      ok: status >= 200 && status < 300,
      status,
      statusText: status === 201 ? 'Created' : 'OK',
      headers: { get: (name) => (String(name).toLowerCase() === 'content-type' ? 'application/json' : null) },
      json: async () => data,
    });

    globalThis.fetch = async (url, init = {}) => {
      requests.push({
        url: String(url),
        method: init.method || 'GET',
        headers: init.headers || {},
        body: init.body ? JSON.parse(init.body) : null,
      });

      if (String(url).includes('/transactions/repeat')) {
        return jsonResp(
          {
            series_id: 'rep_abc123',
            idempotency_key: 'repreq_test_001',
            frequency: 'monthly',
            first_date: '2026-11-10',
            last_date: '2027-01-10',
            end_mode: 'count',
            created_count: 3,
            idempotent_replay: false,
            message: 'Created 3 independent transactions',
            items: [],
          },
          201
        );
      }
      if (String(url).includes('/transactions/suggestions') || String(url).includes('/review-suggestions')) {
        return jsonResp({ duplicate_suggestions: [], transfer_suggestions: [], summary: {} });
      }
      if (String(url).includes('/staging/count')) {
        return jsonResp({ pending_count: 0 });
      }
      if (String(url).includes('/transactions')) {
        return jsonResp({ items: [], total: 0, limit: 25, offset: 0 });
      }
      return jsonResp([]);
    };

    const { createPinia, setActivePinia } = await import('pinia');
    const pinia = createPinia();
    setActivePinia(pinia);

    const { useTransactionsStore } = await import(pathToFileURL(path.join(SRC_DIR, 'stores/transactions.ts')).href);
    const txStore = useTransactionsStore();

    const response = await txStore.createRepeatTransactions({
      transaction_type: 'expense',
      amount: 45,
      merchant: 'Internet Fiber',
      account_id: 1,
      category_id: 2,
      expense_nature: 'fixed',
      frequency: 'monthly',
      first_date: '2026-11-10',
      end_mode: 'count',
      occurrence_count: 3,
      idempotency_key: 'repreq_test_001',
    });

    assert.equal(response.series_id, 'rep_abc123');
    const repeatCall = requests.find((r) => r.url.endsWith('/transactions/repeat'));
    assert.ok(repeatCall, 'must call POST /transactions/repeat');
    assert.equal(repeatCall.method, 'POST');
    assert.equal(repeatCall.headers['Idempotency-Key'], 'repreq_test_001');
    assert.equal(repeatCall.body.occurrence_count, 3);

    // Triggered post-create refreshes (accounts, transactions, recent, staging)
    assert.ok(requests.some((r) => r.url.includes('/transactions?')), 'must refresh ledger & recent');
  });

  test('3. RecordTransactionModal UI contracts: repeat panel, month-end explanation, preview step & retry key lifecycle', () => {
    const modal = readFile('components/RecordTransactionModal.vue');
    const types = readFile('types/index.ts');
    const apiClient = readFile('api/client.ts');

    // TypeScript & API contracts
    assert.ok(types.includes('RepeatTransactionCreatePayload'), 'types must declare RepeatTransactionCreatePayload');
    assert.ok(types.includes('RepeatTransactionCreateResponse'), 'types must declare RepeatTransactionCreateResponse');
    assert.ok(types.includes('repeat_series_id?: string | null'), 'Transaction must expose optional repeat_series_id provenance');
    assert.ok(apiClient.includes('createRepeatTransactions:'), 'api client must expose createRepeatTransactions');

    // Modal repeat controls & preview step
    for (const marker of [
      'data-testid="repeat-transaction-section"',
      'data-testid="repeat-transaction-toggle"',
      'data-testid="repeat-frequency-select"',
      'data-testid="repeat-end-mode-count"',
      'data-testid="repeat-end-mode-end-date"',
      'data-testid="repeat-count-input"',
      'data-testid="repeat-last-date-input"',
      'data-testid="repeat-month-end-rule"',
      'data-testid="repeat-inline-summary"',
      'data-testid="repeat-preview-step"',
      'data-testid="repeat-preview-dates-list"',
      'data-testid="repeat-protection-notice"',
      'data-testid="repeat-edit-pattern-btn"',
      'data-testid="repeat-confirm-submit-btn"',
    ]) {
      assert.ok(modal.includes(marker), `RecordTransactionModal must contain ${marker}`);
    }

    // Retry & single-flight double-submit guards
    assert.ok(modal.includes('if (isSubmitting.value) return;'), 'Modal must prevent concurrent double-submits');
    assert.ok(
      modal.includes('repeatIdempotencyKey.value = createSubmissionKey();'),
      'Modal must assign a submission idempotency key per confirmed schedule'
    );
    assert.ok(
      modal.includes('if (!isRepeatPreviewStep.value) {\n      repeatIdempotencyKey.value = null;'),
      'Modal must rotate key only when pattern is edited, preserving the same key on timeout/error retry'
    );
  });
});

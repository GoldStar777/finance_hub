import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const SRC_DIR = path.resolve('src');

function readFile(subpath) {
  return fs.readFileSync(path.join(SRC_DIR, subpath), 'utf8');
}

describe('Finance Hub Import Pop-out Exclusion and Discard Contract Tests', () => {
  const modalContent = readFile('components/UnifiedImportModal.vue');
  const typesContent = readFile('types/index.ts');
  const clientContent = readFile('api/client.ts');

  test('1. Exclude one candidate: wiring, deduplication, and error resilience', () => {
    // Buttons wired to handlers
    assert.ok(modalContent.includes('@click="excludeItem(item, idx)"'), 'Must wire top-row exclude button to excludeItem');
    assert.ok(modalContent.includes('@click="excludeAsDuplicate(item, idx)"'), 'Must wire duplicate-box button to excludeAsDuplicate');

    // Safe repeated clicks and disable state
    assert.ok(modalContent.includes(':disabled="isDiscarding[item.id] || isCommitting"'), 'Exclude buttons must be disabled while action is in flight');
    assert.ok(modalContent.includes('if (isDiscarding.value[item.id] || isCommitting.value) return;'), 'discardItemFromStaging must guard against duplicate concurrent clicks');

    // API call, removal on confirmation, and queue refresh
    assert.ok(modalContent.includes('await api.discardStagingItem(item.id)'), 'Must call api.discardStagingItem with candidate ID');
    assert.ok(modalContent.includes('reviewItems.value.splice(idx, 1)'), 'Must remove candidate from pop-out on confirmation');
    assert.ok(modalContent.includes('await stagingStore.fetchCount()'), 'Must refresh review queue counter');

    // Error handling preserves candidate and displays error
    assert.ok(modalContent.includes('reviewError.value = err.message'), 'Must populate reviewError if exclude fails');
    assert.ok(modalContent.includes('delete isDiscarding.value[item.id]'), 'Must clean up discarding state in finally block');
  });

  test('2. Discard whole import: wiring, lifecycle, and progress indicator', () => {
    // Footer Discard button
    assert.ok(modalContent.includes('@click="handleDiscardAll"'), 'Footer must wire Discard button to handleDiscardAll');
    assert.ok(modalContent.includes(':disabled="isCommitting || isAnyDiscarding"'), 'Discard button must be disabled when action or exclusion is in flight');
    assert.ok(modalContent.includes("commitAction === 'discard'"), 'Discard button must show progress spinner when active');

    // Deduplication guard
    assert.ok(modalContent.includes('if (isCommitting.value || isAnyDiscarding.value) return;'), 'handleDiscardAll must guard against concurrent calls');

    // API call with action: discard_all
    assert.ok(modalContent.includes("action: 'discard_all'"), 'Must call commitUnifiedImport with action discard_all');
    assert.ok(modalContent.includes('await stagingStore.fetchCount()'), 'Must refresh review queue count after discarding whole import');
    assert.ok(modalContent.includes('handleClose()'), 'Must close or reset pop-out on successful discard');

    // Error resilience
    assert.ok(modalContent.includes("reviewError.value = err.message || 'Failed to discard batch.'"), 'Must populate reviewError if discard fails');
    assert.ok(modalContent.includes('commitAction.value = null'), 'Must reset commitAction in finally block');
  });

  test('3. Stage 2 error alert banner visibility and error dismissal', () => {
    // Review Stage error banner exists inside stage === 'review'
    assert.ok(modalContent.includes("stage === 'review' && importData"), 'Review stage container must exist');
    assert.ok(modalContent.includes('v-if="reviewError"'), 'Review stage must contain dedicated reviewError alert banner');
    assert.ok(modalContent.includes('@click="reviewError = null"'), 'Review error banner must provide close/dismiss button');
    assert.ok(modalContent.includes('The candidate remains in the list'), 'Error banner must inform user that candidates remain intact');
  });

  test('4. Cross-action locking: prevents conflicting actions while mutations are in progress', () => {
    // isAnyDiscarding computed state
    assert.ok(modalContent.includes('const isAnyDiscarding = computed'), 'Must compute isAnyDiscarding from isDiscarding state');

    // Footer actions locked when single discard is in flight
    assert.ok(modalContent.includes(':disabled="isCommitting || isAnyDiscarding"'), 'Send to Queue and Discard buttons must be locked while excluding single item');
    assert.ok(modalContent.includes(':disabled="isCommitting || !canApproveAll || isAnyDiscarding"'), 'Add to Ledger button must be locked while excluding single item');

    // Handlers respect locks
    assert.ok(modalContent.includes('if (!importData.value || !canApproveAll.value || isCommitting.value || isAnyDiscarding.value) return;'), 'handleApproveAll must respect mutation locks');
    assert.ok(modalContent.includes('if (!importData.value || isCommitting.value || isAnyDiscarding.value) return;'), 'handleQueueAll must respect mutation locks');
  });

  test('5. Type contracts for import commit response and API client', () => {
    // Types contract
    assert.ok(typesContent.includes('already_committed_count?: number'), 'UnifiedImportCommitResponse must declare already_committed_count');
    assert.ok(typesContent.includes('message?: string'), 'UnifiedImportCommitResponse must declare optional message');

    // API client methods and header propagation
    assert.ok(clientContent.includes("request<void>(`/staging/${id}`"), 'discardStagingItem must send DELETE /staging/{id}');
    assert.ok(clientContent.includes("request<UnifiedImportCommitResponse>('/staging/import-commit'"), 'commitUnifiedImport must send POST /staging/import-commit');
    assert.ok(clientContent.includes("headers['X-Profile-ID'] = currentProfileId"), 'All staging requests must propagate X-Profile-ID');
  });
});


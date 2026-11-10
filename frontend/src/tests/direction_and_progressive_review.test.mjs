import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

describe('Finance Hub Direction Inference and Progressive Review Contract Tests', () => {
  const modalPath = path.resolve('src/components/UnifiedImportModal.vue');
  const modalContent = fs.readFileSync(modalPath, 'utf-8');

  const typesPath = path.resolve('src/types/index.ts');
  const typesContent = fs.readFileSync(typesPath, 'utf-8');

  it('1. Direction Summary and evidence-based analysis banner', () => {
    // Types contract
    assert.match(typesContent, /interface DirectionSummary/, 'DirectionSummary interface must be declared in types');
    assert.match(typesContent, /expense_count:\s*number/, 'DirectionSummary must include expense_count');
    assert.match(typesContent, /income_count:\s*number/, 'DirectionSummary must include income_count');
    assert.match(typesContent, /uncertain_count:\s*number/, 'DirectionSummary must include uncertain_count');
    assert.match(typesContent, /evidence_type:\s*string/, 'DirectionSummary must include evidence_type');
    assert.match(typesContent, /evidence_description:\s*string/, 'DirectionSummary must include evidence_description');

    // UI banner and batch controls
    assert.match(modalContent, /Transaction Direction Analysis/, 'Modal must display Direction Analysis header');
    assert.match(modalContent, /invertAllDirections/, 'Modal must provide invertAllDirections batch action');
    assert.match(modalContent, /setAllUncertainTo\('expense'\)/, 'Modal must allow setting uncertain rows to Expense');
    assert.match(modalContent, /setAllUncertainTo\('income'\)/, 'Modal must allow setting uncertain rows to Income');
    assert.match(modalContent, /direction_uncertain/, 'Item must track direction_uncertain');
  });

  it('2. Progressive Review Dashboard Cards', () => {
    assert.match(modalContent, /Ready to Add/, 'Dashboard must show Ready to Add metric');
    assert.match(modalContent, /Needs Review/, 'Dashboard must show Needs Review metric');
    assert.match(modalContent, /Added to Ledger/, 'Dashboard must show Added to Ledger metric');
    assert.match(modalContent, /Excluded/, 'Dashboard must show Excluded metric');

    assert.match(modalContent, /readyToAddCount/, 'Modal must compute readyToAddCount');
    assert.match(modalContent, /needsReviewCount/, 'Modal must compute needsReviewCount');
    assert.match(modalContent, /alreadyAddedCount/, 'Modal must track alreadyAddedCount');
    assert.match(modalContent, /excludedCount/, 'Modal must track excludedCount');
  });

  it('3. Row-level Faster Review Actions (Approve & Next, Skip, Apply to Similar)', () => {
    assert.match(modalContent, /approveRowAndNext/, 'Modal must implement row-level approveRowAndNext');
    assert.match(modalContent, /skipItem/, 'Modal must implement row-level skipItem');
    assert.match(modalContent, /openApplyToSimilar/, 'Modal must implement openApplyToSimilar');
    assert.match(modalContent, /⚡️ Apply to similar/, 'Modal must render Apply to Similar button');
    assert.match(modalContent, /✓ Approve & next/, 'Modal must render Approve & Next button');
  });

  it('4. Apply to Similar Modal with safe current-import scoping and optional profile persistence', () => {
    assert.match(modalContent, /isSimilarModalOpen/, 'Modal must track isSimilarModalOpen state');
    assert.match(modalContent, /similarApplyType/, 'Modal must allow toggling type propagation');
    assert.match(modalContent, /similarApplyCategory/, 'Modal must allow toggling category propagation');
    assert.match(modalContent, /similarApplyAccount/, 'Modal must allow toggling account propagation');
    assert.match(modalContent, /similarRememberFuture/, 'Modal must have future profile persistence option');

    // Verify default safety: unchecked by default
    assert.match(modalContent, /similarRememberFuture\s*=\s*ref\(false\)/, 'Remember for future imports must be false by default');
    assert.match(modalContent, /normalizeMerchant/, 'Modal must use normalizeMerchant to match vendor names reliably');
    assert.match(modalContent, /applyToSimilarConfirm/, 'Modal must confirm batch application across matching items');
  });

  it('5. Footer progressive commit: Add Reviewed to Ledger without blocking on unresolved items', () => {
    assert.match(modalContent, /handleApproveReviewed/, 'Modal must provide progressive handleApproveReviewed');
    assert.match(modalContent, /Add Reviewed to Ledger \(\{\{ readyToAddCount \}\}\)/, 'Modal must display Add Reviewed button with count');
    assert.match(modalContent, /action:\s*'approve_selected'/, 'Progressive commit must use approve_selected');
  });
});


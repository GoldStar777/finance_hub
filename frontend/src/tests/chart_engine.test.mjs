import { test, describe } from 'node:test';
import assert from 'node:assert';
import {
  computeNiceScale,
  formatAxisCurrency,
  formatTooltipCurrency,
  getVisibleTickIndices,
  computeTooltipCoords,
  buildSvgPath,
  buildSegmentedPaths,
} from '../utils/chartEngine.ts';

describe('Finance Hub Analysis Chart Engine Core Tests', () => {
  test('1. computeNiceScale handles positive, zero, and negative ranges with rounded bounds', () => {
    // Standard positive range (£0 to £4,500)
    const pos = computeNiceScale(0, 450000, 200, 20);
    assert.strictEqual(pos.minPence, 0);
    assert.ok(pos.maxPence >= 450000);
    assert.ok(pos.ticks.length >= 3);
    assert.ok(pos.ticks.some(t => t.isZero));

    // Spanning negative and positive (-£200 to £800)
    const span = computeNiceScale(-20000, 80000, 200, 20);
    assert.ok(span.minPence <= -20000);
    assert.ok(span.maxPence >= 80000);
    assert.ok(span.ticks.some(t => t.isZero), 'Zero tick must be explicitly present when range spans 0');
    assert.ok(span.zeroY > 20 && span.zeroY < 220, 'zeroY must be within chart plot bounds');

    // All zero range
    const zero = computeNiceScale(0, 0, 200, 20);
    assert.strictEqual(zero.minPence, 0);
    assert.ok(zero.maxPence > 0, 'Zero range must provide fallback headroom');
    assert.ok(zero.ticks.length >= 3);

    // Narrow positive range (£500 to £510)
    const narrow = computeNiceScale(50000, 51000, 200, 20, { forceZero: false });
    assert.ok(narrow.minPence <= 50000);
    assert.ok(narrow.maxPence >= 51000);
  });

  test('2. formatAxisCurrency formats compact labels accurately', () => {
    assert.strictEqual(formatAxisCurrency(0, 'GBP', '£'), '£0');
    assert.strictEqual(formatAxisCurrency(5000, 'GBP', '£'), '£50');
    assert.strictEqual(formatAxisCurrency(150000, 'GBP', '£'), '£1.5k');
    assert.strictEqual(formatAxisCurrency(2500000, 'GBP', '£'), '£25k');
    assert.strictEqual(formatAxisCurrency(100000000, 'GBP', '£'), '£1M');
    assert.strictEqual(formatAxisCurrency(-50000, 'GBP', '£'), '-£500');
    assert.strictEqual(formatAxisCurrency(-125000, 'GBP', '£'), '-£1.3k');
  });

  test('3. formatTooltipCurrency formats full 2-decimal precision', () => {
    assert.strictEqual(formatTooltipCurrency(0, 'GBP', '£'), '£0.00');
    assert.strictEqual(formatTooltipCurrency(123456, 'GBP', '£'), '£1,234.56');
    assert.strictEqual(formatTooltipCurrency(-98765, 'GBP', '£'), '-£987.65');
  });

  test('4. getVisibleTickIndices decimates dense ticks and always includes first and last', () => {
    // Small point count fits comfortably
    const small = getVisibleTickIndices(5, 600, 68);
    assert.strictEqual(small.size, 5);

    // Dense point count (365 days)
    const dense = getVisibleTickIndices(365, 600, 68);
    assert.ok(dense.size <= 12, 'Dense points must be decimated');
    assert.ok(dense.has(0), 'First tick must always be included');
    assert.ok(dense.has(364), 'Last tick must always be included');
  });

  test('5. computeTooltipCoords clamps inside chart viewport and flips if near top', () => {
    // Normal position
    const normal = computeTooltipCoords(300, 150, 600, 250);
    assert.ok(normal.left >= 10);
    assert.ok(normal.top >= 8);
    assert.strictEqual(normal.placeBelow, false);

    // Near top edge flips below
    const nearTop = computeTooltipCoords(300, 10, 600, 250);
    assert.strictEqual(nearTop.placeBelow, true);
    assert.ok(nearTop.top > 10);

    // Near right edge clamps horizontally
    const nearRight = computeTooltipCoords(590, 150, 600, 250);
    assert.ok(nearRight.left + 210 <= 600);
  });

  test('6. buildSegmentedPaths separates solid vs dashed and breaks on unavailable points', () => {
    const points = [
      { x: 10, y: 100, isAvailable: true, isDashed: false },
      { x: 20, y: 90, isAvailable: true, isDashed: false },
      { x: 30, y: 80, isAvailable: true, isDashed: true }, // Transition to dashed (e.g. planned or inferred)
      { x: 40, y: 70, isAvailable: true, isDashed: true },
      { x: 50, y: 60, isAvailable: false },                 // Unavailable gap (e.g. missing valuation)
      { x: 60, y: 50, isAvailable: true, isDashed: false },
      { x: 70, y: 40, isAvailable: true, isDashed: false },
    ];

    const result = buildSegmentedPaths(points);
    assert.ok(result.solidPaths.length >= 2, 'Should have solid segments before and after gap');
    assert.ok(result.dashedPaths.length >= 1, 'Should have dashed segment');
    // Ensure no path connects across x=50
    for (const p of [...result.solidPaths, ...result.dashedPaths]) {
      assert.ok(!p.includes('50.0 60.0'), 'Path must never include unavailable point');
    }
  });
});

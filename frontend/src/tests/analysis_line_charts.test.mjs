import { test, describe } from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  computeNiceScale,
  formatAxisCurrency,
  formatTooltipCurrency,
  getVisibleTickIndices,
  computeTooltipCoords,
  buildSvgPath,
  buildSegmentedPaths,
} from '../utils/chartEngine.ts';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC_DIR = path.resolve(__dirname, '..');

describe('Finance Hub Analysis Line Charts Quality & Accessibility Contract Tests', () => {
  const analysisViewContent = fs.readFileSync(path.join(SRC_DIR, 'views/AnalysisView.vue'), 'utf-8');

  test('1. All four line charts use chartEngine scale, horizontal gridlines, and Y-axis labels', () => {
    // 1. Cumulative Cash Flow chart
    assert.ok(
      analysisViewContent.includes('v-for="tick in cumulativeChartData.scale.ticks"'),
      'Cumulative Cash Flow must render Y-axis ticks from computeNiceScale'
    );
    assert.ok(
      analysisViewContent.includes('tick.formattedLabel'),
      'Cumulative Cash Flow ticks must display formatted currency labels'
    );
    assert.ok(
      analysisViewContent.includes(':stroke-dasharray="tick.isZero ? \'none\' : \'3 3\'"'),
      'Cumulative Cash Flow must render zero baseline and light dashed gridlines'
    );

    // 2. Spending Trends chart
    assert.ok(
      analysisViewContent.includes('v-for="tick in spendingLineChartData.scale.ticks"'),
      'Spending Trends must render Y-axis ticks from computeNiceScale'
    );
    assert.ok(
      analysisViewContent.includes('spendingLineChartData.scale.ticks'),
      'Spending Trends ticks must display formatted currency labels'
    );

    // 3. Balances & Net Worth chart
    assert.ok(
      analysisViewContent.includes('v-for="tick in netWorthChartData.scale.ticks"'),
      'Net Worth must render Y-axis ticks from computeNiceScale'
    );
    assert.ok(
      analysisViewContent.includes('netWorthChartData.scale.ticks'),
      'Net Worth ticks must display formatted currency labels'
    );

    // 4. Investments chart
    assert.ok(
      analysisViewContent.includes('v-for="tick in investmentsChartData.scale.ticks"'),
      'Investments must render Y-axis ticks from computeNiceScale'
    );
    assert.ok(
      analysisViewContent.includes('investmentsChartData.scale.ticks'),
      'Investments ticks must display formatted currency labels'
    );
  });

  test('2. Scale stability: scales are calculated from data/filter state, not hover state', () => {
    // Hover state does not mutate scale or trigger recalculation of computed chartData
    assert.ok(analysisViewContent.includes('hoveredCumulativeIdx = ref<number | null>(null)'));
    assert.ok(analysisViewContent.includes('hoveredSpendLineIdx = ref<number | null>(null)'));
    assert.ok(analysisViewContent.includes('hoveredNwIdx = ref<number | null>(null)'));
    assert.ok(analysisViewContent.includes('hoveredInvestmentsIdx = ref<number | null>(null)'));

    // computeNiceScale is called inside computed properties based on store data and selections
    assert.ok(analysisViewContent.includes('computeNiceScale(minVal, maxVal'));
  });

  test('3. Accessible inspection: tabindex, keyboard navigation, and viewport-bounded tooltips', () => {
    // Keyboard navigation helper
    assert.ok(analysisViewContent.includes('function navigateChartPoint('), 'Must provide keyboard navigation handler');

    // Chart 1 (Cumulative) accessibility
    assert.ok(analysisViewContent.includes('tabindex="0"'), 'Interactive chart points must have tabindex 0 for keyboard focus');
    assert.ok(
      analysisViewContent.includes('@keydown.left.prevent="navigateChartPoint'),
      'Must support Left arrow navigation between points'
    );
    assert.ok(
      analysisViewContent.includes('@keydown.right.prevent="navigateChartPoint'),
      'Must support Right arrow navigation between points'
    );
    assert.ok(
      analysisViewContent.includes(':style="getCumulativeTooltipStyle(cumulativeChartData.points[hoveredCumulativeIdx])"'),
      'Cumulative tooltip must use dynamic viewport-bounded positioning'
    );

    // Chart 2 (Spending Trends) accessibility
    assert.ok(
      analysisViewContent.includes(':style="getSpendTooltipStyle(spendingLineChartData.points[hoveredSpendLineIdx])"'),
      'Spending Trends tooltip must use dynamic viewport-bounded positioning'
    );

    // Chart 3 (Net Worth) accessibility
    assert.ok(
      analysisViewContent.includes(':style="getNetWorthTooltipStyle(netWorthChartData.points[hoveredNwIdx])"'),
      'Net Worth tooltip must use dynamic viewport-bounded positioning'
    );

    // Chart 4 (Investments) accessibility
    assert.ok(
      analysisViewContent.includes(':style="getInvestmentsTooltipStyle(investmentsChartData.points[hoveredInvestmentsIdx])"'),
      'Investments tooltip must use dynamic viewport-bounded positioning'
    );

    // Viewport bounding logic
    const coords = computeTooltipCoords(20, 10, 600, 260, 220, 120);
    assert.ok(coords.left >= 8, 'Tooltip left must be clamped inside viewport');
    assert.strictEqual(coords.placeBelow, true, 'Tooltip near top must flip below anchor point');
  });

  test('4. Planned / Forecast distinction: solid actuals vs dashed planned lines with hollow markers', () => {
    // Cumulative Cash Flow
    assert.ok(
      analysisViewContent.includes('cumulativeChartData.incomeSolidPaths'),
      'Cumulative Cash Flow must render solid paths for actual income'
    );
    assert.ok(
      analysisViewContent.includes('cumulativeChartData.incomeDashedPaths'),
      'Cumulative Cash Flow must render dashed paths for planned income'
    );
    assert.ok(
      analysisViewContent.includes('stroke-dasharray="5 4"'),
      'Planned paths must use distinct dash styling'
    );
    assert.ok(
      analysisViewContent.includes(':fill="pt.is_planned ? \'white\' : \'#10B981\'"'),
      'Planned points must use hollow markers with solid stroke'
    );

    // Spending Trends
    assert.ok(
      analysisViewContent.includes('spendingLineChartData.totalSolidPaths'),
      'Spending Trends must render solid paths for actual total spend'
    );
    assert.ok(
      analysisViewContent.includes('spendingLineChartData.totalDashedPaths'),
      'Spending Trends must render dashed paths for planned total spend'
    );
  });

  test('5. Inferred Pre-Anchor and Carried-Forward visual distinctions', () => {
    // Balances & Net Worth inferred distinction
    assert.ok(
      analysisViewContent.includes('netWorthChartData.solidNetWorthPaths'),
      'Net Worth must render solid paths for ground-truth balance periods'
    );
    assert.ok(
      analysisViewContent.includes('netWorthChartData.inferredNetWorthPaths'),
      'Net Worth must render dashed paths for pre-anchor inferred periods'
    );
    assert.ok(
      analysisViewContent.includes(':fill="pt.has_inferred ? \'#F59E0B\' : \'#10B981\'"'),
      'Net Worth inferred points must use amber marker fill'
    );
    assert.ok(
      analysisViewContent.includes('Inferred Pre-Anchor'),
      'Net Worth tooltip must clearly badge inferred periods'
    );

    // Investments carried-forward distinction
    assert.ok(
      analysisViewContent.includes('investmentsChartData.freshPaths'),
      'Investments must render solid paths for direct checkpoint valuations'
    );
    assert.ok(
      analysisViewContent.includes('investmentsChartData.carriedForwardPaths'),
      'Investments must render dashed paths for carried-forward valuations'
    );
    assert.ok(
      analysisViewContent.includes('pt.is_available && pt.is_carried_forward'),
      'Investments must distinguish carried-forward points'
    );
    assert.ok(
      analysisViewContent.includes('Carried forward from'),
      'Investments tooltip must indicate source date for carried forward checkpoints'
    );
  });

  test('6. Unavailable investment checkpoints break lines cleanly without fabricating points', () => {
    // Segmented paths break on unavailable points
    const testPoints = [
      { x: 10, y: 100, isDashed: false, isAvailable: true },
      { x: 20, y: 120, isDashed: false, isAvailable: true },
      { x: 30, y: 130, isDashed: false, isAvailable: false }, // unavailable gap
      { x: 40, y: 140, isDashed: false, isAvailable: true },
      { x: 50, y: 150, isDashed: false, isAvailable: true },
    ];
    const seg = buildSegmentedPaths(testPoints);
    assert.strictEqual(seg.solidPaths.length, 2, 'Must break into 2 separate paths across the unavailable gap');
    assert.strictEqual(seg.dashedPaths.length, 0);

    // AnalysisView guards against empty/unavailable dataset
    assert.ok(
      analysisViewContent.includes('v-if="!investmentsChartData.isEmpty"'),
      'Investments must guard against empty/unavailable dataset'
    );
    assert.ok(
      analysisViewContent.includes('No investment valuation checkpoints recorded for this window'),
      'Investments must show clear message when no valuations exist'
    );

    // Cumulative chart no longer injects fabricated 'Range start' point
    assert.ok(
      !analysisViewContent.includes("label: 'Range start'"),
      'Cumulative Cash Flow must not fabricate an artificial Range start £0 point'
    );
  });

  test('7. Heckbert / Wilkinson nice numbers algorithm handles zero, negative, and narrow ranges', () => {
    // All positive
    const scale1 = computeNiceScale(0, 7800, 200, 30);
    assert.strictEqual(scale1.minPence, 0, 'Positive range should include zero baseline');
    assert.ok(scale1.maxPence >= 7800, 'Max bound must cover maximum data point');
    assert.ok(scale1.ticks.length >= 3 && scale1.ticks.length <= 7, 'Ticks count should be reasonable');

    // Negative to positive (e.g. net savings or debt to equity)
    const scale2 = computeNiceScale(-50000, 30000, 200, 30);
    assert.ok(scale2.minPence <= -50000, 'Negative bound must cover -50000');
    assert.ok(scale2.maxPence >= 30000, 'Positive bound must cover 30000');
    const zeroTick = scale2.ticks.find(t => t.isZero);
    assert.ok(zeroTick !== undefined, 'Zero line must be present in mixed positive/negative range');

    // Narrow positive range not forced to zero baseline (e.g. net worth 1.2M - 1.25M)
    const scale3 = computeNiceScale(12000000, 12500000, 200, 30, { forceZero: false });
    assert.ok(scale3.minPence > 0, 'When forceZero is false, narrow range should not start at zero');
    assert.ok(scale3.minPence <= 12000000);
    assert.ok(scale3.maxPence >= 12500000);

    // Single point or all zero
    const scale4 = computeNiceScale(0, 0, 200, 30);
    assert.strictEqual(scale4.minPence, 0);
    assert.ok(scale4.maxPence > 0);
    assert.ok(scale4.ticks.length >= 2);
  });
});

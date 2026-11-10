/**
 * Finance Hub Analysis Chart Engine
 *
 * Provides:
 * - Robust "nice numbers" Y-axis scale calculation (Heckbert / Wilkinson algorithm).
 * - Currency formatting for axis ticks and tooltips according to active profile currency/locale.
 * - Responsive X-axis tick filtering to prevent overlap across screen sizes.
 * - Safe tooltip viewport bounding so tooltips never clip or obscure focal points.
 * - Segmented SVG path generation supporting solid, dashed, and broken/missing periods.
 */

export interface ChartScaleTick {
  valuePence: number;
  formattedLabel: string;
  y: number;
  isZero: boolean;
}

export interface ChartScaleResult {
  minPence: number;
  maxPence: number;
  stepPence: number;
  rangePence: number;
  zeroY: number;
  ticks: ChartScaleTick[];
  getY: (pence: number) => number;
}

export interface NiceScaleOptions {
  targetTicks?: number;
  forceZero?: boolean;
  padRatio?: number;
  currency?: string;
  currencySymbol?: string;
}

/**
 * Computes human-friendly rounded axis bounds and ticks.
 */
export function computeNiceScale(
  minPence: number,
  maxPence: number,
  plotHeight: number,
  paddingTop: number,
  options: NiceScaleOptions = {}
): ChartScaleResult {
  const targetTicks = Math.max(3, options.targetTicks ?? 5);
  const forceZero = options.forceZero ?? true;
  const currency = options.currency || 'GBP';
  const currencySymbol = options.currencySymbol || '£';

  let effMin = minPence;
  let effMax = maxPence;

  if (forceZero) {
    if (effMin > 0) effMin = 0;
    if (effMax < 0) effMax = 0;
  }

  // Handle zero/empty range
  if (effMin === effMax) {
    if (effMin === 0) {
      effMin = 0;
      effMax = 10000; // £100 default headroom
    } else if (effMin > 0) {
      effMin = 0;
      effMax = Math.round(effMax * 1.25);
    } else {
      effMax = 0;
      effMin = Math.round(effMin * 1.25);
    }
  }

  // Add subtle padding if range is very tight (< 5% difference)
  const rawRangePence = effMax - effMin;
  if (rawRangePence > 0 && !forceZero && (options.padRatio ?? 0) > 0) {
    const pad = Math.round(rawRangePence * (options.padRatio ?? 0.05));
    effMin -= pad;
    effMax += pad;
  }

  // Heckbert nice numbers algorithm (in pounds)
  const rangePounds = Math.max(1, (effMax - effMin) / 100);
  const rawStepPounds = rangePounds / (targetTicks - 1);
  const exponent = Math.floor(Math.log10(rawStepPounds));
  const fraction = rawStepPounds / Math.pow(10, exponent);

  let niceFraction: number;
  if (fraction <= 1.2) {
    niceFraction = 1;
  } else if (fraction <= 2.2) {
    niceFraction = 2;
  } else if (fraction <= 3.5) {
    niceFraction = 2.5;
  } else if (fraction <= 7.0) {
    niceFraction = 5;
  } else {
    niceFraction = 10;
  }

  const stepPounds = niceFraction * Math.pow(10, exponent);
  const stepPence = Math.max(100, Math.round(stepPounds * 100)); // Minimum 100p (£1) tick step

  let niceMinPence = Math.floor(effMin / stepPence) * stepPence;
  let niceMaxPence = Math.ceil(effMax / stepPence) * stepPence;

  if (forceZero && effMin >= 0 && niceMinPence < 0) {
    niceMinPence = 0;
  }
  if (forceZero && effMax <= 0 && niceMaxPence > 0) {
    niceMaxPence = 0;
  }

  const rangePence = Math.max(stepPence, niceMaxPence - niceMinPence);

  const getY = (val: number): number => {
    const clampedVal = Math.max(niceMinPence, Math.min(niceMaxPence, val));
    return paddingTop + plotHeight * ((niceMaxPence - clampedVal) / rangePence);
  };

  const zeroY = getY(0);

  // Generate tick array
  const ticks: ChartScaleTick[] = [];
  for (let val = niceMinPence; val <= niceMaxPence + stepPence / 2; val += stepPence) {
    // Avoid floating point jitter
    const roundedVal = Math.round(val);
    if (roundedVal > niceMaxPence + 1) break;
    ticks.push({
      valuePence: roundedVal,
      formattedLabel: formatAxisCurrency(roundedVal, currency, currencySymbol),
      y: getY(roundedVal),
      isZero: roundedVal === 0,
    });
  }

  return {
    minPence: niceMinPence,
    maxPence: niceMaxPence,
    stepPence,
    rangePence,
    zeroY,
    ticks,
    getY,
  };
}

/**
 * Formats a currency value for chart axes (compact, human-readable).
 * Examples: £0, £250, £1.5k, £25k, £1.2M, -£500, -£1.2k
 */
export function formatAxisCurrency(pence: number, _currency = 'GBP', symbol = '£'): string {
  if (pence === 0) return `${symbol}0`;

  const isNeg = pence < 0;
  const absPence = Math.abs(pence);
  const pounds = absPence / 100;
  const sign = isNeg ? '-' : '';

  if (pounds < 1000) {
    // Exact pound integer if whole, else 1 decimal if small
    const str = pounds % 1 === 0 ? pounds.toFixed(0) : pounds.toFixed(1);
    return `${sign}${symbol}${str}`;
  } else if (pounds < 1_000_000) {
    const k = pounds / 1000;
    const str = k >= 100 || k % 1 === 0 ? k.toFixed(0) : k.toFixed(1);
    return `${sign}${symbol}${str}k`;
  } else {
    const m = pounds / 1_000_000;
    const str = m >= 10 || m % 1 === 0 ? m.toFixed(0) : m.toFixed(1);
    return `${sign}${symbol}${str}M`;
  }
}

/**
 * Formats a currency value for tooltips with full 2-decimal precision.
 * Examples: £1,250.00, -£345.20, £0.00
 */
export function formatTooltipCurrency(pence: number, _currency = 'GBP', symbol = '£'): string {
  const isNeg = pence < 0;
  const absPence = Math.abs(pence);
  const pounds = absPence / 100;
  const formattedPounds = pounds.toLocaleString('en-GB', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return `${isNeg ? '-' : ''}${symbol}${formattedPounds}`;
}

/**
 * Calculates responsive tick density to avoid X-axis label collision.
 */
export function getVisibleTickIndices(totalPoints: number, containerWidth: number, minSpacing = 68): Set<number> {
  const visible = new Set<number>();
  if (totalPoints <= 0) return visible;
  if (totalPoints === 1) {
    visible.add(0);
    return visible;
  }

  const maxTicks = Math.max(2, Math.floor(containerWidth / minSpacing));
  if (totalPoints <= maxTicks) {
    for (let i = 0; i < totalPoints; i++) visible.add(i);
    return visible;
  }

  const stride = Math.ceil(totalPoints / maxTicks);
  for (let i = 0; i < totalPoints; i += stride) {
    visible.add(i);
  }
  // Ensure the very last point is always included for boundary clarity
  visible.add(totalPoints - 1);
  return visible;
}

/**
 * Computes clamped coordinates for tooltips so they remain fully within view.
 */
export function computeTooltipCoords(
  targetX: number,
  targetY: number,
  containerWidth: number,
  containerHeight: number,
  tooltipWidth = 210,
  tooltipHeight = 120
): { left: number; top: number; placeBelow: boolean } {
  // Horizontal clamp
  let left = targetX - tooltipWidth / 2;
  if (left < 10) left = 10;
  if (left + tooltipWidth > containerWidth - 10) {
    left = Math.max(10, containerWidth - tooltipWidth - 10);
  }

  // Vertical placement: default above target, flip below if too close to ceiling
  let top = targetY - tooltipHeight - 12;
  let placeBelow = false;
  if (top < 8) {
    top = targetY + 14;
    placeBelow = true;
  }
  if (top + tooltipHeight > containerHeight - 8) {
    top = Math.max(8, containerHeight - tooltipHeight - 8);
  }

  return { left, top, placeBelow };
}

/**
 * Builds continuous SVG path string.
 */
export function buildSvgPath(points: Array<{ x: number; y: number }>): string {
  if (!points || points.length === 0) return '';
  return points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ');
}

export interface SegmentedPoint {
  x: number;
  y: number;
  isAvailable?: boolean;
  isDashed?: boolean;
}

export interface SegmentedPathsResult {
  solidPaths: string[];
  dashedPaths: string[];
}

/**
 * Builds segmented SVG paths for charts that mix solid, dashed, and unavailable sections.
 * Never connects across unavailable points.
 */
export function buildSegmentedPaths(points: SegmentedPoint[]): SegmentedPathsResult {
  const solidPaths: string[] = [];
  const dashedPaths: string[] = [];

  if (!points || points.length === 0) {
    return { solidPaths, dashedPaths };
  }

  let currentSegment: { isDashed: boolean; points: Array<{ x: number; y: number }> } | null = null;

  for (let i = 0; i < points.length; i++) {
    const pt = points[i];
    const isAvail = pt.isAvailable !== false;

    if (!isAvail) {
      if (currentSegment && currentSegment.points.length > 1) {
        const path = buildSvgPath(currentSegment.points);
        if (currentSegment.isDashed) dashedPaths.push(path);
        else solidPaths.push(path);
      }
      currentSegment = null;
      continue;
    }

    const isDashed = !!pt.isDashed;

    if (!currentSegment) {
      currentSegment = { isDashed, points: [{ x: pt.x, y: pt.y }] };
    } else if (currentSegment.isDashed === isDashed) {
      currentSegment.points.push({ x: pt.x, y: pt.y });
    } else {
      // Transition from solid to dashed or vice-versa:
      // Include the boundary point in both so the visual line remains connected
      currentSegment.points.push({ x: pt.x, y: pt.y });
      const path = buildSvgPath(currentSegment.points);
      if (currentSegment.isDashed) dashedPaths.push(path);
      else solidPaths.push(path);

      currentSegment = { isDashed, points: [{ x: pt.x, y: pt.y }] };
    }
  }

  if (currentSegment && currentSegment.points.length > 1) {
    const path = buildSvgPath(currentSegment.points);
    if (currentSegment.isDashed) dashedPaths.push(path);
    else solidPaths.push(path);
  }

  return { solidPaths, dashedPaths };
}

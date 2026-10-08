import test from 'node:test';
import assert from 'node:assert/strict';
import { getRiskTier, RISK_TIERS } from '../src/utils/riskColor.js';

test('RiskGauge color mapping - Normal tier (0 to 39)', () => {
  const t0 = getRiskTier(0);
  assert.equal(t0.tier, 'NORMAL');
  assert.equal(t0.hex, '#10B981');
  assert.equal(t0.label, 'Normal');

  const t25 = getRiskTier(25.5);
  assert.equal(t25.tier, 'NORMAL');

  const t39 = getRiskTier(39.9);
  assert.equal(t39.tier, 'NORMAL');
});

test('RiskGauge color mapping - Watch tier (40 to 59)', () => {
  const t40 = getRiskTier(40.0);
  assert.equal(t40.tier, 'WATCH');
  assert.equal(t40.hex, '#F59E0B');
  assert.equal(t40.label, 'Watch');

  const t50 = getRiskTier(50.0);
  assert.equal(t50.tier, 'WATCH');

  const t59 = getRiskTier(59.9);
  assert.equal(t59.tier, 'WATCH');
});

test('RiskGauge color mapping - Warning tier (60 to 79)', () => {
  const t60 = getRiskTier(60.0);
  assert.equal(t60.tier, 'WARNING');
  assert.equal(t60.hex, '#F97316');
  assert.equal(t60.label, 'Warning');

  const t75 = getRiskTier(75.2);
  assert.equal(t75.tier, 'WARNING');

  const t79 = getRiskTier(79.9);
  assert.equal(t79.tier, 'WARNING');
});

test('RiskGauge color mapping - Critical tier (80 to 100+)', () => {
  const t80 = getRiskTier(80.0);
  assert.equal(t80.tier, 'CRITICAL');
  assert.equal(t80.hex, '#EF4444');
  assert.equal(t80.label, 'Critical');

  const t95 = getRiskTier(95.0);
  assert.equal(t95.tier, 'CRITICAL');

  const t100 = getRiskTier(100.0);
  assert.equal(t100.tier, 'CRITICAL');
});

test('RiskGauge color mapping - Custom threshold override', () => {
  // Custom thresholds: Warning at 50, Critical at 70
  const custom = { warning: 50.0, critical: 70.0 };

  assert.equal(getRiskTier(45, custom).tier, 'WATCH');
  assert.equal(getRiskTier(55, custom).tier, 'WARNING');
  assert.equal(getRiskTier(72, custom).tier, 'CRITICAL');
});

test('RiskGauge color mapping - String status inputs and fallbacks', () => {
  assert.equal(getRiskTier('Normal').tier, 'NORMAL');
  assert.equal(getRiskTier('watch').tier, 'WATCH');
  assert.equal(getRiskTier('Warning').tier, 'WARNING');
  assert.equal(getRiskTier('Critical').tier, 'CRITICAL');

  // Edge cases: null, undefined, NaN
  assert.equal(getRiskTier(null).tier, 'NORMAL');
  assert.equal(getRiskTier(undefined).tier, 'NORMAL');
  assert.equal(getRiskTier('unknown').tier, 'NORMAL');
});

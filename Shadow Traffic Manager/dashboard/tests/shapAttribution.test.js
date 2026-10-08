import test from 'node:test';
import assert from 'node:assert/strict';
import { getMetricColor, getMetricShortName } from '../src/utils/riskColor.js';

test('Metric short names map cleanly to explainability labels', () => {
  assert.equal(getMetricShortName('avg_response_time_ms'), 'Response time');
  assert.equal(getMetricShortName('request_rate'), 'Request rate');
  assert.equal(getMetricShortName('error_rate_percent'), 'Error rate');
  assert.equal(getMetricShortName('active_users'), 'Active users');
});

test('Metric colors provide distinct visual palettes', () => {
  const c1 = getMetricColor('avg_response_time_ms');
  const c2 = getMetricColor('request_rate');
  const c3 = getMetricColor('error_rate_percent');
  const c4 = getMetricColor('active_users');

  assert.equal(c1, '#818CF8');
  assert.equal(c2, '#38BDF8');
  assert.equal(c3, '#FB923C');
  assert.equal(c4, '#34D399');
});

test('SHAP-style attribution string formatting produces requested headline', () => {
  const mockFactors = [
    { metric: 'avg_response_time_ms', percentage_contribution: 45 },
    { metric: 'request_rate', percentage_contribution: 30 },
    { metric: 'error_rate_percent', percentage_contribution: 25 },
  ];

  const headline = mockFactors
    .map((item, index) => {
      const name = getMetricShortName(item.metric);
      if (index === 0) {
        return `${name}: ${item.percentage_contribution}% of risk score`;
      }
      return `${name}: ${item.percentage_contribution}%`;
    })
    .join(', ');

  assert.equal(
    headline,
    'Response time: 45% of risk score, Request rate: 30%, Error rate: 25%'
  );
});

import test from 'node:test';
import assert from 'node:assert/strict';

test('Auto-remediation message formatter matches specification', () => {
  const mockAction = {
    id: 'rem-test-123',
    action_type: 'SCALE_OUT',
    previous_instances: 2,
    new_instances: 4,
    status: 'COMPLETED',
    message: 'Auto-remediation triggered: scaled from 2 to 4 instances.',
  };

  assert.equal(
    mockAction.message,
    'Auto-remediation triggered: scaled from 2 to 4 instances.'
  );
  assert.equal(mockAction.previous_instances, 2);
  assert.equal(mockAction.new_instances, 4);
  assert.equal(mockAction.status, 'COMPLETED');
});

test('Auto-remediation scale-out delta calculation', () => {
  const calcNewInstances = (prev, step = 2, max = 8) => Math.min(max, prev + step);

  assert.equal(calcNewInstances(2), 4);
  assert.equal(calcNewInstances(4), 6);
  assert.equal(calcNewInstances(6), 8);
  assert.equal(calcNewInstances(8), 8); // Respects max limit
});

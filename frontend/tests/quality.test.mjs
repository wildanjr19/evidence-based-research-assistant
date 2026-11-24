import assert from 'node:assert/strict';
import test from 'node:test';
import { evaluateClaims } from '../src/quality.ts';

const claims = Array.from({ length: 5 }, (_, i) => ({ claim_id: `c${i}` }));

test('two cards run concurrently and publish in completion order', async () => {
  const pending = new Map();
  const started = [], completed = [];
  let active = 0, maximum = 0;
  const run = evaluateClaims(claims, async (claim) => {
    started.push(claim.claim_id);
    maximum = Math.max(maximum, ++active);
    await new Promise((resolve) => pending.set(claim.claim_id, resolve));
    completed.push(claim.claim_id);
    --active;
  }, () => true);
  assert.deepEqual(started, ['c0', 'c1']);
  for (const id of ['c1', 'c2', 'c3', 'c4', 'c0']) {
    pending.get(id)();
    await new Promise((resolve) => setImmediate(resolve));
  }
  await run;
  assert.equal(maximum, 2);
  assert.deepEqual(completed, ['c1', 'c2', 'c3', 'c4', 'c0']);
  assert.equal(new Set(started).size, claims.length);
});

test('changing the answer prevents queued cards from starting', async () => {
  let current = true;
  const started = [], pending = [];
  const run = evaluateClaims(claims, async (claim) => {
    started.push(claim.claim_id);
    await new Promise((resolve) => pending.push(resolve));
  }, () => current);
  current = false;
  pending.forEach((resolve) => resolve());
  await run;
  assert.deepEqual(started, ['c0', 'c1']);
});

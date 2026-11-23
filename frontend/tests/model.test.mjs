import assert from 'node:assert/strict';
import test from 'node:test';
import { licenseLabel, number, safeSource, score, supportLabel, tokenSummary } from '../src/model.ts';

test('numbers follow Indonesian notation, including zero and negative relevancy', () => {
  assert.equal(number.format(2514), '2.514');
  assert.equal(score.format(0), '0,000');
  assert.equal(score.format(-0.125), '-0,125');
});

test('source links permit only public HTTPS navigation without credentials', () => {
  for (const url of [null, '/local.pdf', 'file:///data/paper.pdf', 'javascript:alert(1)', 'https://user:password@example.com/']) {
    assert.equal(safeSource(url), undefined);
  }
  assert.equal(safeSource('https://example.com/paper'), 'https://example.com/paper');
  assert.match(licenseLabel('LicenseRef-UserProvided-Unverified'), /Belum diverifikasi/);
});

test('MiniCheck requires every citation and ignores results for other claims or verifiers', () => {
  const claim = { claim_id: 'c1', citations: ['a', 'b'], unsupported: false };
  const result = (chunk_id, label, verifier = 'minicheck', claim_id = 'c1') => ({ chunk_id, label, verifier, claim_id });
  assert.equal(supportLabel(claim, [result('a', 'supported'), result('b', 'supported')]), 'Didukung MiniCheck');
  assert.equal(supportLabel(claim, [result('a', 'supported'), result('b', 'supported', 'llm_judge')]), 'Belum diverifikasi');
  assert.equal(supportLabel(claim, [result('a', 'supported'), result('b', 'supported', 'minicheck', 'c2')]), 'Belum diverifikasi');
  assert.equal(supportLabel(claim, [result('a', 'partially_supported')]), 'Perlu diperiksa');
  assert.equal(supportLabel({ ...claim, unsupported: true }, []), 'Tidak ada bukti');
});

test('usage totals exclude unknown and historical demo usage', () => {
  const usage = { input_tokens: 250, output_tokens: 30, backend_calls: 1, cache_hits: 2, unknown_usage_attempts: 0 };
  const answer = { claims: [{ claim_id: 'c1' }, { claim_id: 'c2' }] };
  const summary = tokenSummary(answer, { c1: { usage } });
  assert.equal(summary.rows[0].input, 'Belum tersedia');
  assert.deepEqual(summary.total, { input_tokens: 250, output_tokens: 30, backend_calls: 1, cache_hits: 2 });
  assert.equal(summary.incomplete, true);
  assert.equal(tokenSummary({ claims: [], usage }, {}).incomplete, false);
});

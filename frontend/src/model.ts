import type { Answer, Claim, Quality, Usage, Verification } from './types.ts';

export const number = new Intl.NumberFormat('id-ID');
export const score = new Intl.NumberFormat('id-ID', {
  minimumFractionDigits: 3,
  maximumFractionDigits: 3,
});

export function licenseLabel(value: string): string {
  return value === 'LicenseRef-UserProvided-Unverified'
    ? 'Belum diverifikasi (koleksi PDF lokal)'
    : value;
}

export function safeSource(value: string | null): string | undefined {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && !url.username && !url.password ? value : undefined;
  } catch {
    return undefined;
  }
}

export function supportLabel(claim: Claim, records: Verification[]): string {
  if (claim.unsupported || !claim.citations.length) return 'Tidak ada bukti';
  const labels = new Map(records.filter((item) => item.claim_id === claim.claim_id && item.verifier === 'minicheck')
    .map((item) => [item.chunk_id, item.label]));
  const values = claim.citations.map((key) => labels.get(key));
  if (values.every((label) => label === 'supported')) return 'Didukung MiniCheck';
  if (values.some((label) => label === 'not_supported' || label === 'partially_supported')) return 'Perlu diperiksa';
  return 'Belum diverifikasi';
}

export function tokenSummary(answer: Answer, quality: Record<string, Quality>) {
  const stages: [string, (Usage | undefined)[]][] = [
    ['Generator', [answer.usage]],
    ['Evaluasi RAGAS', answer.claims.map((claim) => quality[claim.claim_id]?.usage)],
  ];
  const total = { input_tokens: 0, output_tokens: 0, backend_calls: 0, cache_hits: 0 };
  let incomplete = false;
  const rows = stages.map(([stage, usages]) => {
    const known = usages.filter((usage): usage is Usage => usage !== undefined);
    incomplete ||= known.length !== usages.length || known.some((usage) => usage.unknown_usage_attempts > 0);
    const input = known.reduce((sum, usage) => sum + usage.input_tokens, 0);
    const output = known.reduce((sum, usage) => sum + usage.output_tokens, 0);
    total.input_tokens += input;
    total.output_tokens += output;
    total.backend_calls += known.reduce((sum, usage) => sum + usage.backend_calls, 0);
    total.cache_hits += known.reduce((sum, usage) => sum + usage.cache_hits, 0);
    return { stage, input: known.length || !usages.length ? number.format(input) : 'Belum tersedia',
      output: known.length || !usages.length ? number.format(output) : 'Belum tersedia' };
  });
  rows.push({ stage: 'Total tercatat', input: number.format(total.input_tokens), output: number.format(total.output_tokens) });
  return { rows, total, incomplete };
}

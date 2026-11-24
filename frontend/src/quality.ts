import type { Claim } from './types.ts';

export async function evaluateClaims(
  claims: Claim[],
  evaluate: (claim: Claim) => Promise<void>,
  isCurrent: () => boolean,
): Promise<void> {
  let next = 0;
  await Promise.all(Array.from({ length: 2 }, async () => {
    while (isCurrent()) {
      const claim = claims[next++];
      if (!claim) return;
      await evaluate(claim);
    }
  }));
}

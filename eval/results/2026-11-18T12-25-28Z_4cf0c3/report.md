# Human pilot comparison

Run: `2026-11-18T12:25:28Z_4cf0c3`. Source: `2026-11-18T11:50:46Z_ad072b`.

The human annotator corrected P to S and explicitly confirmed supported for all twelve pairs. Original review material, feedback, predictions, and corpus remain unchanged. Labels are retained as a human pilot pending adjudication, without promotion to final gold.

- Jev: 4/12 matching human labels (33.3%), coverage 12/12, unweighted kappa 0.
- MiniCheck: 3/10 matching human labels (30.0%), coverage 10/12, unweighted kappa 0. Two pairs remain unverified due to the existing token limit.

All human labels are supported. Kappa equals zero because observed agreement equals chance under this single-class human distribution; this is not evidence of either model's general quality. There is one annotator, one paper, five grouped chunks, and twelve draft-reference pairs. Aggregate model results had previously been disclosed, so the review was not fully blinded.

Eight Jev disagreements include all seven abstract pairs and one partial prediction. Review each disputed claim against its specific chunk. Keep the human label unless the annotator explicitly revises it; model agreement does not establish ground truth.

Manual labels SHA-256: `a1fa7aa78964e1278728339b559c16307f3f8ebdb584caea01ccf5f6ebae6dc0`. Source config SHA-256: `eb71dccb46aed5ca25665a5da31483532e15fce42c9f6a26b2588b57faf2aad4`. Seed: 42.

No paid API calls, model inference, or source database updates were performed. Resources in metrics.json describe this local scoring process only.

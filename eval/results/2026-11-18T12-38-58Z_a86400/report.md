# Revised human pilot comparison

Run: `2026-11-18T12:38:58Z_a86400`. Source predictions remain unchanged.

The user completed eight individual reviews, changing seven labels. The twelve current labels are five supported, three partially_supported, and four not_supported. Original labels and the completed worksheet are preserved. No human labels were inferred or corrected by the agent.

- Jev matches 8/12 (66.7%), coverage 12/12, unweighted kappa 0.483871.
- MiniCheck matches 7/10 (70.0%), coverage 10/12, unweighted kappa 0.523810.

These are provisional agreement statistics against the labels as entered. Three partial rationales still discuss length or needing more context rather than identifying a supported subset of the claim. Clarify row-08, row-02, and row-18 against their exact chunk; do not change labels to follow model predictions. Chunk position or lack of empirical results alone does not determine support.

Review selected only model disagreements after aggregate results were disclosed. The increase in agreement is not independent evidence of model quality. One annotator, one paper, twelve draft-reference pairs, and two MiniCheck token-limit rejections remain limitations. This pilot does not close M6 and is not final gold.

Manual labels SHA-256: `a5a9a44a23c9b634be69e09d4dcc10a8746fea3e1e0807933a3145dada5f12ab`. Source config SHA-256: `eb71dccb46aed5ca25665a5da31483532e15fce42c9f6a26b2588b57faf2aad4`. Seed: 42.

No paid API calls, model inference, or corpus updates were performed. Resource counters in metrics.json cover this local scoring process only.

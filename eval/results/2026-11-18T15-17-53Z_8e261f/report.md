# Human pilot review v3

Run: `2026-11-18T15:17:53Z_8e261f`. Seed: 42.

The user entered N/N/N/P for row-08, row-02, row-18, and row-35. Four revised labels and original rationales were saved in human-labels-v3.jsonl. Blank worksheet annotator fields retain the prior chat-user identity because the user reported completing the review. Row-35 explicitly adopts the visible AI explanation. The twelve current labels are four supported, one partially_supported, and seven not_supported. Prior labels, model predictions, and the completed worksheet are preserved.

| Model | Matches | Coverage | Unweighted kappa |
|---|---|---|---|
| jev | 12/12 | 12/12 | 1.000000 |
| minicheck | 10/10 | 10/12 | 1.000000 |

This is agreement on a nonblind pilot after AI suggestions were shown. It is not independent validation of model accuracy. Two MiniCheck inputs remain unverified due to the token limit. Four revisions do not add new unique pairs; the forty remaining annotation pairs are still unlabeled. M6 remains open.

Manual labels SHA-256: `133c5d2145151dd24b1fc0b2e2f7f3dd2acf0bcc7fd3fd026fe4137eb3c88c1b`. Source config SHA-256: `eb71dccb46aed5ca25665a5da31483532e15fce42c9f6a26b2588b57faf2aad4`.

No paid API calls, model inference, corpus updates, or final gold promotion occurred. Resource counters cover this local scoring process only.

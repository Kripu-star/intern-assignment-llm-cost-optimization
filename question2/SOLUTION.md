# Question 2 — Solution

## Result

| Ticket | Baseline | Optimized | Target |
|---|---:|---:|---:|
| T-1004 (replace) | 72,972 | 1,257 | ≤ 2,500 |
| T-1003 (escalate) | 72,768 | 1,296 | ≤ 2,500 |

Public tickets T-1001 to T-1004 and the holdout T-1091 all stay under 1,450 points, and `action` / `kb_article` are unchanged on every one.

## Per-call breakdown

**T-1004: physical fulfillment path (REPLACE)**

| Node | Baseline in / out | Baseline points | Optimized in / out | Optimized points |
|---|---|---:|---|---:|
| triage | 8,439 / 480 | 32,517 | code, no call | 0 |
| retrieve | 590 / 36 | 2,310 | code, no call | 0 |
| compose | 1,150 / 494 | 10,860 | 239 / 36 | 1,257 |
| audit | 6,690 / 481 | 27,285 | code, no call | 0 |
| **Total** | | **72,972** | | **1,257** |

**T-1003: escalation path (ESCALATE_TIER2)**

| Node | Baseline in / out | Baseline points | Optimized in / out | Optimized points |
|---|---|---:|---|---:|
| triage | 8,437 / 480 | 32,511 | code, no call | 0 |
| retrieve | 590 / 39 | 2,355 | code, no call | 0 |
| compose | 1,151 / 481 | 10,668 | 237 / 39 | 1,296 |
| audit | 6,678 / 480 | 27,234 | code, no call | 0 |
| **Total** | | **72,768** | | **1,296** |

No call uses cached input. Reproduce the optimized numbers with `python question2/run.py`.

## What was wrong

- The triage and audit calls were sent about 120k and 80k characters of "help center", which is mostly filler. Only five real articles exist.
- The triage and audit prompts told the model to restate and double-check, which produces about 480 output tokens per call. Output costs 15 points per token.
- Triage output was passed forward again, twice in the compose prompt.
- The retrieve step asked a model to print articles that already exist as files.
- A fresh `uuid` sat at the top of the triage prompt.

## What I changed

The four nodes are still there, but only compose calls the model.

1. **Triage (code).** Takes the customer's messages and the order facts, drops `order_id` and `sku`, and builds a search query from the thread, the product type and the order flags (damaged, custom, license shown, opened).
2. **Retrieve (code).** Scores the real articles by word overlap with the query and keeps the top 3. The filler is never loaded or sent.
3. **Compose (one model call).** Gets the 3 articles, the thread and the compact order snapshot. It is asked for JSON only, with no reasoning request.
4. **Audit (code).** Parses the reply and checks that the action is one of the four allowed values and that the cited article exists. Anything malformed or invented becomes `ESCALATE_TIER2`.

The audit still checks the output, but with plain code, which costs nothing and is deterministic.

## Tests

- Cost is at most 2,500 points on every ticket.
- The simulator ignores article text, so a separate test checks that the correct article is in the retrieved top 3 for each ticket, including the holdout.
- A test feeds the audit bad output (not JSON, unknown action, made-up article) and expects escalation.
- The old test asserting the baseline was expensive was removed, since it checked the behavior I replaced.

## Limitations

- Retrieval is word overlap. It works for 5 articles, but a real help center of hundreds of articles would need embeddings or a proper search index, with the top-k tuned on labelled tickets.
- If retrieval misses the right article, the model cannot cite it. The audit would then escalate rather than answer wrongly, which is the safer failure.
- The model here is a simulator that does not read the prompt text, so I can only prove the prompts are small and the retrieval is correct, not the model's accuracy. With a real model I would measure accuracy on a labelled set before and after.
- Caching was not used. The prompt is about 240 tokens, well under the 1,024-token minimum.

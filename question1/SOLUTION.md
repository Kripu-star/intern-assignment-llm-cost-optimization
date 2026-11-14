# Question 1 — Solution

## Result

| | Points / ticket (avg) | Total (4 public tickets) |
|---|---:|---:|
| Baseline | ~8,880 | 35,529 |
| Optimized | **~1,370** | **5,472** |
| Target | ≤ 3,000 | — |

Graded fields (`action`, `kb_article`) are unchanged on all public tickets **and** the holdout `T-1091`.

## Per-call breakdown — T-1001

| | Input tokens | Cached | Output tokens | Points |
|---|---:|---:|---:|---:|
| Baseline | 529 | 0 | 487 | 8,892 (1,587 in + 7,305 out) |
| Optimized | 258 | 0 | 46 | 1,464 (774 in + 690 out) |

Reproduce with `python question1/run.py`.

## What I changed and why

1. **Removed verbose-reasoning instructions** ("Think step by step… write full reasoning, quote any article"). Output costs 15 points per token, 5× the input price, and those instructions produced about 490 output tokens. Only `action` and `kb_article` are consumed downstream, so free-text reasoning is pure cost. **This was ~82% of the baseline bill.**
2. **Replaced full help-center text with one-line routing rules.** Each article becomes one rule: condition → action → article id. The model needs the decision logic and the id to cite, not the prose.
3. **Removed the redundant few-shot block.** The rules already cover these four cases, so the examples repeated them.
4. **Removed the `Run id {uuid}` header.** It added tokens, and because it changed on every call it would have defeated prefix caching.
5. **Compacted the order snapshot.** I switched to `separators=(",", ":")` instead of `indent=2` and dropped routing-irrelevant identifiers (`order_id`, `sku`).
6. **Kept only customer messages from the thread**, since the agent's own filler lines carry no information.

## Things I chose not to do

- **No hardcoding by ticket id and no rules engine replacing the LLM call.** The point is a cheaper prompt, not bypassing the model. The holdout ticket `T-1091` (a subscription case not in the examples) still routes correctly, which shows the rules generalise.
- **Prompt caching (`cached_prefix`) is not used.** It only applies to an identical prefix of at least 1,024 tokens, and the optimized system prompt is about 200 tokens. Padding it to 1,024 tokens would cost 1,024 × 0.3 ≈ 307 points, compared with about 600 points uncached today. That is a saving of roughly 300 points on every call after the first, but only at high volume. In production with a larger, stable system prompt, I would put all static content first and pass it as `cached_prefix`.

## Test change

`test_baseline_cost_is_high` asserted the *old* behaviour (cost > 15,000) and fails by design after optimizing. I replaced it with `test_cost_per_ticket_under_target`, which asserts at most 3,000 points for each public ticket and for the holdout.

## Production considerations

- Short `customer_reply` is kept so the product still has a message to send.
- With a real model, I would track routing accuracy on a labelled eval set when tightening prompts. I would also add a validation step: an unknown action or article falls back to `ESCALATE_TIER2`.

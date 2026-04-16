# backend/tests/evals — Agent Behavior Evals

This directory is **physically separated** from `backend/tests/` for a reason:

| Directory | Tests what | Question it asks | Pass mode |
|-----------|-----------|------------------|-----------|
| `tests/` (272 tests) | Code mechanism | "Does the code execute as written?" | Deterministic assertion |
| `tests/evals/` (new) | Agent behavior | "Does the agent do what the user needs?" | Behavior assertion + measurement |

## Why the separation matters

If we mix SDK mechanism tests (e.g., "middleware.before_node was called") with model
capability evals (e.g., "important information survived compaction"), the signal gets
diluted. SDK tests pass for any implementation; evals expose real user-facing failures.

Ref: `~/.claude/rules/agent-eval-curation.md` (Taxonomy rule #2)

## Running evals

```bash
# Run all evals
uv run pytest tests/evals/ -v

# Run by category (taxonomy filter)
uv run pytest tests/evals/ -v -m "eval_category('retrieval')"

# Correctness vs efficiency separation
uv run pytest tests/evals/ -v -m correctness
uv run pytest tests/evals/ -v -m efficiency
```

## Eval files

| File | What it measures | Categories |
|------|------------------|------------|
| `test_compaction_evals.py` | `ContextCompactionMiddleware` behavior when compressing long conversations | `retrieval`, `invariance`, `tool_use`, `efficiency` |
| `test_router_evals.py` | `router_node` classification accuracy across edge-case queries | `routing` |

## Taxonomy

Tag by **what the eval measures**, not where the scenario came from. This is from the
eval-curation rule: SWE-bench and BFCL both sit in "external benchmarks", but they
test retrieval vs tool_use — tagging by origin hides the signal.

Good tags:
- `retrieval` — can the agent recall earlier facts?
- `invariance` — are specific fields preserved under transformation?
- `tool_use` — do tool_call/tool_response pairs stay intact?
- `efficiency` — measurement of latency/cost/token budget with target bounds
- `routing` — 4-way classification accuracy on real/edge queries

## Anti-patterns to avoid

1. **Adding evals for coverage's sake** — "more evals ≠ better agents"; each eval
   shifts agent behavior. Only add evals that measure a behavior you care about.
2. **Testing mechanism in evals** — `assert middleware.was_called()` belongs in `tests/`,
   not here. Evals ask user-level behavior questions.
3. **Exact-match for semantic outputs** — for LLM summaries, use LLM-as-judge or
   structured facts with defined anchors, not `assert output == "expected string"`.

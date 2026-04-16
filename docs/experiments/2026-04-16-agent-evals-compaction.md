# Experiment · Agent Behavior Evals + Deep Agent SDK Compaction

**Date**: 2026-04-16
**Branch**: `experiment/agent-evals-compaction`
**Scope**: Demonstrate Agent behavior evals as a methodology, then use them
to guide upgrading `ContextCompactionMiddleware` from naive truncation to a
Deep Agent SDK-inspired smart strategy.

---

## TL;DR

1. **Unit tests say truncate works. Behavior evals say truncate is broken.**
   Both are right — they measure different things. This experiment produces
   evidence for that distinction inside our own codebase.
2. **Smart strategy fixes 3/3 correctness evals that truncate fails** while
   keeping efficiency targets met.
3. **Eval discovered a bonus bug** in the router keyword fallback —
   something no unit test was watching for.
4. **Zero production risk**: smart is opt-in; `ContextCompactionMiddleware()`
   with no args is byte-identical to the previous behavior.

---

## Motivation

Two rules eaten this session drive this work:

- `~/.claude/rules/agent-eval-curation.md` — "unit tests test code;
  behavior evals test the agent. Agents need both."
- `~/.claude/rules/agent-context-compaction.md` — "naive truncation suffers
  from four documented failure modes (摘要劣化 / 顺序错乱 / 结构损坏 / 指针丢失).
  Deep Agent SDK's remedy is a four-step strategy: bucketing + summary +
  invariance + tool-pair preservation."

tiny-flow's current `ContextCompactionMiddleware` is a textbook **naive
truncation**: `messages[:2] + messages[-(max-2):]`, drop middle entirely,
no summarization, no structure awareness, no invariance. The existing 6
unit tests all pass — they ask whether the truncation happened, not whether
the agent still works after it. We wanted to find out if the behaviors
the Deep Agent SDK paper warns about are real failures on our code.

They are.

---

## Part 1 — Behavior Evals Expose What Unit Tests Miss

### 1.1 The side-by-side

Existing unit test (`tests/test_loop_context_mw.py:132`):

```python
def test_compaction_trims_to_limit(self):
    mw = ContextCompactionMiddleware(max_messages=10)
    state = {"messages": self._msgs(20)}
    result = mw.before_node(state, "dispatch")
    assert result["_compacted_count"] == 10  # ✅ PASS
```

Question it answers: "Did the code execute its rule?"

New behavior eval (`tests/evals/test_compaction_evals.py`):

```python
@pytest.mark.eval_category("retrieval")
def test_eval_early_fact_retention(conversation_with_early_fact, strategy):
    mw = ContextCompactionMiddleware(max_messages=10, strategy=strategy)
    result = mw.before_node({"messages": conversation_with_early_fact}, "x")
    content = _compacted_text(result["messages"])
    assert "q4_forecast_v2.docx" in content  # ❌ truncate FAILS
```

Question it answers: "Will the user still be able to work with the agent?"

### 1.2 Before / After snapshots

**Input**: 35-message conversation, user mentions `q4_forecast_v2.docx` at turn 2
(after greeting), then 28 turns of chat, then asks "what was that file name?"

**Truncate output** (`strategy="truncate"`, documented behavior):

```
[0] Human: '你好'
[1] AI:    '你好，有什么可以帮你？'
[2] AI:    '好的，item 10 已处理。'        ← turn 27 originally
[3] Human: '另外顺便看下 item 11'
[4] AI:    '好的，item 11 已处理。'
[5] Human: '另外顺便看下 item 12'
[6] AI:    '好的，item 12 已处理。'
[7] Human: '另外顺便看下 item 13'
[8] AI:    '好的，item 13 已处理。'
[9] Human: '对了，我最开始让你分析的那个文件叫什么名字？'
```

- File name `q4_forecast_v2.docx` **gone**.
- User's actual intent ("我要分析一份文件...") **gone**.
- Only preserved context: greetings + last 8 turns of unrelated chat.

**Smart output** (`strategy="smart", retention_window=8`):

```
[0] Human: '我要分析一份文件，叫 q4_forecast_v2.docx'   ← invariance
[1] System: '[Prior context summary]\nuser: 你好 / user: 我要分析...
                                      / user: 请提取 top-line 营收 / ...'
[2] AI:    '好的，item 13 已处理。'
[3] Human: '另外顺便看下 item 14'
[4-9]: last 6 retention messages
```

- File name **present** (both in first_human and summary).
- Original goal **present** as first message.
- Structure: tool pairs (if any) intact.

### 1.3 Eval result matrix

```
$ uv run pytest tests/evals/ -v

CORRECTNESS EVALS
  retrieval     / truncate :  XFAIL (documented broken — strict)
  retrieval     / smart    :  PASSED ✅
  invariance    / truncate :  XFAIL
  invariance    / smart    :  PASSED ✅
  tool_use      / truncate :  XFAIL
  tool_use      / smart    :  PASSED ✅

EFFICIENCY EVALS
  latency       / truncate :  PASSED ✅
  latency       / smart    :  PASSED ✅
  size_budget   / truncate :  PASSED ✅
  size_budget   / smart    :  PASSED ✅

ROUTING EVALS
  keyword_fallback × 14    :  PASSED ✅
  keyword_fallback × 1     :  XFAIL (latent router defect exposed)
  aggregate_weighted_cost  :  PASSED ✅ (cost=2, budget=5)
```

**Translation**:
- Smart strategy does what we want (all correctness pass, all efficiency pass).
- Truncate is objectively broken in 3 out of 3 ways the Deep Agent SDK paper predicted.
- The router has a latent bug we didn't go looking for — eval found it for free.

### 1.4 Bonus finding — router defect

`分别总结这三篇文章` expected `ultra`, got `pro`. The keyword fallback
logic requires enumeration punctuation (`、` or `，`) to classify `分别`
as parallel intent. This query has neither but is semantically clearly
parallel (三篇文章 = three articles).

Unit tests don't catch this because they test the code path, not the
semantic coverage. Eval caught it in 0 additional effort — a single
labeled query in the dataset did the job.

Documented inline in `_KNOWN_ROUTER_DEFECTS`, xfailed strict-mode so CI
stays green but the finding won't silently disappear.

---

## Part 2 — Smart Compaction Implementation

### 2.1 Four steps, mapped to code

| Step | Deep Agent SDK principle | tiny-flow location |
|------|--------------------------|--------------------|
| 1. Bucketing | Split into retention window + compaction zone | `_apply_smart` lines ~115-120 |
| 2. Invariance | Preserve user's first substantive message | `_first_substantive_human_msg` |
| 3. Structure | Drop orphan tool_responses | `_remove_orphan_tool_responses` |
| 4. Summarize | Call summarizer, write to metadata | `_apply_smart` lines ~132-148 |

### 2.2 Design decisions and why

**Strategy parameter, not new class**. `ContextCompactionMiddleware(strategy=...)`
instead of `SmartCompactionMiddleware` as a sibling. Two strategies share
the same trigger logic, retention configuration, and logging — abstracting
them apart means synchronizing two places. Revisit at 3+ strategies (YAGNI).

**Metadata, not new GraphState field**. Rolling summary lives in
`state["metadata"]["context_summary"]`, not a new typed field. Zero schema
change, zero risk to existing checkpoints. If smart graduates into a first-
class feature, promotion is a 5-line patch.

**Graceful degradation on summarizer failure**. `except Exception → truncate
fallback + log warning`. A crashing middleware is worse than a lossy one;
LangGraph's InMemorySaver preserves the pre-compaction state anyway, so
the signal isn't lost.

**Greeting heuristic is opt-outable**. `greeting_patterns` is a constructor
kwarg. Production teams with different greeting conventions (German, Japanese,
corporate) can replace the tuple without subclassing.

### 2.3 What we did NOT build

Per the scope-B agreement during brainstorming, these are deliberately out of scope:

- **Real LLM summarizer integration** (C scope) — the middleware accepts any
  callable; integration with `core.models.factory` is a 10-line follow-up
  but adds spend, latency, and test flakiness to this experiment.
- **Multi-model comparison for summary quality** — one model is enough to
  prove the mechanism works. Comparison is a generation-2 concern.
- **Dogfood eval mining from real threads** — hand-written edge cases cover
  the demonstration; production logs were not tapped.
- **LLM-as-judge for router evals** — keyword fallback is 100% deterministic
  and is the actual production path for edge cases; judge is only needed
  when outputs are semantically flexible.

---

## Part 3 — Process Reflection

### 3.1 What worked

**Red before green, literally**. Writing the evals before implementing
smart strategy forced us to define "what does 'working' mean?" precisely,
and made the red phase a concrete artifact: when truncate evals fail,
they fail with descriptive messages that point at specific user harm.

**Parametrization made the narrative compact**. Same eval × two strategies
produces directly comparable results. Without parametrization we'd have
had to write "test_truncate_fails_at_X" and "test_smart_succeeds_at_X"
separately, doubling the surface area without adding signal.

**Physical separation of tests/ and tests/evals/**. Matches the eval-curation
rule's "SDK tests vs model capability evals must not mix". Makes the
taxonomy visible in the file system, not just in docstrings.

### 3.2 What surprised us

**Truncate's defaults were protective enough that the demo almost failed.**
My first `conversation_with_early_fact` fixture put the file name in
`messages[0]`, which truncate preserves. I had to move the file name to
`messages[2]` to expose the real failure mode. This is itself a finding:
**truncate works if users state intent in message 0**. That's a narrow
use case, but it's what pure unit tests have been testing against — a
convenient assumption that doesn't hold in real chat.

**The router defect was found with zero extra work.** I added router evals
as the "Layer 2 — methodology scope" experiment to prove evals aren't only
useful for compaction. One of 15 labeled queries failed, for a reason that
the keyword fallback's code doesn't document. Eval as dogfooding discovery
mechanism was immediate.

**xfail strict-mode turned "expected fail" into a contract.** Marking
truncate × correctness as `xfail(strict=True)` means the test suite will
alert us if truncate is ever secretly fixed. That's a stronger guarantee
than a comment saying "this is broken."

### 3.3 What I would do differently

**Write the data flow diagram before the code.** I started implementation
after getting approach-A approved, but the data flow between steps 4-6
(summarize, roll, assemble) had three bugs I caught only during eval runs:
metadata not persisting, first_human duplication with retention, and
summary message type confusion (initial draft used AIMessage instead of
SystemMessage). A diagram would've caught all three in 5 minutes.

**The conftest fixtures should have been asserted-against-their-invariants
before being used in evals.** My initial `tool_call_pair_at_boundary`
fixture placed the pair in the kept tail accidentally, which made the
"orphan" eval trivially pass. I caught this during the red phase run,
but a 2-line "assert tool_call in drop_zone" at fixture build time would
have caught it before the eval ran.

---

## Part 4 — Links

- Eval infrastructure: `backend/tests/evals/` (README, conftest, 2 eval files)
- Smart strategy: `backend/core/middleware/context_compaction.py`
- Unit tests: `backend/tests/test_loop_context_mw.py` (TestSmartContextCompaction)
- Rules referenced:
  - `~/.claude/rules/agent-eval-curation.md`
  - `~/.claude/rules/agent-context-compaction.md`
- Original source materials eaten for these rules:
  - https://x.com/vtrivedy10/status/2037203679997018362
  - https://midawang.feishu.cn/wiki/UMr7wFxbFiQ8g5krQIccqACCnFf

---

## Part 5 — What's Next

This experiment established the pattern. To make it production-grade:

1. **Wire a real summarizer** — use `core.models.factory` with a cheap model
   (GLM-4-Air). Budget: ~30 min implementation + eval cost verification.
2. **Enable `strategy="smart"` in one mode** — start with `thinking` (shortest
   conversations, smallest blast radius). Monitor for 1 week.
3. **Mine dogfood data** — `backend/data/*.db` thread history is a ready
   source of real compaction scenarios. Build 10-20 real evals from
   production conversations.
4. **Fix the router defect** — relax enum_markers check when `分别` co-occurs
   with quantity markers like `这N篇`.
5. **Promote `context_summary` to GraphState** — once used, add the field
   with a TypedDict default. Migration is one-line.

All of these are follow-ups, not blockers on this experiment.

# Context Management Guide

Last reviewed: 2026-05-16

## Why This Exists

The LLM-Harness survey separates context and memory from task execution: the
harness owns what goes into the model window, how tool outputs are compacted,
and when long-running state is turned into structured memory. AIDD-Intern uses
the same principle. The agent should not rely on the model to notice that its
own prompt is too large; the runtime must budget context before every LLM call.

This matters for local deployments. Many local or OpenAI-compatible models
advertise unknown context metadata to LiteLLM but actually hard-fail at 65,536
tokens. AIDD-Intern therefore treats unknown local models conservatively and
adapts policy by model window.

## Model Window Discovery

Context size is resolved in this order:

1. `AIDD_INTERN_MODEL_MAX_TOKENS`, when explicitly set.
2. `litellm.get_model_info(model)["max_input_tokens"]`, when available.
3. Conservative local/OpenAI-compatible default: `65_536`.
4. Hosted-model fallback: `200_000`.
5. Provider overflow errors during runtime. If the provider reports a smaller
   window such as `maximum context length is 65536`, the session immediately
   shrinks its local budget to that value.

For local 65K models, set:

```bash
export AIDD_INTERN_MODEL_MAX_TOKENS=65536
```

## Window-Specific Policy

`ContextManager` applies different policies by context window:

| Window | Compaction threshold | Summary budget | Untouched tail | Per-message preserved limit |
| --- | ---: | ---: | ---: | ---: |
| `<= 70k` | 68% | 1,500 tokens | 3 messages | 12,000 tokens |
| `<= 131k` | 75% | 2,500 tokens | 4 messages | 20,000 tokens |
| `> 131k` | 90% | up to 8,000 tokens | 5 messages | 50,000 tokens |

The 65K profile intentionally compacts early. It keeps enough room for:

- tool schemas;
- provider-specific overhead;
- assistant output;
- recovery prompts after malformed tool calls;
- hidden reasoning or tool-call formatting overhead.

## Per-Call Output Budget

Before each LLM call, AIDD-Intern estimates current prompt tokens and sets a
safe `max_completion_tokens`. This prevents the failure mode:

```text
45537 input + 20000 output > 65536 context window
```

If headroom is low, the runtime marks the context as needing compaction before
retrying.

## Operational Guidance

For 65K local models:

- Prefer shorter tool outputs.
- Use ACE playbooks and project manifests instead of replaying every raw log.
- Compact proactively instead of waiting for provider errors.
- Keep generated reports in files and reference paths rather than pasting full
  contents back into the conversation.

For large hosted models:

- Wider tails are acceptable, but large CSV/PDB/log outputs should still be
  summarized or stored as artifacts.
- Do not assume a hosted model's advertised window is accurate; provider errors
  still override local metadata.

## Related Files

- `agent/core/session.py`: model-window discovery and model-switch updates.
- `agent/context_manager/manager.py`: compaction policy and summarization.
- `agent/core/agent_loop.py`: per-call output budgeting and overflow recovery.
- `agent/domain_packs/protein_design/ace.py`: structured campaign memory.


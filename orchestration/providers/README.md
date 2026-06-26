# Provider seam — operating notes

Provider-agnostic, **local-first** (Decision Log §29; Stage 4 §2). All LLM calls
go through this seam:

```
extract / normalize / judge  ->  registry.resolve(role, settings)  ->  ModelProvider.complete()
```

- `base.py` — the contract (`LLMRequest`, `LLMResponse`, `ModelProvider`).
- `local_openai.py` — **default** backend; any OpenAI-compatible server.
- `anthropic_claude.py` — the hot-swappable **cloud yardstick** (Claude).
- `registry.py` — role → tier → provider routing **+ data-sensitivity routing**
  (private-overlay prompts forced on-device; mirrors Decision Log §13).

Provider-specific levers (Claude prompt caching / adaptive thinking / effort;
local quantization) ride in `LLMRequest.options` or live inside the adapter —
never flattened into the shared contract.

## Choosing a local runtime (open 🅓 — decide via the Stage-4 bake-off)

All three expose the OpenAI Chat Completions API, so the adapter is identical;
only `LOCAL_OPENAI_BASE_URL` changes.

| Runtime | Good for | `LOCAL_OPENAI_BASE_URL` |
|---|---|---|
| **Ollama** | easiest local start; great on Apple Silicon | `http://localhost:11434/v1` |
| **vLLM** | throughput / serving; GPU | `http://localhost:8000/v1` |
| **LM Studio** | GUI, model browsing | `http://localhost:1234/v1` |

The *which-runtime + which-model* call is empirical: run the truthfulness eval
(`evals/truthfulness.py`) across candidates and pick on quality vs. latency vs.
cost — that's the Stage-4 bake-off (§8), not a decision to hardcode here.

## Config

Per-tier provider/model come from the environment (see `.env.example`):
`ADVENTURE_PROVIDER_{MECHANICAL,JUDGMENT}`, `ADVENTURE_MODEL_*`,
`ADVENTURE_LOCAL_MODEL_*`, `LOCAL_OPENAI_BASE_URL`, `ANTHROPIC_API_KEY`.

## Status

Adapters implement `complete()` (mapping + response shaping, unit-tested with
injected fakes). Running them for real needs a reachable local model server
(local) or `ANTHROPIC_API_KEY` (cloud) — both blocked in the build sandbox, so
live calls are the user-machine next step.

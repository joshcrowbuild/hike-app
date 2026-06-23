"""Provider-agnostic model seam (Decision Log §29; Stage 4 §2).

    extract / normalize / judge  ->  registry  ->  ModelProvider adapter

Local/self-hosted is the default; the Anthropic SDK (Claude) is a hot-swappable
yardstick. Routing (role -> tier -> provider, plus data-sensitivity routing) lives
in registry.py; the adapters do dumb completion only.
"""

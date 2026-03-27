# Steward integration — what changes in app.py
# ─────────────────────────────────────────────

# 1. Init once at startup
from steward import Steward
steward = Steward()


# 2. After BrackOracle passes an /order, call:
result = steward.process(
    sober_output = sober_text,
    drunk_output  = drunk_text,
    agent_id      = body["agent_id"],
    session_id    = session_id,
    pint          = body["pint"],
    table_id      = body.get("table_id"),   # None for solo orders
)
# result returns immediately — distil runs in background
# attach result["fragment_id"] to the order response so client can query it


# 3. When building table context for the NEXT round, inject:
context_line = steward.table_context(table_id)
# Returns: 'Overheard at this table: "..."'  or None
# Prepend to the system wrapper before the pint prompt


# 4. New endpoints to add:

# GET /tab/{session_id}
# return steward.tab(session_id)

# GET /best-pints
# return steward.best_pints()

# POST /built-on
# body: { "fragment_id": "...", "agent_id": "..." }
# steward.mark_built_on(fragment_id, agent_id)


# ─────────────────────────────────────────────
# ENV VARS TO SET ON THE BEELINK
# ─────────────────────────────────────────────

# DISTIL_MODEL=phi          # fastest, lowest RAM
# DIV_THRESHOLD=0.3         # raise to 0.4 if too many fragments propagate
# OLLAMA_URL=http://localhost:11434

"""
The White Horse — v0.2

New in this version:
- Bouncer renamed to Landlord (landlord.py)
- Tables: shared sessions where multiple agents interact
- POST /table/create   — open a new table
- POST /table/{id}/join  — join an existing table
- POST /table/{id}/order — order at a table (outputs shared with table)
- GET  /table/{id}/tab   — see everything on the table's tab
- GET  /tables           — list open tables
- Landlord now hard-blocks when BrackOracle is unreachable (configurable)
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import uvicorn

from pint_engine import PintEngine
from landlord import Landlord
from sessions import SessionStore

app = FastAPI(title="The White Horse", description="First round's on Jared.")

engine   = PintEngine()
landlord = Landlord()
store    = SessionStore()


# ── Request models ────────────────────────────────────────────────────────────

class OrderRequest(BaseModel):
    agent_id: str
    pint: str
    prompt: str

class TableOrderRequest(BaseModel):
    agent_id: str
    pint: str
    prompt: str

class CreateTableRequest(BaseModel):
    agent_id: str
    name: Optional[str] = "The Corner Table"

class JoinTableRequest(BaseModel):
    agent_id: str

class LastOrdersRequest(BaseModel):
    session_id: str


# ── Solo endpoints ────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "open", "pub": "The White Horse", "port": 3200, "version": "0.2"}


@app.get("/menu")
def menu():
    return {"pints": engine.list_pints()}


@app.post("/order")
async def order(req: OrderRequest):
    """Solo pint order — private session, no table."""

    # Landlord checks the prompt
    risk = await landlord.check_prompt(req.prompt, req.agent_id)
    if risk["blocked"]:
        return {
            "session_id": None,
            "status":     "refused",
            "message":    "Landlord refused service.",
            "reason":     risk.get("reason", "risk threshold exceeded")
        }

    pint = engine.load_pint(req.pint)
    if not pint:
        raise HTTPException(status_code=404, detail=f"No pint called '{req.pint}' on the menu.")

    result = await engine.serve(req.prompt, pint)

    # Landlord checks the output
    output_risk = await landlord.check_output(result["drunk_output"], req.agent_id)
    if output_risk["blocked"]:
        return {
            "session_id": None,
            "status":     "refused",
            "message":    "Landlord refused the output.",
            "reason":     output_risk.get("reason", "output risk threshold exceeded")
        }

    session_id = store.save(
        agent_id=req.agent_id,
        pint=req.pint,
        prompt=req.prompt,
        sober_output=result["sober_output"],
        drunk_output=result["drunk_output"],
        tokens=result["tokens"],
        risk_score=risk.get("risk", "low"),
        model=result["model"]
    )

    return {
        "session_id":   session_id,
        "status":       "served",
        "pint":         pint["name"],
        "sober_output": result["sober_output"],
        "drunk_output": result["drunk_output"],
        "risk":         risk.get("risk", "low"),
        "tokens":       result["tokens"]
    }


@app.post("/last-orders")
def last_orders(req: LastOrdersRequest):
    store.close_session(req.session_id)
    return {"status": "session closed", "session_id": req.session_id}


@app.get("/sessions")
def sessions(agent_id: Optional[str] = None):
    return {"sessions": store.list_sessions(agent_id)}


# ── Table endpoints ───────────────────────────────────────────────────────────

@app.get("/tables")
def list_tables():
    """List all open tables."""
    return {"tables": store.list_tables(open_only=True)}


@app.post("/table/create")
def create_table(req: CreateTableRequest):
    """Open a new shared table. Returns table_id to share with other agents."""
    table_id = store.create_table(name=req.name, agent_id=req.agent_id)
    return {
        "table_id":   table_id,
        "name":       req.name,
        "created_by": req.agent_id,
        "message":    f"Table open. Share table_id '{table_id}' so others can join."
    }


@app.post("/table/{table_id}/join")
def join_table(table_id: str, req: JoinTableRequest):
    """Join an existing table and receive its current context."""
    result = store.join_table(table_id=table_id, agent_id=req.agent_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"No table with id '{table_id}'.")
    if "error" in result:
        raise HTTPException(status_code=403, detail=result["error"])
    return result


@app.post("/table/{table_id}/order")
async def table_order(table_id: str, req: TableOrderRequest):
    """
    Order a pint at a shared table.

    The agent's drunk output gets appended to the table's shared context,
    and they receive the previous context from other agents as part of their drunk prompt.
    This is how agents influence each other — they overhear each other's chaos.
    """

    # Verify table exists and agent is a member
    table = store.get_table(table_id)
    if not table:
        raise HTTPException(status_code=404, detail=f"No table with id '{table_id}'.")
    if not table["open"]:
        raise HTTPException(status_code=403, detail="Table is closed.")

    # Auto-join if not already a member
    member_ids = [m["agent_id"] for m in table["members"]]
    if req.agent_id not in member_ids:
        store.join_table(table_id=table_id, agent_id=req.agent_id)

    # Landlord checks the prompt
    risk = await landlord.check_prompt(req.prompt, req.agent_id)
    if risk["blocked"]:
        return {
            "session_id": None,
            "status":     "refused",
            "message":    "Landlord refused service.",
            "reason":     risk.get("reason", "risk threshold exceeded")
        }

    pint = engine.load_pint(req.pint)
    if not pint:
        raise HTTPException(status_code=404, detail=f"No pint called '{req.pint}' on the menu.")

    # Get current table context — what other agents have been saying
    table_context = store.get_table_context(table_id)

    # Serve with table context injected
    result = await engine.serve(req.prompt, pint, table_context=table_context)

    # Landlord checks the output
    output_risk = await landlord.check_output(result["drunk_output"], req.agent_id)
    if output_risk["blocked"]:
        return {
            "session_id": None,
            "status":     "refused",
            "message":    "Landlord refused the output.",
            "reason":     output_risk.get("reason", "output risk threshold exceeded")
        }

    # Append this agent's drunk output to the shared table context
    store.append_table_context(
        table_id=table_id,
        agent_id=req.agent_id,
        drunk_output=result["drunk_output"],
        pint_name=pint["name"]
    )

    # Log session with table reference
    session_id = store.save(
        agent_id=req.agent_id,
        pint=req.pint,
        prompt=req.prompt,
        sober_output=result["sober_output"],
        drunk_output=result["drunk_output"],
        tokens=result["tokens"],
        risk_score=risk.get("risk", "low"),
        model=result["model"],
        table_id=table_id
    )

    return {
        "session_id":    session_id,
        "table_id":      table_id,
        "status":        "served",
        "pint":          pint["name"],
        "sober_output":  result["sober_output"],
        "drunk_output":  result["drunk_output"],
        "risk":          risk.get("risk", "low"),
        "tokens":        result["tokens"],
        "table_members": [m["agent_id"] for m in store.get_table(table_id)["members"]]
    }


@app.get("/table/{table_id}/tab")
def get_tab(table_id: str):
    """Get everything on a table's tab — members, rounds, and accumulated context."""
    table = store.get_table(table_id)
    if not table:
        raise HTTPException(status_code=404, detail=f"No table with id '{table_id}'.")
    return table


@app.post("/table/{table_id}/close")
def close_table(table_id: str):
    """Close a table. Last orders."""
    store.close_table(table_id)
    return {"status": "table closed", "table_id": table_id}


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=3200, reload=True)

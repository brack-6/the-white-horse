"""
The Landlord — White Horse safety layer via BrackOracle.

Replaces bouncer.py. Key changes from v0.1:
- Correct field mapping: BrackOracle returns 'risk' (string) not 'risk_score' (float)
- Hard block mode: when BrackOracle unreachable, blocks by default (set ALLOW_ON_ORACLE_DOWN=true to override)
- Screens both prompt input AND drunk output before returning
- All decisions logged with [LANDLORD] prefix
"""

import os
import httpx

BRACKORACLE_URL = "http://localhost:3100"
RISK_THRESHOLD  = os.getenv("RISK_THRESHOLD", "high")          # low | medium | high
ALLOW_ON_ORACLE_DOWN = os.getenv("ALLOW_ON_ORACLE_DOWN", "false").lower() == "true"

# Ordinal mapping — anything at or above threshold is blocked
RISK_LEVELS = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _is_blocked(risk: str) -> bool:
    threshold = RISK_LEVELS.get(RISK_THRESHOLD, 2)
    return RISK_LEVELS.get(risk, 0) >= threshold


class Landlord:

    async def check_prompt(self, prompt: str, agent_id: str) -> dict:
        """Screen incoming prompt before the pint is poured."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{BRACKORACLE_URL}/prompt-risk",
                    json={"content": prompt},
                    headers={"X-Free-Tier": "AGENTFAST"}
                )
                resp.raise_for_status()
                data = resp.json()
                risk     = data.get("risk", "low")
                blocked  = _is_blocked(risk)
                patterns = data.get("patterns", [])
                action   = data.get("recommended_action", "allow")
                if blocked:
                    print(f"[LANDLORD] Refused prompt for {agent_id} — risk={risk}, patterns={patterns[:1]}")
                else:
                    print(f"[LANDLORD] Prompt cleared for {agent_id} — risk={risk}")
                return {
                    "blocked":  blocked,
                    "risk":     risk,
                    "action":   action,
                    "patterns": patterns,
                    "reason":   f"prompt risk: {risk}"
                }

        except (httpx.HTTPError, Exception) as e:
            if ALLOW_ON_ORACLE_DOWN:
                print(f"[LANDLORD] WARNING: BrackOracle unreachable ({e}), allowing prompt for {agent_id}")
                return {"blocked": False, "risk": "unknown", "action": "allow", "patterns": [], "reason": "oracle_unavailable"}
            else:
                print(f"[LANDLORD] BLOCKING: BrackOracle unreachable ({e}), refusing prompt for {agent_id}")
                return {"blocked": True, "risk": "unknown", "action": "block", "patterns": [], "reason": "oracle_unavailable — hard block mode"}

    async def check_output(self, output: str, agent_id: str) -> dict:
        """Screen drunk output before returning to agent."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{BRACKORACLE_URL}/output-risk",
                    json={"content": output},
                    headers={"X-Free-Tier": "AGENTFAST"}
                )
                resp.raise_for_status()
                data     = resp.json()
                risk     = data.get("risk", "low")
                blocked  = _is_blocked(risk)
                patterns = data.get("patterns", [])
                action   = data.get("recommended_action", "allow")
                if blocked:
                    print(f"[LANDLORD] Refused output for {agent_id} — risk={risk}, patterns={patterns[:1]}")
                else:
                    print(f"[LANDLORD] Output cleared for {agent_id} — risk={risk}")
                return {
                    "blocked":  blocked,
                    "risk":     risk,
                    "action":   action,
                    "patterns": patterns,
                    "reason":   f"output risk: {risk}"
                }

        except (httpx.HTTPError, Exception) as e:
            if ALLOW_ON_ORACLE_DOWN:
                print(f"[LANDLORD] WARNING: BrackOracle unreachable ({e}), allowing output for {agent_id}")
                return {"blocked": False, "risk": "unknown", "action": "allow", "patterns": [], "reason": "oracle_unavailable"}
            else:
                print(f"[LANDLORD] BLOCKING: BrackOracle unreachable ({e}), refusing output for {agent_id}")
                return {"blocked": True, "risk": "unknown", "action": "block", "patterns": [], "reason": "oracle_unavailable — hard block mode"}

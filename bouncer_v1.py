import os
import httpx

BRACKORACLE_URL = os.getenv("BRACKORACLE_URL", "http://localhost:3100")
RISK_THRESHOLD = float(os.getenv("RISK_THRESHOLD", "0.7"))


class Bouncer:

    async def check_prompt(self, prompt: str, agent_id: str) -> dict:
        """Check prompt before serving the pint."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    f"{BRACKORACLE_URL}/prompt-risk",
                    json={"content": prompt},
                    headers={"X-Free-Tier": "AGENTFAST"}
                )
                resp.raise_for_status()
                data = resp.json()
                score = data.get("risk_score", 0.0)
                return {
                    "blocked": score >= RISK_THRESHOLD,
                    "score": score,
                    "reason": data.get("reason", "")
                }
        except httpx.HTTPError:
            # BrackOracle unreachable — log and allow with warning
            # In production you may want to block instead
            print(f"[BOUNCER] WARNING: BrackOracle unreachable, allowing prompt for {agent_id}")
            return {"blocked": False, "score": 0.0, "reason": "oracle_unavailable"}

    async def check_output(self, output: str, agent_id: str) -> dict:
        """Check model output before returning to agent."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    f"{BRACKORACLE_URL}/output-risk",
                    json={"content": output},
                    headers={"X-Free-Tier": "AGENTFAST"}
                )
                resp.raise_for_status()
                data = resp.json()
                score = data.get("risk_score", 0.0)
                return {
                    "blocked": score >= RISK_THRESHOLD,
                    "score": score,
                    "reason": data.get("reason", "")
                }
        except httpx.HTTPError:
            print(f"[BOUNCER] WARNING: BrackOracle unreachable, allowing output for {agent_id}")
            return {"blocked": False, "score": 0.0, "reason": "oracle_unavailable"}

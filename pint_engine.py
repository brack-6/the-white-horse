"""
Pint Engine — serves sober and drunk Ollama calls.

v0.2: accepts optional table_context which gets injected before the drunk prompt,
allowing agents at a shared table to influence each other's outputs.
"""

import json
import os
import httpx
from pathlib import Path
from typing import Optional

MENU_DIR    = Path(__file__).parent / "menu"
OLLAMA_URL  = os.getenv("OLLAMA_URL",   "http://localhost:11434")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

# How much of the table context to inject (chars) — keeps prompts sane
TABLE_CONTEXT_LIMIT = int(os.getenv("TABLE_CONTEXT_LIMIT", "500"))


class PintEngine:

    def list_pints(self):
        pints = []
        for f in sorted(MENU_DIR.glob("*.json")):
            with open(f) as fp:
                data = json.load(fp)
                pints.append({
                    "id":         f.stem,
                    "name":       data.get("name"),
                    "risk_level": data.get("risk_level", "low"),
                    "hash":       data.get("hash", "")
                })
        return pints

    def load_pint(self, pint_id: str):
        path = MENU_DIR / f"{pint_id}.json"
        if not path.exists():
            return None
        with open(path) as f:
            return json.load(f)

    async def serve(self, prompt: str, pint: dict, table_context: Optional[str] = None) -> dict:
        """
        Pour a pint. Returns sober and drunk outputs.

        table_context: accumulated drunk outputs from other agents at the same table.
        These are injected before the drunk prompt — agents "overhear" each other's chaos.
        """

        # ── Sober run — clean baseline ────────────────────────────────────────
        sober = await self._call_model(
            prompt=prompt,
            system="You are a helpful assistant.",
            temperature=0.7,
            top_p=0.9,
            max_tokens=pint.get("max_tokens", 800)
        )

        # ── Build drunk prompt ────────────────────────────────────────────────
        system_wrapper    = pint.get("system_wrapper", "")
        context_injection = pint.get("context_injection", "")

        # Pint's own context injection
        drunk_prompt = f"{context_injection}\n\n{prompt}".strip() if context_injection else prompt

        # Table context injection — overhearing other agents at the table
        if table_context:
            trimmed = table_context[-TABLE_CONTEXT_LIMIT:].strip()
            if trimmed:
                drunk_prompt = (
                    f"[Overheard at this table recently:]\n{trimmed}\n\n"
                    f"[Your turn:]\n{drunk_prompt}"
                )

        # ── Drunk run ─────────────────────────────────────────────────────────
        drunk = await self._call_model(
            prompt=drunk_prompt,
            system=system_wrapper or "You are a helpful assistant.",
            temperature=pint.get("temperature", 1.2),
            top_p=pint.get("top_p", 0.95),
            frequency_penalty=pint.get("frequency_penalty", 0.0),
            presence_penalty=pint.get("presence_penalty", 0.0),
            max_tokens=pint.get("max_tokens", 800)
        )

        # ── Recursion — Recursive Lager style ────────────────────────────────
        recursion = pint.get("recursion", 0)
        if recursion > 0:
            recursive_output = drunk["text"]
            for _ in range(recursion):
                reflect_prompt = (
                    f"{pint.get('system_wrapper', '')}\n\n"
                    f"Previous thought:\n{recursive_output}\n\n"
                    f"Expand and deepen this."
                )
                result = await self._call_model(
                    prompt=reflect_prompt,
                    system=system_wrapper or "You are a helpful assistant.",
                    temperature=pint.get("temperature", 1.2),
                    top_p=pint.get("top_p", 0.95),
                    max_tokens=pint.get("max_tokens", 600)
                )
                recursive_output = result["text"]
            drunk["text"] = recursive_output

        total_tokens = sober.get("tokens", 0) + drunk.get("tokens", 0)

        return {
            "sober_output": sober["text"],
            "drunk_output": drunk["text"],
            "tokens":       total_tokens,
            "model":        DEFAULT_MODEL
        }

    async def _call_model(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.7,
        top_p: float = 0.9,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
        max_tokens: int = 800
    ) -> dict:
        payload = {
            "model":   DEFAULT_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": prompt}
            ],
            "options": {
                "temperature":    temperature,
                "top_p":          top_p,
                "num_predict":    max_tokens,
                "repeat_penalty": 1.0 + abs(frequency_penalty),
            },
            "stream": False
        }

        async with httpx.AsyncClient(timeout=240.0) as client:
            try:
                resp = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
            except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.WriteTimeout) as e:
                print(f"[PINT_ENGINE] Ollama timeout: {e}")
                # Return graceful fallback response
                return {
                    "text": "I apologize, but I'm experiencing connection issues. Please try again later.",
                    "tokens": 0
                }
            except Exception as e:
                print(f"[PINT_ENGINE] Ollama error: {e}")
                # Return graceful fallback response for other errors
                return {
                    "text": "I apologize, but I'm experiencing technical difficulties. Please try again later.",
                    "tokens": 0
                }

        text   = data.get("message", {}).get("content", "")
        tokens = data.get("eval_count", 0) + data.get("prompt_eval_count", 0)

        return {"text": text, "tokens": tokens}

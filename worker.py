"""
Worker process for The White Horse - handles async pint brewing.

This allows the main FastAPI process to return immediately while 
the worker handles the expensive AI processing in the background.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.append(str(Path(__file__).parent))

from sessions import SessionStore
from pint_engine import PintEngine
from landlord import Landlord


class WhiteHorseWorker:
    """Background worker that processes pending pints."""

    def __init__(self):
        self.store = SessionStore()
        self.engine = PintEngine()
        self.landlord = Landlord()

    async def process_pending_sessions(self):
        """Process all pending sessions in the database."""
        while True:
            try:
                # Get all brewing sessions
                pending = self.store._connect().execute("""
                    SELECT session_id, agent_id, pint, prompt 
                    FROM sessions 
                    WHERE accepted = 0 AND closed = 0
                    ORDER BY timestamp ASC
                    LIMIT 10
                """).fetchall()

                for session_id, agent_id, pint, prompt in pending:
                    print(f"[WORKER] Processing session {session_id} for {agent_id}")
                    
                    try:
                        # Load pint configuration
                        pint_config = self.engine.load_pint(pint)
                        if not pint_config:
                            print(f"[WORKER] Invalid pint '{pint}' for session {session_id}")
                            self.store.update_pending(session_id, "", "", 0, "invalid_pint", "", None)
                            continue

                        # Process the pint
                        result = await self.engine.serve(prompt, pint_config)
                        
                        # Check output safety
                        output_risk = await self.landlord.check_output(result["drunk_output"], agent_id)
                        if output_risk["blocked"]:
                            print(f"[WORKER] Output blocked for session {session_id}: {output_risk.get('reason')}")
                            self.store.update_pending(session_id, "", "", 0, "refused", "", None)
                            continue

                        # Update session with results
                        self.store.update_pending(
                            session_id=session_id,
                            sober_output=result["sober_output"],
                            drunk_output=result["drunk_output"],
                            tokens=result["tokens"],
                            risk_score=output_risk.get("risk", "low"),
                            model=result["model"]
                        )
                        print(f"[WORKER] Completed session {session_id}")

                    except Exception as e:
                        print(f"[WORKER] Error processing session {session_id}: {e}")
                        self.store.update_pending(session_id, "", "", 0, "error", "", None)

                # Wait before next batch
                await asyncio.sleep(2)

            except Exception as e:
                print(f"[WORKER] Worker error: {e}")
                await asyncio.sleep(5)

    async def run(self):
        """Main worker loop."""
        print("[WORKER] White Horse worker started")
        await self.process_pending_sessions()


if __name__ == "__main__":
    import uvloop
    
    # Set up event loop policy for better performance
    if sys.platform != "win32":
        uvloop.install()
    
    worker = WhiteHorseWorker()
    asyncio.run(worker.run())

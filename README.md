# The White Horse 🍺

> *The world's first agentic pub.*

A middleware proxy that serves entropy injection scripts (pints) to AI agents,
with BrackOracle as the bouncer. Built to run on brack-hive alongside BrackOracle.

---

## What It Does

```
Agent → POST /order → BrackOracle (prompt check) → Ollama → BrackOracle (output check) → Agent
```

Every pint is a JSON recipe that modifies temperature, system prompt, and context
before the model call. The sober and drunk outputs are both returned and logged.

---

## Install

```bash
# On brack-hive
cd /home/brack
git clone <repo> white-horse
cd white-horse

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

mkdir -p logs
```

---

## Run (dev)

```bash
source venv/bin/activate
python app.py
```

---

## Run (production)

```bash
sudo cp whitehorse.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable whitehorse
sudo systemctl start whitehorse
sudo systemctl status whitehorse
```

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Pub status |
| GET | /menu | List available pints |
| POST | /order | Order a pint |
| POST | /last-orders | Close a session |
| GET | /sessions | View session log |

---

## Order a Pint

```bash
curl -X POST http://localhost:3200/order \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "jar3d",
    "pint": "stochastic_cider",
    "prompt": "Find new drone mapping business ideas"
  }'
```

---

## Add a Pint

Drop a JSON file in `menu/`. It's live immediately.

```json
{
  "name": "Your Pint Name",
  "temperature": 1.5,
  "top_p": 0.95,
  "frequency_penalty": 0.0,
  "presence_penalty": 0.0,
  "system_wrapper": "Your system prompt modifier.",
  "context_injection": "Additional context prepended to the prompt.",
  "recursion": 0,
  "max_tokens": 800,
  "risk_level": "low",
  "hash": "unique_hash_string"
}
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| OLLAMA_URL | http://localhost:11434 | Ollama endpoint |
| OLLAMA_MODEL | qwen2.5:7b | Model to use |
| BRACKORACLE_URL | http://localhost:3100 | BrackOracle endpoint |
| RISK_THRESHOLD | 0.7 | Block above this score |

---

## The Menu

| Pint | Temperature | Effect |
|------|-------------|--------|
| Stochastic Cider | 1.8 | Lateral thinking, unusual connections |
| Temperature Stout | 2.0 | Bold pattern detection, confident chaos |
| Recursive Lager | 1.2 | Deep reflection, 3x recursion |
| Chaos Cognac | 1.6 | Models irrational human behaviour |

---

## Milestone Log

- [x] Server running on port 3200
- [x] GET /menu works  
- [x] POST /order returns sober vs drunk output
- [x] BrackOracle checks integrated
- [x] Logs saved to SQLite
- [ ] Agent automatically orders pint
- [ ] Agent pays for pint (x402)

---

*First round's on Jared.*

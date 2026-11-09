# University IT helpdesk with LangGraph (practice exercise)

Fictional data only. Nothing is sent to real systems. Tested with **Python 3.12.1** (Windows) and Python 3.12 in CI.

## Install
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1          # macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt   # exact versions I used
copy .env.example .env              # macOS/Linux: cp .env.example .env
```
Edit `.env`: set `OPENAI_API_KEY` and `MODEL_NAME` (I used `gpt-5.6-luna`, provider OpenAI). Never commit `.env`.

## Run
| What | Command |
|---|---|
| Part 1 original graph (no model, no key) | `python part1.py` |
| Part 1 graph with `clarify_problem` | `python part1.py changed` |
| One message | `python helpdesk.py send --user demo-user-a --thread t1 --status normal "Show me the Wi-Fi troubleshooting steps."` |
| Interactive chat (empty line quits) | `python helpdesk.py chat --user demo-user-a --thread t1 --status normal` |
| All scenarios S01-S14 | `python run_scenarios.py` |
| Some scenarios | `python run_scenarios.py S06 S07 S08` |
| Tests (no API key) | `python -m pytest -q` |

`--status` is one of `normal`, `wifi_outage`, `recovery_outage`, `status_unavailable`.
To test a restart manually: run `send`, close the terminal, run `send` again with the same `--user` and `--thread`.

## Where memory is saved, and how to clear it
Everything is in `local-storage/` (ignored by git; change it with `HELPDESK_STORAGE_DIR`):
- `checkpoints.sqlite` - conversation state (LangGraph SQLite checkpointer)
- `user_memory.sqlite` - saved user preferences (table `user_prefs`)
- `tickets/` - local ticket drafts

Clear everything: `python helpdesk.py reset` (or delete the folder).
`run_scenarios.py` resets storage before each scenario (as `reset_before` asks) and copies tickets to `outputs/tickets/<scenario>/`.

## Logs
`outputs/part1_*_trace.json`, `outputs/scenarios/S01..S14.json`, `outputs/tickets/`.

## CI
`.github/workflows/tests.yml` runs `pytest` on every push. The tests use a clearly labelled fake model (`tests/fakes.py`), so no key is needed. The real-model runs (`run_scenarios.py`) are separate.
import json
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
import part1
from memory import reset_storage

scenarios = json.loads(Path("data/scenarios.json").read_text(encoding="utf-8"))["scenarios"]
wanted = set(sys.argv[1:])
OUT = Path("outputs/scenarios"); OUT.mkdir(parents=True, exist_ok=True)
env = {**os.environ, "PYTHONIOENCODING": "utf-8"}

for sc in scenarios:
    if wanted and sc["id"] not in wanted:
        continue
    print(f"\n===== {sc['id']} {sc['title']} (snapshot {sc['status_profile']}) =====")
    log = OUT / f"{sc['id']}.json"
    log.unlink(missing_ok=True)
    if sc.get("reset_before"):
        reset_storage()

    if sc["part"] == 1:
        changed = sc.get("graph_variant") == "with_clarification"
        app = part1.build_graph(changed=changed)
        runs = []
        for ev in sc["events"]:
            r = part1.run_with_trace(app, ev["message"])
            r.update(user_id=ev["user_id"], thread_id=ev["thread_id"])
            print(r["message"], "->", " -> ".join(r["node_order"]))
            runs.append(r)
        log.write_text(json.dumps({"scenario": sc["id"], "status_profile": sc["status_profile"],
                                   "graph_variant": "changed" if changed else "original",
                                   "runs": runs}, indent=2, ensure_ascii=False), encoding="utf-8")
        continue

    segments, cur = [], []
    for ev in sc["events"]:
        if ev["action"] == "restart_process":
            segments.append(cur); cur = []
        else:
            cur.append(ev)
    segments.append(cur)
    for i, seg in enumerate(segments):
        if i:
            print("\n--- process terminated, new process started on the same storage ---")
        subprocess.run([sys.executable, "helpdesk.py", "batch", "--scenario", sc["id"],
                        "--status", sc["status_profile"]],
                       input=json.dumps(seg), text=True, encoding="utf-8", check=True, env=env)
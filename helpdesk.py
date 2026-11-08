import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from agent import Helpdesk
from memory import reset_storage

PROFILES = ["normal", "wifi_outage", "recovery_outage", "status_unavailable"]


def build_model():
    from langchain_openai import ChatOpenAI
    name = os.getenv("MODEL_NAME")
    if not name:
        sys.exit("Set MODEL_NAME in .env")
    return ChatOpenAI(model=name, reasoning_effort=os.getenv("REASONING_EFFORT", "none"))


def show(rec):
    print("\nhelpdesk>", rec["final_response"])
    print("  [nodes:", " -> ".join(rec["nodes"]), "| tools:",
          [t["tool"] for t in rec["tool_requests"]], "| limit:", rec["loop_limit_reached"], "]")
    for f in rec["ticket_files"]:
        print("  [ticket file:", f, "]")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("chat", "send", "batch"):
        s = sub.add_parser(name)
        s.add_argument("--status", default="normal", choices=PROFILES)
        if name != "batch":
            s.add_argument("--user", default="demo-user-a")
            s.add_argument("--thread", required=True)
        if name == "send":
            s.add_argument("message")
        if name == "batch":
            s.add_argument("--scenario", required=True)
    sub.add_parser("reset")
    a = p.parse_args()

    if a.cmd == "reset":
        reset_storage()
        print("Storage cleared:", os.getenv("HELPDESK_STORAGE_DIR", "local-storage"))
        return

    hd = Helpdesk(build_model())
    try:
        if a.cmd == "chat":
            log = Path("outputs/chat"); log.mkdir(parents=True, exist_ok=True)
            print(f"user={a.user} thread={a.thread} status={a.status}. Empty line to quit.")
            while (text := input("\nyou> ").strip()):
                rec = hd.send(a.user, a.thread, a.status, text)
                show(rec)
                with open(log / f"{a.user}__{a.thread}.jsonl", "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        elif a.cmd == "send":
            show(hd.send(a.user, a.thread, a.status, a.message))
        elif a.cmd == "batch":
            events = json.load(sys.stdin)
            path = Path("outputs/scenarios") / f"{a.scenario}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            log = (json.loads(path.read_text(encoding="utf-8")) if path.exists() else
                   {"scenario": a.scenario, "status_profile": a.status,
                    "model": os.getenv("MODEL_NAME"), "provider": "openai", "segments": []})
            seg = {"process_id": os.getpid(), "events": []}
            for ev in events:
                rec = hd.send(ev["user_id"], ev["thread_id"], a.status, ev["message"], a.scenario)
                show(rec)
                seg["events"].append(rec)
            log["segments"].append(seg)
            path.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
    finally:
        hd.close()


if __name__ == "__main__":
    main()
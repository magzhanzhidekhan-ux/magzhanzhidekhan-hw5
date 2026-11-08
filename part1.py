import json
import sys
from pathlib import Path
from typing import TypedDict

from langgraph.graph import StateGraph, START, END

ROOT = Path(__file__).parent
HELPDESK = json.loads((ROOT / "data" / "helpdesk.json").read_text(encoding="utf-8"))
ALIASES = HELPDESK["topic_aliases"]      # {"wifi": ["wifi", "wi-fi"], "password": ["password"]}


class State(TypedDict, total=False):
    message: str
    category: str
    reply: str


def topics_in(message):
    text = message.lower()
    return [t for t, words in ALIASES.items() if any(w in text for w in words)]


def format_instructions(topic):
    ins = HELPDESK["instructions"][topic]
    steps = "\n".join(f"{i}. {s}" for i, s in enumerate(ins["steps"], 1))
    return f"{ins['title']} [{ins['instruction_id']}]\n{steps}"


def read_request_original(state: State) -> dict:
    found = topics_in(state["message"])
    if "wifi" in found:
        return {"category": "wifi"}
    if "password" in found:
        return {"category": "password"}
    return {"category": "other"}


def read_request_changed(state: State) -> dict:
    found = topics_in(state["message"])
    if "wifi" in found and "password" in found:
        return {"category": "both"}
    if "wifi" in found:
        return {"category": "wifi"}
    if "password" in found:
        return {"category": "password"}
    return {"category": "other"}


def wifi_help(state: State) -> dict:
    return {"reply": format_instructions("wifi")}


def password_help(state: State) -> dict:
    return {"reply": format_instructions("password")}


def other_help(state: State) -> dict:
    return {"reply": "Is your problem about Wi-Fi or about a password?"}


def clarify_problem(state: State) -> dict:
    return {"reply": "Your message mentions both Wi-Fi and a password. "
                     "Which problem do you want to solve first: Wi-Fi or password?"}


def route_request(state: State) -> str:
    return state["category"]


def build_graph(changed=False):
    g = StateGraph(State)
    g.add_node("read_request", read_request_changed if changed else read_request_original)
    g.add_node("wifi_help", wifi_help)
    g.add_node("password_help", password_help)
    g.add_node("other_help", other_help)
    routes = {"wifi": "wifi_help", "password": "password_help", "other": "other_help"}
    if changed:
        g.add_node("clarify_problem", clarify_problem)
        routes["both"] = "clarify_problem"
    g.add_edge(START, "read_request")
    g.add_conditional_edges("read_request", route_request, routes)
    for node in set(routes.values()):
        g.add_edge(node, END)
    return g.compile()


def run_with_trace(app, message):
    """Returns the order of nodes and the full state after every step."""
    trace, order = [], []
    for mode, chunk in app.stream({"message": message}, stream_mode=["updates", "values"]):
        if mode == "updates":
            order.extend(chunk.keys())
        else:
            trace.append(dict(chunk))        # full state after this step
    return {"message": message, "node_order": order, "states": trace}


MESSAGES = ["I cannot connect to Wi-Fi.", "I forgot my PASSWORD.",
            "My laptop screen is broken.", "My Wi-Fi password does not work."]

if __name__ == "__main__":
    changed = len(sys.argv) > 1 and sys.argv[1] == "changed"
    app = build_graph(changed)
    out = Path("outputs"); out.mkdir(exist_ok=True)
    results = [run_with_trace(app, m) for m in MESSAGES]
    for r in results:
        print(r["message"], "->", " -> ".join(r["node_order"]))
    name = "part1_changed" if changed else "part1_original"
    (out / f"{name}_trace.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / f"{name}_graph.mmd").write_text(app.get_graph().draw_mermaid(), encoding="utf-8")
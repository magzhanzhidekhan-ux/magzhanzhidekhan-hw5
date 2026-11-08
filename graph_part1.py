import json
from pathlib import Path
from typing import TypedDict
from langgraph.graph import StateGraph, START, END

HELPDESK = json.loads((Path(__file__).parent / "data" / "helpdesk.json").read_text(encoding="utf-8"))


class State(TypedDict, total=False):
    message: str
    category: str
    reply: str


def read_request(state: State) -> dict:
    text = state["message"].lower()
    if "wifi" in text or "wi-fi" in text:
        category = "wifi"
    elif "password" in text:
        category = "password"
    else:
        category = "other"
    return {"category": category}


def route_request(state: State) -> str:
    return {"wifi": "wifi_help", "password": "password_help"}.get(state["category"], "other_help")


def wifi_help(state: State) -> dict:
    return {"reply": HELPDESK["wifi"]}      # TODO: use the real key/structure from helpdesk.json


def password_help(state: State) -> dict:
    return {"reply": HELPDESK["password"]}  # TODO: same


def other_help(state: State) -> dict:
    return {"reply": "Is your problem about Wi-Fi or about a password?"}


def build_graph():
    g = StateGraph(State)
    g.add_node("read_request", read_request)
    g.add_node("wifi_help", wifi_help)
    g.add_node("password_help", password_help)
    g.add_node("other_help", other_help)
    g.add_edge(START, "read_request")
    g.add_conditional_edges("read_request", route_request,
                            ["wifi_help", "password_help", "other_help"])
    for n in ("wifi_help", "password_help", "other_help"):
        g.add_edge(n, END)
    return g.compile()


if __name__ == "__main__":
    app = build_graph()
    for msg in ["I cannot connect to Wi-Fi.", "I forgot my PASSWORD.",
                "My laptop screen is broken.", "My Wi-Fi password does not work."]:
        print("MESSAGE:", msg)
        for step in app.stream({"message": msg}, stream_mode="updates"):
            print("  ", step)          # node name + the update it returned
        print()
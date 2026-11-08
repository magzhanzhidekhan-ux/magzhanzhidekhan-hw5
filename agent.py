import json
import os
import sqlite3
import time
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from helpdesk_tools import ALL_TOOLS, TOOLS_BY_NAME
from memory import UserMemory, storage_dir

MAX_TOOL_ROUNDS = int(os.getenv("MAX_TOOL_ROUNDS", "5"))

SYSTEM_PROMPT = """You are a university IT helpdesk assistant in a PRACTICE exercise. All data is fictional and nothing is sent to real systems.
Scope: Wi-Fi troubleshooting, password recovery guidance, service status lookup, local ticket drafts. For anything else say it is out of scope and ask whether the problem is about Wi-Fi or a password.
Rules:
- For instructions always call find_instructions. Do not recite steps from memory.
- To check an outage call check_service_status (service 'wifi', or 'account_recovery' for password problems). Status 'unknown' means the source is unavailable: it is NOT operational and NOT a confirmed outage. Never invent a repair time.
- Call prepare_ticket only when you know the problem and the steps the user already tried. If either is missing, ask the user. Never invent details; use only steps the user stated. Pass the status you actually checked, or 'not_checked'.
- Obey conditions in the request. If the user says to prepare a ticket only if the service is operating: prepare it only when the status tool says operational. If the status is outage, do not prepare it and explain. If the status is unknown, do not prepare it and offer a draft that says the status could not be checked.
- Never ask for or store passwords, API keys or recovery codes.
- A ticket is only a local draft. Say nothing was sent, and give the ticket id and file path from the tool result.
- If the user asks you to remember the language of replies, call save_user_preference(key='language', value=...).
- Answer questions about earlier messages only from this conversation's history. If there is none, say so.
- If a language preference is saved below, write your replies in that language.
- Call prepare_ticket only if the user explicitly asks for a ticket or accepts your offer. Do not check service status unless the user asks, or a ticket or outage question requires it.
- When you mention a file path, copy it exactly from the tool result."""


class AgentState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    user_prefs: dict
    tool_rounds: int
    limit_reached: bool


def build_system_prompt(prefs):
    if prefs:
        return SYSTEM_PROMPT + f"\n\nSaved preferences for this user: {json.dumps(prefs)}"
    return SYSTEM_PROMPT + "\n\nNo saved preferences for this user."


def build_graph(model, checkpointer):
    bound = model.bind_tools(ALL_TOOLS)

    def load_user_memory(state, config):
        c = config["configurable"]
        return {"user_prefs": UserMemory(c.get("storage_dir")).get_all(c["user_id"])}

    def agent(state, config):
        msgs = [SystemMessage(build_system_prompt(state.get("user_prefs")))] + state["messages"]
        return {"messages": [bound.invoke(msgs)]}

    def tools(state, config):
        out = []
        for tc in state["messages"][-1].tool_calls:
            t0 = time.perf_counter()
            tool = TOOLS_BY_NAME.get(tc["name"])
            try:
                result = (tool.invoke(tc["args"], config) if tool
                          else {"error": "unknown_tool", "message": f"No tool {tc['name']}"})
            except Exception as e:                       # bad arguments etc.
                result = {"error": "tool_failed", "message": str(e)[:200]}
            out.append(ToolMessage(content=json.dumps(result, ensure_ascii=False),
                                   tool_call_id=tc["id"], name=tc["name"],
                                   additional_kwargs={"seconds": round(time.perf_counter() - t0, 5)}))
        return {"messages": out, "tool_rounds": state.get("tool_rounds", 0) + 1}

    def limit_reached(state, config):
        msgs = [ToolMessage(content=json.dumps({"error": "loop_limit_reached"}),
                            tool_call_id=tc["id"], name=tc["name"])
                for tc in state["messages"][-1].tool_calls]
        msgs.append(AIMessage(content="I reached the tool-call limit and stopped. "
                                      "Please try a simpler request."))
        return {"messages": msgs, "limit_reached": True}

    def route_after_agent(state):
        if getattr(state["messages"][-1], "tool_calls", None):
            return "tools" if state.get("tool_rounds", 0) < MAX_TOOL_ROUNDS else "limit_reached"
        return "end"

    g = StateGraph(AgentState)
    g.add_node("load_user_memory", load_user_memory)
    g.add_node("agent", agent)
    g.add_node("tools", tools)
    g.add_node("limit_reached", limit_reached)
    g.add_edge(START, "load_user_memory")
    g.add_edge("load_user_memory", "agent")
    g.add_conditional_edges("agent", route_after_agent,
                            {"tools": "tools", "limit_reached": "limit_reached", "end": END})
    g.add_edge("tools", "agent")
    g.add_edge("limit_reached", END)
    return g.compile(checkpointer=checkpointer)


def text_of(msg):
    c = msg.content
    if isinstance(c, list):
        return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in c)
    return c


SOURCES = {"find_instructions": "reference file data/helpdesk.json",
           "check_service_status": "data/service_status.json snapshot",
           "prepare_ticket": "local ticket file",
           "save_user_preference": "user memory (write)"}


class Helpdesk:
    def __init__(self, model, storage=None):
        self.storage = storage_dir(storage)
        self.conn = sqlite3.connect(self.storage / "checkpoints.sqlite", check_same_thread=False)
        self.graph = build_graph(model, SqliteSaver(self.conn))

    def close(self):
        self.conn.close()

    @staticmethod
    def _thread_key(user_id, thread_id):
        return f"{user_id}:{thread_id}"      # the same thread name for two users never collides

    def history(self, user_id, thread_id):
        cfg = {"configurable": {"thread_id": self._thread_key(user_id, thread_id)}}
        return (self.graph.get_state(cfg).values or {}).get("messages", [])

    def send(self, user_id, thread_id, status_profile, text, scenario_id=None):
        config = {"recursion_limit": 40, "configurable": {
            "thread_id": self._thread_key(user_id, thread_id), "user_id": user_id,
            "status_profile": status_profile, "storage_dir": str(self.storage)}}
        # the ticket should show the plain thread name, not the internal key
        config["configurable"]["thread_id_public"] = thread_id
        rec = {"scenario": scenario_id, "user_id": user_id, "thread_id": thread_id,
               "status_profile": status_profile, "user_message": text,
               "conversation_messages_read": len(self.history(user_id, thread_id)),
               "conversation_memory_source": "checkpoint (SQLite, thread %s)" % thread_id,
               "user_memory_read": None, "nodes": [], "tool_requests": [], "tool_results": [],
               "final_response": None, "ticket_files": [], "loop_limit_reached": False}
        inp = {"messages": [HumanMessage(text)], "tool_rounds": 0, "limit_reached": False}
        for chunk in self.graph.stream(inp, config, stream_mode="updates"):
            for node, upd in chunk.items():
                upd = upd or {}
                rec["nodes"].append(node)
                if node == "load_user_memory":
                    rec["user_memory_read"] = upd.get("user_prefs", {})
                elif node == "agent":
                    m = upd["messages"][-1]
                    if m.tool_calls:
                        rec["tool_requests"] += [{"id": c["id"], "tool": c["name"], "args": c["args"]}
                                                 for c in m.tool_calls]
                    else:
                        rec["final_response"] = text_of(m)
                elif node == "tools":
                    for m in upd["messages"]:
                        result = json.loads(m.content)
                        rec["tool_results"].append({
                            "id": m.tool_call_id, "tool": m.name, "result": result,
                            "source": SOURCES.get(m.name),
                            "seconds": m.additional_kwargs.get("seconds")})
                        if isinstance(result, dict) and result.get("path"):
                            rec["ticket_files"].append(result["path"])
                elif node == "limit_reached":
                    rec["loop_limit_reached"] = True
                    rec["final_response"] = text_of(upd["messages"][-1])
        rec["conversation_messages_after"] = len(self.history(user_id, thread_id))
        return rec
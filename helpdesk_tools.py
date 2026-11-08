import json
import re
import uuid
from pathlib import Path
from typing import Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from memory import UserMemory, storage_dir

DATA = Path(__file__).parent / "data"
SECRET = re.compile(r"(password|passcode|recovery code)\s*[:=]\s*\S+", re.I)


def _load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def _ctx(config):
    return (config or {}).get("configurable", {})

def find_instructions_impl(topic):
    h = _load("helpdesk.json")
    t = str(topic).strip().lower()
    for name, words in h["topic_aliases"].items():
        if t == name or t in words:
            return {"topic": name, **h["instructions"][name], "source": "data/helpdesk.json"}
    return {"error": "unknown_topic", "message": "Available topics: wifi, password",
            "available": list(h["instructions"])}


def check_service_status_impl(service, status_profile):
    h = _load("helpdesk.json")
    profiles = _load("service_status.json")["profiles"]
    key = str(service).strip().lower()
    for topic, words in h["topic_aliases"].items():
        if key in words:
            key = topic
    key = h["topic_services"].get(key, key)          # password -> account_recovery
    if status_profile not in profiles:
        return {"error": "unknown_profile", "message": f"No snapshot named {status_profile}"}
    if key not in profiles[status_profile]:
        return {"error": "unknown_service", "message": "Services: wifi, account_recovery"}
    return {"service": key, **profiles[status_profile][key], "status_profile": status_profile}


def prepare_ticket_impl(category, summary, steps_tried, service_status,
                        user_id, thread_id, status_profile, storage_path=None):
    h = _load("helpdesk.json")
    steps = [s.strip() for s in (steps_tried or []) if isinstance(s, str) and s.strip()]
    missing = []
    if category not in h["instructions"]:
        missing.append("category (wifi or password)")
    if not (summary or "").strip():
        missing.append("problem description")
    if not steps:
        missing.append("steps already tried")
    if missing:
        return {"error": "missing_information", "missing": missing,
                "message": "Ask the user for these details. Do not invent them."}
    if SECRET.search(summary) or any(SECRET.search(s) for s in steps):
        return {"error": "secret_information",
                "message": "Ticket text must not contain passwords or recovery codes."}
    ticket = _load("ticket_template.json")["ticket"]
    ticket.update({
        "ticket_id": "TCK-" + uuid.uuid4().hex[:8], "status": "draft",
        "user_id": user_id, "thread_id": thread_id, "category": category,
        "summary": summary.strip(), "steps_tried": steps,
        "service_status": service_status,
        "status_profile": status_profile if service_status != "not_checked" else None,
        "reference_ids": [h["instructions"][category]["instruction_id"]],
    })
    folder = storage_dir(storage_path) / "tickets"
    folder.mkdir(exist_ok=True)
    path = folder / f"{ticket['ticket_id']}.json"
    path.write_text(json.dumps(ticket, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"ticket_id": ticket["ticket_id"], "path": str(path), "ticket": ticket,
            "note": "Local draft only. Nothing was sent."}


def save_user_preference_impl(user_id, key, value, storage_path=None):
    if key != "language":
        return {"error": "unsupported_key", "message": "Only 'language' can be saved."}
    value = str(value).strip()
    if not value or len(value) > 50:
        return {"error": "invalid_value", "message": "Language must be 1-50 characters."}
    UserMemory(storage_path).set(user_id, key, value)
    return {"saved": {key: value}}


@tool
def find_instructions(topic: str) -> dict:
    """Look up the local helpdesk instructions for a topic: 'wifi' or 'password'.
    Returns the title, numbered steps and the instruction id (for example GUIDE-WIFI)."""
    return find_instructions_impl(topic)


@tool
def check_service_status(service: str, config: RunnableConfig) -> dict:
    """Check whether a service is operating or has a known outage. service is 'wifi' or
    'account_recovery' (use account_recovery for password problems). Status 'unknown' means
    the status source is unavailable: it is not operational and not a confirmed outage."""
    return check_service_status_impl(service, _ctx(config).get("status_profile", "normal"))


@tool
def prepare_ticket(category: Literal["wifi", "password"], summary: str,
                   steps_tried: list[str],
                   service_status: Literal["operational", "outage", "unknown", "not_checked"],
                   config: RunnableConfig) -> dict:
    """Save a LOCAL ticket draft (nothing is sent). Needs a problem summary and the steps the
    user already tried, using only what the user said. If either is missing, do not call this
    tool: ask the user. service_status is the status you actually checked, or 'not_checked'."""
    c = _ctx(config)
    return prepare_ticket_impl(category, summary, steps_tried, service_status,
                               c.get("user_id"), c.get("thread_id_public") or c.get("thread_id"),
                               c.get("status_profile"), c.get("storage_dir"))


@tool
def save_user_preference(key: Literal["language"], value: str, config: RunnableConfig) -> dict:
    """Remember a preference for this user across conversations. Use it when the user asks
    you to remember the language of replies (key='language', value for example 'Kazakh')."""
    c = _ctx(config)
    return save_user_preference_impl(c["user_id"], key, value, c.get("storage_dir"))


ALL_TOOLS = [find_instructions, check_service_status, prepare_ticket, save_user_preference]
TOOLS_BY_NAME = {t.name: t for t in ALL_TOOLS}
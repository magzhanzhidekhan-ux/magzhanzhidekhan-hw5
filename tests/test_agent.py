import json
import pytest
from langchain_core.messages import ToolMessage

from agent import Helpdesk
from fakes import ScriptedModel, call, say


def conditional(messages):
    tm = [m for m in messages if isinstance(m, ToolMessage)]
    if not tm:
        return call("check_service_status", {"service": "wifi"})
    last = json.loads(tm[-1].content)
    if tm[-1].name == "check_service_status" and last["status"] == "operational":
        return call("prepare_ticket", {"category": "wifi", "summary": "Campus-Demo fails",
                                       "steps_tried": ["enabled Wi-Fi"], "service_status": "operational"})
    return say("done")


@pytest.mark.parametrize("profile,tickets", [("normal", 1), ("wifi_outage", 0), ("status_unavailable", 0)])
def test_tool_result_changes_what_the_agent_does(tmp_path, profile, tickets):
    hd = Helpdesk(ScriptedModel(conditional), tmp_path)
    rec = hd.send("demo-user-a", "t1", profile, "check wifi, ticket if operating")
    hd.close()
    assert len(rec["ticket_files"]) == tickets
    assert rec["nodes"].count("tools") == (2 if tickets else 1)


def test_loop_limit_stops_and_keeps_history_valid(tmp_path):
    state = {"stop": False}
    hd = Helpdesk(ScriptedModel(lambda m: say("ok") if state["stop"]
                                else call("find_instructions", {"topic": "wifi"})), tmp_path)
    rec = hd.send("demo-user-a", "t1", "normal", "loop forever")
    assert rec["loop_limit_reached"] and len(rec["tool_results"]) == 5
    state["stop"] = True
    assert hd.send("demo-user-a", "t1", "normal", "hello")["final_response"] == "ok"
    hd.close()


def pref_script(messages):
    if any(isinstance(m, ToolMessage) for m in messages):
        return say("saved")
    return call("save_user_preference", {"key": "language", "value": "Kazakh"})


def test_memory_survives_restart_and_stays_separate(tmp_path):
    hd = Helpdesk(ScriptedModel(pref_script), tmp_path)
    hd.send("demo-user-a", "t1", "normal", "remember Kazakh")
    hd.close()

    plain = ScriptedModel(lambda m: say("ok"))
    hd2 = Helpdesk(plain, tmp_path)
    assert len(hd2.history("demo-user-a", "t1")) > 0
    assert hd2.send("demo-user-a", "t1", "normal", "again")["conversation_messages_read"] > 0

    rec_new = hd2.send("demo-user-a", "t2", "normal", "language?")
    assert rec_new["conversation_messages_read"] == 0
    assert rec_new["user_memory_read"] == {"language": "Kazakh"}
    assert "Kazakh" in plain.seen[-1][0].content

    rec_b = hd2.send("demo-user-b", "t1", "normal", "language?")
    assert rec_b["conversation_messages_read"] == 0 and rec_b["user_memory_read"] == {}
    assert "Kazakh" not in plain.seen[-1][0].content
    hd2.close()
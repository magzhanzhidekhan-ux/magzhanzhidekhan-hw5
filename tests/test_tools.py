import json
import pytest
from helpdesk_tools import (check_service_status_impl, find_instructions_impl,
                            prepare_ticket_impl, save_user_preference_impl)
from memory import UserMemory


def test_find_instructions():
    r = find_instructions_impl("Wi-Fi")
    assert r["instruction_id"] == "GUIDE-WIFI" and len(r["steps"]) == 4
    assert find_instructions_impl("password")["instruction_id"] == "GUIDE-PASSWORD"
    assert find_instructions_impl("printer")["error"] == "unknown_topic"


@pytest.mark.parametrize("profile,service,status", [
    ("normal", "wifi", "operational"), ("wifi_outage", "wifi", "outage"),
    ("status_unavailable", "wifi", "unknown"), ("recovery_outage", "password", "outage")])
def test_status_snapshots(profile, service, status):
    assert check_service_status_impl(service, profile)["status"] == status


def test_status_errors():
    assert check_service_status_impl("wifi", "nope")["error"] == "unknown_profile"
    assert check_service_status_impl("printer", "normal")["error"] == "unknown_service"


def test_ticket_draft_is_saved(tmp_path):
    r = prepare_ticket_impl("wifi", "Campus-Demo will not connect", ["enabled Wi-Fi"],
                            "operational", "demo-user-a", "t1", "normal", tmp_path)
    saved = json.loads(open(r["path"], encoding="utf-8").read())
    assert saved["status"] == "draft" and saved["steps_tried"] == ["enabled Wi-Fi"]
    assert saved["reference_ids"] == ["GUIDE-WIFI"] and saved["ticket_id"].startswith("TCK-")


def test_ticket_missing_details_and_secrets(tmp_path):
    r = prepare_ticket_impl("wifi", "", [], "not_checked", "u", "t", "normal", tmp_path)
    assert r["error"] == "missing_information" and len(r["missing"]) == 2
    r = prepare_ticket_impl("password", "cannot sign in", ["tried password: hunter2"],
                            "not_checked", "u", "t", "normal", tmp_path)
    assert r["error"] == "secret_information"
    assert not (tmp_path / "tickets").exists() or not list((tmp_path / "tickets").iterdir())


def test_preference_tool(tmp_path):
    assert save_user_preference_impl("demo-user-a", "language", "Kazakh", tmp_path)["saved"]
    assert UserMemory(tmp_path).get_all("demo-user-a") == {"language": "Kazakh"}
    assert save_user_preference_impl("demo-user-a", "color", "red", tmp_path)["error"]
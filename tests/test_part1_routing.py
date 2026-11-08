import pytest
from part1 import build_graph


def path(app, msg):
    return [next(iter(c)) for c in app.stream({"message": msg}, stream_mode="updates")]


CASES = [("I cannot connect to Wi-Fi.", "wifi_help"), ("I forgot my PASSWORD.", "password_help"),
         ("My laptop screen is broken.", "other_help"),
         ("My Wi-Fi password does not work.", "wifi_help")]


@pytest.mark.parametrize("msg,node", CASES)
def test_original_graph_routes(msg, node):
    assert path(build_graph(), msg) == ["read_request", node]


def test_changed_graph_asks_for_clarification_only_on_two_topics():
    app = build_graph(changed=True)
    assert path(app, "My Wi-Fi password does not work.") == ["read_request", "clarify_problem"]
    assert path(app, "I cannot connect to Wi-Fi.") == ["read_request", "wifi_help"]
"""FAKE model used only by the tests, so they need no API key."""
import uuid

from langchain_core.messages import AIMessage


class ScriptedModel:
    def __init__(self, script):
        self.script, self.seen = script, []

    def bind_tools(self, tools):
        return self

    def invoke(self, messages, config=None):
        self.seen.append(messages)
        return self.script(messages)


def call(name, args):
    return AIMessage(content="", tool_calls=[
        {"name": name, "args": args, "id": "c" + uuid.uuid4().hex[:8], "type": "tool_call"}])


def say(text):
    return AIMessage(content=text)
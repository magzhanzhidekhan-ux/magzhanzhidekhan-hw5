# HW5 — My LangGraph helpdesk
**AI assistance:** 
I used Claude (claude.ai) to explain the task, to draft the code (`agent.py`, `helpdesk_tools.py`, `memory.py`, `helpdesk.py`, `run_scenarios.py`, 
tests, workflow) and to help with Git. I ran all code, tests and scenarios myself, fixed the errors that 
appeared, and the results below come from my own logs.

## Part 1 — How the graph works

### My graph and state

```
START → read_request → [route_request]
                         ├─ wifi     → wifi_help     → END
                         ├─ password → password_help → END
                         └─ other    → other_help    → END
```

State fields: `message` (the user's original text), `category` (set by `read_request`), `reply` (set by a help node).

| Node | Reads | Changes |
|---|---|---|
| `read_request` | `message` | `category` |
| `wifi_help` | nothing from the state (reads `data/helpdesk.json`) | `reply` |
| `password_help` | nothing from the state (reads `data/helpdesk.json`) | `reply` |
| `other_help` | nothing from the state | `reply` |

**Node update vs conditional edge.** 
A node returns an update: a dictionary with the state fields it wants to change, and LangGraph merges 
it into the state. A conditional edge (`route_request`) only returns the name of the route to follow.
It changes nothing in the state.

**What the next node receives.** 
The current state of the whole graph (the original input plus all updates merged so far), not only 
the previous node's update. For example, `wifi_help` could read `message` even though `read_request` 
did not return it.

**START, END and compile.** 
`START` and `END` are the entry and exit points of the graph. `compile()` turns the description 
(nodes and edges) into a runnable object. Before compiling, the graph is only a plan.

### Predictions before running

| Message | Predicted route | Actual route | What I learned |
| --- | --- | --- | --- |
| I cannot connect to Wi-Fi. | read_request → wifi_help | read_request → wifi_help | The Wi-Fi rule matches both "Wi-Fi" and "wifi"; lowercasing makes the match simple. |
| I forgot my PASSWORD. | read_request → password_help | read_request → password_help | Upper case does not matter because I lowercase the message before checking. |
| My laptop screen is broken. | read_request → other_help | read_request → other_help | A message with no known topic falls through to the default rule and the user is asked what the problem is. |
| My Wi-Fi password does not work. | read_request → wifi_help | read_request → wifi_help | The message mentions both topics, but the Wi-Fi rule is checked first, so the password topic is never looked at. The order of the rules decides, not the graph structure. |

Traces: `outputs/part1_original_trace.json` (node order and full state after each step).

**Both topics in one message.** 
"My Wi-Fi password does not work." contains "wi-fi" and "password". Rule 1 (Wi-Fi) matches first, so the request goes to `wifi_help`. The user may actually need password help, and the graph gives no sign of this problem.

### My change to the graph

```
START → read_request → [route_request]
                         ├─ wifi     → wifi_help       → END
                         ├─ password → password_help   → END
                         ├─ both     → clarify_problem → END
                         └─ other    → other_help      → END
```

`read_request` now returns the category `both` when both topics appear, and the new node `clarify_problem` asks which problem to solve first.

New trace (`outputs/part1_changed_trace.json`):

```
I cannot connect to Wi-Fi.        -> read_request -> wifi_help
I forgot my PASSWORD.             -> read_request -> password_help
My laptop screen is broken.       -> read_request -> other_help
My Wi-Fi password does not work.  -> read_request -> clarify_problem
```

Only the fourth message changed its route. The other three behave as before.

**What LangGraph controls and what my functions decide.** 
LangGraph controls the execution: it starts at `START`, runs a node, merges the returned update 
into the state, calls the conditional edge, follows the chosen route and stops at `END`. My own Python 
functions decide the content: how a message is classified, which category name is returned, and what each 
reply says. There is no model in this part, so every decision is a fixed rule that I wrote.

## Part 2 — Model and tools

Model: `gpt-5.6-luna`, provider OpenAI (via `langchain-openai`), reasoning set to `none`.

```
START → load_user_memory → agent ──(tool request, rounds < 5)──→ tools ─┐
                             ↑                                           │
                             └───────────────────────────────────────────┘
                             ├─(tool request, rounds = 5)→ limit_reached → END
                             └─(plain answer)→ END
```

**Tools** (`helpdesk_tools.py`): `find_instructions`, `check_service_status`, `prepare_ticket`, plus `save_user_preference` for Part 3. Each has a plain function (`*_impl`) that works without the agent and without a model. Direct calls: `outputs/direct_tool_calls.txt` [ВСТАВЬТЕ: one line on what it shows, e.g. the outage snapshot returns "outage" and the ticket file was written].

**How does the graph decide between running a tool and ending?** 
The conditional edge `route_after_agent` looks at the last message. If it has `tool_calls`, it goes to `tools`; otherwise to END.

**Which component requests, which executes?** 
The model (node `agent`) only requests, as a tool name plus arguments. My Python node `tools` executes, 
and the model never runs anything. The user id, thread id and status snapshot come from the run 
configuration, not from the model's arguments.

**What changes in the state after a tool result returns?** 
One `ToolMessage` per request is appended to `messages`, using the same `tool_call_id`, and `tool_rounds`
goes up by 1. The next `agent` call sees the results and decides to continue or answer.

**Difference from Part 1.** 
In Part 1 my own rules chose the route from the text. Here the model chooses the next step from the tool 
results, so the path is decided while running (S06: two tool rounds; S07: one).

**Loop limit.** 
`MAX_TOOL_ROUNDS = 5`. The `tools` node counts rounds and the conditional edge enforces the limit. 
When it is reached, node `limit_reached` answers every pending request with an error and writes a final 
message, so the saved history stays valid. A second guard is `recursion_limit = 40`. The test 
`test_loop_limit_stops_and_keeps_history_valid` checks it with a fake model that asks for tools forever.

**Same conditional request, three snapshots** 
(request: check Wi-Fi; prepare a ticket only if it is operating):

| Snapshot | Scenario | Status tool result | What the assistant did |
|---|---|---|---|
| normal | S06 | `operational` | Prepared ticket `TCK-5b0d2c86` (`outputs/tickets/S06/`). |
| wifi_outage | S07 | `outage` | No ticket; explained why; no repair time invented. |
| status_unavailable | S08 | `unknown` | No ticket; said it cannot confirm operating or outage. |

In S06 the ticket `steps_tried` are only `Enabled Wi-Fi.` and `Forgot the saved network.`, which are the steps I stated; `thread_id` is `s06`. Real S06 run (requests, results, answer): `outputs/scenarios/S06.json`.

## Part 3 — Memory

- **Conversation memory:** LangGraph `SqliteSaver` (`local-storage/checkpoints.sqlite`). A **`thread_id` identifies one conversation**. The checkpointer saves that conversation's messages under it. I store it internally as `user_id:thread_id`, so two users with the same thread name do not collide.
- **User memory:** table `user_prefs` in `local-storage/user_memory.sqlite`, keyed by **`user_id`**, which identifies the person. A thread is one conversation; a user can have many threads, and the preference is shared by all of them.
- The application sets `user_id` and `thread_id` in the run configuration. The model cannot choose whose data is loaded. The preference is learned from the message when the model calls `save_user_preference`; it is not hard-coded and not read from `demo_users.json`.
- **Retrieval vs memory.** Looking up Wi-Fi instructions is retrieval: it reads a shared reference file (`helpdesk.json`) that is the same for every user and was written before the conversation. Recalling the chosen language is memory: it is something this user said, saved by the application and different for each user.

| Situation | Command used | Log file | What happened |
| --- | --- | --- | --- |
| Refer to an earlier message | `python run_scenarios.py S10` | `outputs/scenarios/S10.json` | Second message "Which steps did I already try?" was answered with no tool call: enabling Wi-Fi, forgetting the network, reconnecting. Conversation memory read: [ВСТАВЬТЕ `conversation_messages_read` of the 2nd event]. |
| Close, restart and resume | `python run_scenarios.py S11` | `outputs/scenarios/S11.json` | Two segments with different `process_id`, i.e. a real restart on the same storage. After it, the assistant (in Kazakh) recalled the Wi-Fi problem and the steps, with `tools: []` and nodes `load_user_memory → agent`. |
| Same user, new conversation | `python run_scenarios.py S12` | `outputs/scenarios/S12.json` | Thread `preference-a1`: `user_memory_read = {}`, 0 messages. Thread `preference-a2`, after a restart: `user_memory_read = {'language': 'Kazakh'}`, `conversation_messages_read = 0`. It replied in Kazakh and said Kazakh was requested, so the preference came from user memory, not from replayed history. |
| Different user | `python run_scenarios.py S13` | `outputs/scenarios/S13.json` | `demo-user-b` asked about a language or previous problem and got "No. In this conversation, you haven't specified a preferred language or mentioned a previous problem." Reply in English, no Kazakh. |

## Part 4 — Running and checking my work

Setup, package versions (`requirements.txt`, from `pip freeze`), Python 3.12.1, memory locations and reset are in `README.md`. CI: `.github/workflows/tests.yml`. All 19 tests pass locally and use a fake model (`tests/fakes.py`, `ScriptedModel`); only `run_scenarios.py` and `helpdesk.py` call the real model.

| Test | What it would catch |
|---|---|
| `test_original_graph_routes` (4 cases) | Wrong rule order, case-sensitive matching, wrong help node |
| `test_changed_graph_asks_for_clarification_only_on_two_topics` | `clarify_problem` not wired, or triggered by one-topic messages |
| `test_find_instructions` | Wrong topic mapping, lost instruction id, bad unknown-topic error |
| `test_status_snapshots` (4 cases) | Wrong snapshot, `unknown` treated as operating, password not mapped to `account_recovery` |
| `test_status_errors` | Crash on unknown snapshot or service |
| `test_ticket_draft_is_saved` | Ticket not saved, template fields missing, wrong reference id |
| `test_ticket_missing_details_and_secrets` | Tickets with missing details, passwords stored in a ticket |
| `test_preference_tool` | Preference not stored, unsupported key accepted |
| `test_tool_result_changes_what_the_agent_does` (3 snapshots) | Tool result not returned to the model; snapshot ignored |
| `test_loop_limit_stops_and_keeps_history_valid` | Endless loop; unanswered tool calls breaking the next turn |
| `test_memory_survives_restart_and_stays_separate` | State lost after closing, memory shared between users or threads |

## Choices and limitations

**Storage.** 
SQLite for both the checkpointer (supplied package) and user preferences: local, no server, survives 
restarts, simple to reset. Separate files keep conversation memory and user memory apart. 
`langchain-openai` with OpenAI, because HW4 already used this model.

**What still does not work reliably:**
- **S08:** SCENARIOS.md expects an offer of a draft ticket saying the status could not be checked. My assistant refused the ticket and explained, but did not make that offer. [ВСТАВЬТЕ: whether you changed the prompt]
- **Path in the reply text:** in S06 the model wrote `local-storage\ tickets\ TCK-...json` with extra spaces. The real file path in `ticket_files` and in the log is correct. [ВСТАВЬТЕ if you fixed it with `as_posix()`]
- **Unneeded tool calls:** in S07 and S08 the model also called `find_instructions`; it did not affect the answer.
- **Model-dependent behaviour:** whether a preference is saved or a ticket is prepared depends on the model's choices, which can vary between runs. Tests with the fake model cover the code, not the real model's judgement.
- **No authentication:** `user_id` is supplied by the caller. The model cannot change it, but a real system would need login.
- The saved Kazakh replies were not checked by a Kazakh speaker.

## Supplied scenarios — my actual results

| Scenario | Command | Log file | What happened / what I changed |
| --- | --- | --- | --- |
| S01 | `python run_scenarios.py S01` | `outputs/scenarios/S01.json` | `read_request → wifi_help`. As predicted. |
| S02 | `... S02` | `S02.json` | `read_request → password_help`; upper case ignored. |
| S03 | `... S03` | `S03.json` | `read_request → other_help`; asks Wi-Fi or password. |
| S04 | `... S04` | `S04.json` | Original graph: `wifi_help`; the password topic was ignored. |
| S05 | `... S05` | `S05.json` | Changed graph: `clarify_problem` asks which problem first. |
| S06 | `... S06` | `S06.json` | Instructions via `find_instructions`; then status `operational` and ticket `TCK-5b0d2c86` with only the user's steps. |
| S07 | `... S07` | `S07.json` | Status `outage`; no ticket; no repair time. |
| S08 | `... S08` | `S08.json` | Status `unknown`; no ticket; did not offer the draft (see limitations). |
| S09 | `... S09` | `S09.json` | First message: asked for problem and steps (no tools). Second: ticket `TCK-66242c68` from those details; status stated as operational. |
| S10 | `... S10` | `S10.json` | First reply gave the next guide steps and offered a status check, with no ticket. Second recalled the steps from the conversation. This was fixed from an earlier run where the model made an unrequested ticket; I changed the system prompt. |
| S11 | `... S11` | `S11.json` | Preference saved; after a real process restart the problem and steps were recalled. |
| S12 | `... S12` | `S12.json` | New thread read `{'language': 'Kazakh'}` from user memory with 0 conversation messages. |
| S13 | `... S13` | `S13.json` | User B saw no data from user A. |
| S14 | `... S14` | `S14.json` | Looked up `account_recovery` (not Wi-Fi): outage, no repair time. |

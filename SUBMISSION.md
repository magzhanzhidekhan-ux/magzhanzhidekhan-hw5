# HW5 — My LangGraph helpdesk

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

**Both topics in one message.** "My Wi-Fi password does not work." contains "wi-fi" and "password". Rule 1 (Wi-Fi) matches first, so the request goes to `wifi_help`. The user may actually need password help, and the graph gives no sign of this problem.

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

TODO: draw the model/tool loop. Answer the four questions in the brief. Record the model and provider, direct calls to each tool, and one actual run that uses multiple tools. Explain the loop limit.

## Part 3 — Memory

TODO: explain conversation state, thread_id, user identifier, user preference storage, and retrieval from helpdesk.json.

| Situation | Command used | Log file | What happened |
| --- | --- | --- | --- |
| Refer to an earlier message | | | |
| Close, restart and resume | | | |
| Same user, new conversation | | | |
| Different user | | | |

## Part 4 — Running and checking my work

TODO: point to the README setup steps, package versions, memory-reset instructions, tests and GitHub Actions workflow. Explain which mistake each test catches and which runs use a fake model.

## Choices and limitations

TODO: explain the storage and libraries I chose, why they fit this task, and what still does not work reliably.

## Supplied scenarios — my actual results

| Scenario | Command or manual steps | Log file | What happened / what I changed |
| --- | --- | --- | --- |
| S01 — Simple Wi-Fi route | | | |
| S02 — Case-insensitive password route | | | |
| S03 — Unsupported request | | | |
| S04 — Two topics before the graph change | | | |
| S05 — Two topics after adding clarification | | | |
| S06 — Instructions then local ticket | | | |
| S07 — The same request during a Wi-Fi outage | | | |
| S08 — Status source unavailable | | | |
| S09 — Missing ticket details | | | |
| S10 — Use the current conversation | | | |
| S11 — Persist and recall after restart | | | |
| S12 — Preference across threads without replay | | | |
| S13 — Do not share memory between users | | | |
| S14 — Password recovery outage | | | |

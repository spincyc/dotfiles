---
protocol: relay-v5
run: <UTC-YYYY-MM-DD>-<nn>
turn: <nnn, the same number as the claim>
role: executor
agent: <executor agent implementation>
branch: <branch>
base: <40-character sha of HEAD after the final sync>
answers: .agent/runs/<run>/<nnn-1>-brief.md
---

status: <complete | partial | blocked | failed>
work: <branch>@<40-character sha read after the final sync, or none>
needs: <the exact missing input, authority, or capability. Required for
partial, blocked, and failed; delete this line for complete.>

Files touched, by intent:
- `<path>` — <why it changed>

Verification:
- `<command>` — <outcome>
- `<command>` — skipped, <reason>

Decisions and deviations: <what departed from the brief, and why; none if
nothing did>

Open questions: <what the planner must settle>
Suggested next step: <the smallest useful next turn, or close the run>

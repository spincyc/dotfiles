---
protocol: relay-v6
run: <UTC-YYYY-MM-DD>-<nn>
turn: <nnn>
role: planner
agent: <planner agent implementation>
subagents: <nonnegative integer, excluding the primary executor>
branch: <branch>
base: <40-character sha of the origin/<branch> tip this was committed on>
abandons: <.agent/runs/<run>/<nnn>-brief.md; delete this line unless this brief supersedes an outstanding turn>
---

Objective: <the user-visible outcome, not a list of edits>

Scope boundary: <what the executor owns, and what it must not touch>

Acceptance criteria: <checkable conditions, not aspirations>

Verification: <the exact smallest command(s) that prove the work>

Delegation plan: <why the subagents count above is optimal; when nonzero,
the distinct parallel-safe lanes and the resource each owns exclusively>

Context: <the paths, constraints, and prior decisions that bind this work.
Name each earlier turn by exact repository-relative path and full sha. Every
entry must bind the work; context that only explains the plan does not
belong here.>

When blocked: <what to report, and what not to improvise>

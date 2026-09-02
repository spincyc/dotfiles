---
protocol: relay-v6
run: <UTC-YYYY-MM-DD>-<nn>
turn: <nnn>
role: planner
agent: <planner agent implementation>
branch: <branch>
base: <40-character sha of the origin/<branch> tip this was committed on>
---

Outcome: <what the run achieved, and what it did not>

Commits: <the work commits this run produced, by full sha>

Turns: <each turn of this run by exact repository-relative path, in
lexicographic order, with its status>

For a later session: <what someone picking this up must know, including any
abandoned turn and any unrecorded work found on the branch>

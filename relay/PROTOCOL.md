# Agent relay protocol

Version `relay-v1`.

A planning agent with git write access and no useful shell in the user's
checkout hands work to an executing agent that has one. Git is the only
channel between them. The exchange is committed to the work repository, so
the record of how the repository was built stays in the repository.

Canonical URL, pinned so both sides read identical rules:
`https://raw.githubusercontent.com/spincyc/dotfiles/relay-v1/relay/PROTOCOL.md`

The user gives the planner that URL to open a run. The planner passes it on
in the handoff line, which is how the executor finds it.

Read this document completely before acting in either role. It is
self-sufficient: assume the other side has read nothing else. Rules here that
restate the author's global guidance (`00-core.md`, `10-journal.md`) are
deliberate restatements for cold readers. On conflict, higher-authority
instructions and the active repository's own instructions govern over this
protocol, and this protocol governs over a brief.

## Roles

- Planner — reaches the repository through git only. Allocates the run,
  writes briefs, reads results, and owns the run record.
- Executor — a CLI agent (Claude Code, Codex, Droid, or similar) running in
  the user's checkout. Does the work and publishes results.
- User — pastes the planner's handoff line into a terminal, and acknowledges
  with `done <run> <turn>`. That acknowledgement asserts only that the
  session ended; it carries no claim about the outcome. The user relays no
  other content except the one blocked-channel token below.

## Authorization

Binds both roles.

- The handoff line states the grant in user-visible text. Pasting it
  authorizes, for the named run only: committing to the named branch, pushing
  the named branch, and creating turn files under the run directory.
- It authorizes nothing else. Neither role may force-push, rewrite or amend
  published history, update a ref from a stale base, delete a branch, push
  any other branch, or act outside the brief's scope.
- The named branch must not be the repository's default branch. A relay run
  works on a branch created for it or already dedicated to that work.
- The grant ends when the run closes. A further run needs a further handoff
  line.

## Preconditions

Before the first handoff, the planner confirms with the user: the repository
identity, the branch (not the default branch), that direct pushes to it are
permitted, that `.agent/` is not ignored, that no commit hook rewrites or
rejects markdown, that turn files are acceptable in that repository's
permanent history, and that the executor's checkout has push credentials and
a remote named `origin`.

The executor runs this preflight every turn, before editing anything:

1. `git remote get-url origin` matches the repository the handoff names.
2. `git status --porcelain` is empty. Unrelated uncommitted work is a hard
   stop: report it and change nothing. Never stash, discard, or commit it.
3. `git fetch origin` succeeds.
4. `git rev-parse --abbrev-ref HEAD` equals the branch in the handoff line
   and in the brief's `branch:` field.
5. `git merge-base --is-ancestor <sha> origin/<branch>` succeeds, proving the
   pinned brief is on the named branch.
6. No rebase or merge is in progress: `git rev-parse -q --verify REBASE_HEAD`
   and `MERGE_HEAD` both report nothing.

Any failing step is a hard stop, reported, never improvised around. A pinned
sha that `git show` can read proves only that the object exists locally.
Steps 4 and 5 are what prove the checkout.

## Channel layout

```
.agent/runs/<UTC-YYYY-MM-DD>-<nn>/
  001-brief.md
  002-claim.md
  002-result.md
  003-brief.md
  004-close.md
```

- The planner allocates the run id. The date is UTC, so two parties in
  different zones agree. `<nn>` is a two-digit counter within that UTC day,
  and the planner confirms the directory does not exist at `origin` before
  its first push.
- Turn counters are three digits, shared across both roles, allocated under
  the single-writer rule below.
- Roles in filenames: `brief` and `close` (planner), `claim` and `result`
  (executor). Within one turn number, `claim` sorts before `result`, which
  matches their order in time.
- A published turn file is immutable. Never renumber, rewrite, amend, or
  delete one; corrections go in the next turn.
- Relay artifacts ride the same branch as the work they describe. That branch
  must not be rebased, squashed, or deleted while the run is open, because
  every pinned sha in the run refers to it.
- Squash-merge preserves every turn file in the merged tree, so commit
  *messages* are not load-bearing. Commit *shas* are, which is why the branch
  is frozen against rewriting for the life of the run.

## Turn file format

Every turn file opens with at least these fields, in this order, delimited as
front matter:

```
---
protocol: relay-v1
run: 2026-08-31-01
turn: 002
role: executor
agent: claude-code
branch: feat/relay
base: 4cf777c
answers: .agent/runs/2026-08-31-01/001-brief.md
---
```

- `base` is the commit the turn was written against, read after the turn's
  final rebase.
- `answers` is required on a result and names the brief it responds to.
  `abandons` is optional on a brief and names a turn it supersedes.
- `agent` names the concrete model or CLI, not the role.
- If the two sides' `protocol:` values differ, the executor stops with
  `status: blocked` and `needs: protocol <version>`. Two parties on different
  rule sets must not proceed.
- Every path written anywhere in a turn file is repository-relative. Never
  absolute, never host-identifying.

A brief body states, in order:

- Objective — the user-visible outcome, not a list of edits.
- Scope boundary — what the executor owns and what it must not touch.
- Acceptance criteria — checkable conditions, not aspirations.
- Verification — the exact smallest command(s) that prove the work.
- Context — the paths, constraints, and prior decisions the executor needs,
  each earlier turn named by exact path and commit.
- When blocked — what to report and what not to improvise.

A result body states, in order:

- `status:` — one of `complete`, `partial`, `blocked`, `failed`.
- `work:` — `<branch>@<sha>` for the work commits, read after the final
  rebase, or `none`.
- `needs:` — the exact missing input, authority, or capability. Required for
  `partial`, `blocked`, and `failed`; omitted for `complete`.
- Files touched, grouped by intent.
- Verification — each check run and its outcome, and each relevant check
  skipped with the reason. Never report an unrun check as passing.
- Decisions and deviations from the brief, with reasons.
- Open questions and the suggested next step.

## Handoff line

The planner emits one physical line, containing no newline character, for the
user to paste. It begins with `#` so that a paste into a shell prompt is
inert as a comment rather than a half-executed command.

```
# relay relay-v1 | claude | clean | run 2026-08-31-01 | turn 001 | repo spincyc/dotfiles | branch feat/relay | pasting this authorizes commits and pushes to feat/relay for this run | agent prompt, not a shell command: git fetch origin, then git show 4cf777c:.agent/runs/2026-08-31-01/001-brief.md, read that brief and https://raw.githubusercontent.com/spincyc/dotfiles/relay-v1/relay/PROTOCOL.md, then execute
```

- Substitute a real sha. Never emit a literal `<sha>` placeholder.
- Keep it ASCII. Dashes and quotes that survive one clipboard may not survive
  the next.
- Never emit a shell command with the brief or prompt embedded as a quoted
  argument. Generated text inside shell quoting is a break-out risk.
- `clean` means start a fresh session; `continue` means paste into the live
  session already holding this run. That field addresses the user, not a
  parser. Every brief is self-sufficient at its pinned commit either way, so
  `continue` is a cost hint only. An executor that finds itself missing
  context the brief assumed reports `blocked` with `needs:` rather than
  reading around for it.

## Context boundary

Run directories accumulate. Reading them by default spends context on history
nobody asked for and lets superseded decisions leak into current work. The
boundary is asymmetric, because the two roles need different views.

- The planner may list `.agent/runs/` and its own run directory, and may read
  any turn file within its own run. It may not list or read any other run
  directory.
- The executor reads the pinned brief and nothing else from the run tree. It
  derives its turn number from the handoff line rather than by enumeration.
- Checking whether a path exists is not reading it. Both roles may test for a
  specific known filename.
- A brief that depends on an earlier turn names it by exact path and commit.
  It never says "review the previous runs" or leaves the executor to work out
  which history is relevant.
- A `continue` session already holds its earlier turns in context, which is
  not a reason to re-read them from disk.
- When earlier context turns out to be genuinely required, ask for the exact
  path instead of reading around to find it.

## Turn allocation and the single-writer rule

Both roles allocate from one counter, so allocation needs a rule rather than
a hope. At most one turn may be outstanding per run.

- The planner may not allocate a new turn number until either the expected
  result exists at `origin`, or it has published a brief whose `abandons:`
  field names the outstanding turn, which burns that number.
- The executor claims its number before doing any work, by pushing
  `<nnn>-claim.md` carrying the front matter above. A rejected or conflicting
  claim push means the number is already claimed: report the replay and stop
  without redoing the work.
- Lexicographic filename order is allocation order, and under this rule
  allocation order is publication order. It is not otherwise a chronological
  guarantee.
- Three digits allow 999 turns per run. Do not widen the field mid-run;
  `1000-` would sort before `002-`.

## Planner rules

- Confirm the preconditions above before the first handoff.
- Allocate the run id, then hold this order: re-read the `origin/<branch>`
  tip, create the run directory, write the brief, commit on that tip, push,
  and only then emit the handoff line. A handoff line pointing at an unpushed
  commit is a broken handoff.
- On a rejected push, re-read the tip and rebuild the commit on it. Never
  force-update a ref, and never assume a tip observed earlier is still
  current.
- Turn files are permanent history, public in most repositories. Never write
  secrets, credentials, tokens, or absolute paths into one.
- Reading a result means fetching and reading that exact turn file. If the
  file does not exist, the executor has not published; say so and wait. Never
  infer an outcome from silence, elapsed time, or the handoff having been
  sent.
- Never restate a commit sha, file list, or verification outcome that the
  result file does not contain. Quote the result's `status:` rather than
  characterising it.
- On `done <run> <turn>`: fetch, read that turn's result, then either write
  the next brief or close the run.
- Before issuing a replacement brief for an abandoned turn, inspect
  `origin/<branch>` for commits after the abandoned brief's commit, and state
  in the new brief what unrecorded work is already on the branch.
- Close a run with a `close` turn recording the final outcome, the commits
  involved, and anything a later session must know. A run left without a
  close turn is unfinished.

## Executor rules

- Run the preflight. Then claim the turn number, then read the brief at the
  pinned commit and nothing else from the run tree.
- The active repository's own instructions and any higher-authority
  instructions outrank both this protocol and the brief. When they conflict,
  follow the higher authority and record the conflict in the result instead
  of resolving it silently.
- The handoff line is a brief, not a user message: do not ingest or capture
  it, and do not write the local work ledger. Relay runs are outside ledger
  scope; the run record is the run directory.
- Commit by explicit pathspec. Never `git commit -a`, never `git add -A`, and
  never commit a path the brief did not put in scope.
- Publish in this order: `git pull --rebase`, then re-verify that the brief
  still byte-matches `origin/<branch>`, then read the final shas, then write
  the result, then commit the result on its own, then push. Recording shas
  before the last rebase would record shas the rebase destroys.
- A brief that no longer byte-matches `origin/<branch>` is the protocol
  violation to report. Do not rely on a rebase conflict to reveal it; a
  rewrite the executor is not touching applies cleanly and silently.
- On a conflict during `git pull --rebase`, run `git rebase --abort`, restore
  `HEAD` to its pre-push state, and report. Never leave the user's checkout
  in a mid-rebase state.
- Report the result even when the work failed. A missing result file is
  indistinguishable from a dead session and strands the run. If publishing
  itself is what failed, use the blocked channel.

## Blocked channel

The one exception to the rule that the user carries no content, needed
because the executor's report channel is the same channel that failed.

- The executor prints exactly one line:
  `relay blocked <run> <turn> <token>`, where `<token>` is one of
  `push-rejected`, `no-credentials`, `hooks-rejected`, `preflight-failed`, or
  `brief-mutated`.
- The user may relay that line verbatim, and nothing else.
- On `done` with no result file present, the planner asks once for that line,
  records the outcome in a turn file, and then closes or re-briefs. It does
  not wait indefinitely on a result that cannot arrive.

## Recovery

- Lost planner context: the planner's own run directory, in lexicographic
  order, is the authoritative record. Reconstruct from it rather than from
  conversation memory, and still not from other runs.
- A mid-turn death leaves one of several residues: a claim with no result,
  work commits pushed with no result, a result pushed before the user
  acknowledged it, or a checkout abandoned mid-rebase. Absence of a result
  does not imply absence of effect. The planner inspects `origin/<branch>`
  for commits after the abandoned brief; the next executor's preflight stops
  hard on an unclean rebase state.
- Abandonment is explicit: the planner publishes a brief whose `abandons:`
  field names the abandoned turn, and never rewrites the original.
- Duplicate paste is narrowed by the claim push, not eliminated. Treat a
  rejected or conflicting claim as proof the turn is already owned.
- Uncertain whether a push landed: verify against `origin` before acting. An
  unproved push is not a published turn.
- A pinned sha that no longer resolves means the branch was rewritten while
  the run was open. Stop and report; do not guess at a replacement.

# Agent relay protocol

Version `relay-v5`.

A planning agent with git write access and no useful shell in the user's
checkout hands work to an executing agent that has one. Git is the only
channel between them. The exchange is committed to the work repository, so
the record of how the repository was built stays in the repository.

Canonical URL, pinned so both sides read identical rules:
`https://raw.githubusercontent.com/spincyc/dotfiles/relay-v5/relay/PROTOCOL.md`

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
identity, the executor CLI, model, and reasoning level to launch, the branch
(not the default branch), that direct pushes to it are permitted, that
`.agent/` is not ignored, that no commit hook rewrites or rejects markdown,
that turn files are acceptable in that repository's permanent history, and
that the executor's checkout has push credentials and a remote named `origin`.
When the workspace helper can select a clone branch, select the handoff branch
at creation time; that is the preferred bootstrap and makes the branch switch
below unnecessary.

## Workspace initialization

A fresh executor checkout may start on the repository's default branch. A
branch mismatch at that point is not yet a preflight failure.
Before formal preflight, the executor may switch only to the branch named in
the handoff. This happens before claiming the turn and before making any edit,
as follows:

1. `git remote get-url origin` matches the repository the handoff names.
2. `git status --porcelain` is empty, and the `REBASE_HEAD` and `MERGE_HEAD`
   checks from formal preflight both report nothing. Otherwise stop without
   stashing, discarding, committing, or changing branches.
3. `git fetch origin` succeeds, and `refs/remotes/origin/<branch>` exists.
4. If `HEAD` already names `<branch>`, make no branch change and continue to
   formal preflight.
5. Otherwise, if no local `<branch>` exists, run
   `git switch --track origin/<branch>`. If it does exist, require
   `git rev-parse --abbrev-ref <branch>@{upstream}` to report
   `origin/<branch>`, then run `git switch <branch>`. An existing branch with
   another or no upstream is a hard stop; do not retarget, reset, or recreate
   it.

This is the only branch change the protocol permits. It does not authorize
switching after a claim or after work has begun. Any initialization failure is
reported as `preflight-failed`; otherwise the executor runs the complete
preflight below from the target branch.

The executor runs this preflight every turn, before editing anything:

1. `git remote get-url origin` matches the repository the handoff names.
2. `git status --porcelain` is empty. Unrelated uncommitted work is a hard
   stop: report it and change nothing. Never stash, discard, or commit it.
3. `git fetch origin` succeeds.
4. `git rev-parse --abbrev-ref HEAD` equals the branch in the handoff line.
5. `git merge-base --is-ancestor <sha> origin/<branch>` succeeds, proving the
   pinned brief is on the named branch.
6. No rebase or merge is in progress: `git rev-parse -q --verify REBASE_HEAD`
   and `MERGE_HEAD` both report nothing.

Any failing step is a hard stop, reported, never improvised around. A pinned
sha that `git show` can read proves only that the object exists locally.
Steps 4 and 5 are what prove the checkout. Branch mismatch remains a hard stop
after workspace initialization; only the clean initialization above may cure
it.

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
- Relay artifacts ride the same branch as the work they describe. Its
  published commits must not be rebased, squashed, or deleted while the run
  is open, because every pinned sha in the run refers to them. The final sync
  below replays unpublished commits only, which is why it stays inside this
  rule.
- Squash-merge preserves every turn file in the merged tree, so commit
  *messages* are not load-bearing. Commit *shas* are, which is why the branch
  is frozen against rewriting for the life of the run.

## Turn file format

Every turn file opens with at least these fields, in this order, delimited as
front matter:

```
---
protocol: relay-v5
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
  final sync.
- `answers` is required on a result and names the brief it responds to.
  `abandons` is optional on a brief and names a turn it supersedes.
- `agent` names the concrete agent implementation writing the turn, not its
  role. The handoff separately names the executor CLI, model, and reasoning
  level the user should launch.
- `subagents` is required on a brief. It is the planner's optimal number of
  delegated agents for that turn, written as a nonnegative integer and
  excluding the primary executor. It immediately follows `agent` in brief
  front matter and is omitted from claims, results, and close turns.
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
- Delegation plan — why the `subagents` count is optimal and, when nonzero,
  the distinct parallel-safe lanes they should own.
- Context — the paths, constraints, and prior decisions the executor needs,
  each earlier turn named by exact path and commit.
- When blocked — what to report and what not to improvise.

A result body states, in order:

- `status:` — one of `complete`, `partial`, `blocked`, `failed`.
- `work:` — `<branch>@<sha>` for the work commits, read after the final
  sync, or `none`.
- `needs:` — the exact missing input, authority, or capability. Required for
  `partial`, `blocked`, and `failed`; omitted for `complete`.
- Files touched, grouped by intent.
- Verification — each check run and its outcome, and each relevant check
  skipped with the reason. Never report an unrun check as passing.
- Decisions and deviations from the brief, with reasons.
- Open questions and the suggested next step.

## Seed briefs

A brief that opens a run for new work (a new project, feature, or objective
not continuing a prior run) is a seed brief. The planning conversation behind
it is exploration the repository must never see; the seed is the only thing
that crosses. It is the run's foundation, not a record of the planning that
produced it.

- Sanity-check the request first: the objective is a user-visible outcome,
  the scope is bounded, and acceptance criteria can be checkable. If the
  request itself is not yet coherent, resolve that with the user before
  opening a run.
- Generate the seed from the request alone, then check the result as if the
  planning conversation had never happened. Rebuild from scratch rather than
  editing down; editing down leaves residue.
- The seed carries no abandoned ideas, no declined paths, no ledger of
  alternatives considered. It does not refute what was rejected; it stands
  on what survived. It brings in only what is necessary, and never justifies
  a choice against the original conversation.
- Every context entry must bind the executor's work: an exact path, a
  constraint, or a binding decision. Context exists to make the work
  correct, not to explain the plan.
- Before publishing, audit the draft against the planning conversation for
  leaked exploration. If any sentence only makes sense with that
  conversation in hand, the seed is not clean yet.

Seed discipline and `abandons:` never mix: `abandons:` operates on published
turns mid-run, seed discipline governs the planner's own unpublished pre-run
planning, and a seed brief carries no `abandons:` field.

## Handoff line

The planner emits one physical line, containing no newline character, for the
user to paste. It begins with `#` so that a paste into a shell prompt is
inert as a comment rather than a half-executed command.

```
# relay relay-v5 | agent claude | model opus | reasoning high | state clean | run 2026-08-31-01 | turn 001 | repo spincyc/dotfiles | branch feat/relay | pasting this authorizes commits and pushes to feat/relay for this run | agent prompt, not a shell command: read https://raw.githubusercontent.com/spincyc/dotfiles/relay-v5/relay/PROTOCOL.md, initialize the clean checkout on feat/relay as it permits, run preflight, then git show 4cf777c:.agent/runs/2026-08-31-01/001-brief.md, claim the turn, and execute that brief
```

Presentation requirement:

- The handoff itself is exactly one physical line beginning with `#`.
- In user-visible chat, render that line inside a fenced code block so
  Markdown does not interpret `#` as a heading.
- The fenced code block contains only the handoff line: no prompt marker, no
  wrapping text, no second line, and no shell-language annotation.
- Explanatory prose, if any, must appear outside the fenced block.

- Substitute a real sha. Never emit a literal `<sha>` placeholder.
- Keep it ASCII. Dashes and quotes that survive one clipboard may not survive
  the next.
- Never emit a shell command with the brief or prompt embedded as a quoted
  argument. Generated text inside shell quoting is a break-out risk.
- The `<agent>` field is required and names the executor CLI to launch
  (`claude`, `codex`, `droid`, or similar), settled with the user in the
  preconditions.
- The `<model>` field is required and names the model identifier or configured
  alias that the named CLI accepts, settled with the user in the preconditions.
- The `<reasoning>` field is required and names the reasoning or effort level
  that the named CLI accepts, settled with the user in the preconditions.
- The `<state>` field is required and is one of `clean` or `resume`: `clean`
  means start a fresh session; `resume` means paste into the live session
  already holding this run. That field addresses the user, not a parser.
  Every brief is self-sufficient at its pinned commit either way, so
  `resume` is a cost hint only. An executor that finds itself missing
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
- A `resume` session already holds its earlier turns in context, which is
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
- A handoff line that omits the `agent`, `model`, `reasoning`, or `state`
  field is invalid; re-emit it. Never launch the user toward a session
  without all four.
- A brief that omits `subagents`, gives a range instead of one nonnegative
  integer, or does not explain the count in its Delegation plan is invalid;
  correct it before publishing.
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

- Read the protocol, initialize the workspace when necessary, and run the
  preflight. Then read the brief at the pinned commit and nothing else from
  the run tree, verify its `branch:` matches the handoff, claim the turn
  number, and execute the brief. Reading is not execution and may precede the
  claim; no edit or other brief work may.
- The active repository's own instructions and any higher-authority
  instructions outrank both this protocol and the brief. When they conflict,
  follow the higher authority and record the conflict in the result instead
  of resolving it silently.
- The handoff line is a brief, not a user message: do not ingest or capture
  it, and do not write the local work ledger. Relay runs are outside ledger
  scope; the run record is the run directory.
- Treat `subagents` as the planner's scheduling recommendation, subject to
  higher-authority instructions, available capacity, and actual parallel-safe
  work. Record any deviation and its reason in the result.
- Commit by explicit pathspec. Never `git commit -a`, never `git add -A`, and
  never commit a path the brief did not put in scope.
- Publish in this order: the final sync below, then re-verify that the brief
  still byte-matches `origin/<branch>`, then read the final shas, then write
  the result, then commit the result on its own, then push. Recording shas
  before the sync would record shas a rebase within it destroys.
- A brief that no longer byte-matches `origin/<branch>` is the protocol
  violation to report. Do not rely on a rebase conflict to reveal it; a
  rewrite the executor is not touching applies cleanly and silently.
- Report the result even when the work failed. A missing result file is
  indistinguishable from a dead session and strands the run. If publishing
  itself is what failed, use the blocked channel.

## Final sync

Publishing reconciles with `origin` without destroying history. A rebase is a
rewrite, so the protocol asks for one only when the branch has actually
diverged, and never over commits `origin` already carries. This procedure
replaces the mandatory `git pull --rebase` of earlier protocol versions: that
command rebases unconditionally, so it flattens deliberate merge ancestry and
rewrites work the branch was already carrying correctly. Do not use it in a
relay run.

With the work committed and the tree otherwise clean:

1. Record the pre-sync `HEAD` with `git rev-parse HEAD`.
2. `git fetch origin`.
3. Run `git merge-base --is-ancestor origin/<branch> HEAD`. If it succeeds,
   the branch is already synchronized: do not rebase. Its merge ancestry is
   intentional and must be preserved, and the push that follows is a
   fast-forward.
4. Otherwise the branch has diverged, and only the unpublished range is
   replayed. If `git rev-list --merges HEAD ^origin/<branch>` names any
   commit, that range carries intentional merges: use
   `git rebase --rebase-merges origin/<branch>`. If it names none, the
   unpublished history is linear and a plain `git rebase origin/<branch>` is
   correct.
5. On any conflict, run `git rebase --abort`, confirm `HEAD` is back at the
   sha from step 1, and report. Never leave the user's checkout in a
   mid-rebase state, and never resolve a conflict in another turn's commits
   to get a push through.

Never rewrite a commit already published to `origin`. Rebasing onto
`origin/<branch>` touches only the unpublished range, which is what keeps
that rule and the step 3 exemption consistent.

`--rebase-merges` recreates merges instead of replaying their recorded
result, so a rebuilt merge can differ from the one the executor verified.
After any step 4 rebase, re-run the brief's verification before writing the
result; checks that ran against the pre-sync tree no longer prove the tree
being pushed.

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
  conversation memory, and still not from other runs. A clean seed brief is
  what makes this reconstruction work: it is sufficient to restart the run
  without the planning conversation that produced it.
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

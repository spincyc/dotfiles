# Durable journal workflow

This document exclusively owns journal-conditioned behavior in this guidance
set.

## Ownership and discovery

Resolve the active repository from the user's task and current working tree,
not from this guidance file's path or symlink target. A journal belongs only
to the repository whose root directly contains its `.journal/` directory.

- Read and write only the active repository's `.journal/`.
- Run journal helpers from that repository root.
- Keep its locks, sequences, task IDs, decisions, feedback, and timeline
  isolated from every other repository.
- Never use `~/git/dotfiles/.journal/` as global or fallback state. Use it only
  when the active repository is the dotfiles checkout itself.
- If the active repository has no `.journal/README.md`, do not search another
  repository for one or silently create a journal. Follow other applicable
  instructions and continue unless the user authorizes initialization.

## Durable repository workflow

When the active repository contains its own `.journal/README.md`, read that
file before repository work and:

1. Verify the repository, branch, HEAD, remotes, and working tree.
2. Create an agent-instance UUID. Read journal state, queue, active tasks,
   relevant history, and leases.
3. Durably classify and enrich each user message before acting. Queue new work;
   do not interrupt active work unless explicitly directed or continuation is
   unsafe or invalid.
4. Preserve history with immutable events and decisions. Use journal helpers
   so every record receives UTC occurrence and recording times plus a
   lock-assigned sequence. Supersede explicitly; never silently rewrite.
5. Re-read durable state at recovery and scheduling boundaries, before
   checkpoints, after unexpected Git changes, and before completion or yield.
6. Drain the queue. Do not yield, end the session, or report final completion
   while any task is runnable. After each completion, rebuild and reassess the
   queue, select the next runnable task, and continue it in the same session.
7. Yield only when no task is runnable, progress requires unavailable
   authority or an external-state change, or the environment actually
   prevents further execution or continuation. A blocked task does not
   justify yielding while another task is runnable.
8. Scope unexplained artifacts narrowly. Preserve them and continue every
   independent queue lane that cannot overlap them.
9. Before blocking on required user input, record each independently
   answerable requirement durably with the task. Preserve stable IDs and
   pending-to-complete history, and keep all pending requirements
   repository-wide extractable.
10. Commit journal records on the active non-main topic branch in regular,
    coherent checkpoints adjacent to their attributable implementation
    commits. Keep implementation commits free of `.journal/` changes so they
    can be promoted independently. Do not push, change branches, merge,
    rebase, or rewrite history without authority.

When journal machinery is unclear or defective, publish an immutable feedback
report in its owning repository with `journal.py feedback submit`. Do not
repair protocol state opportunistically. A leased maintenance task in that
repository reviews feedback and records incorporation through an immutable
decision.

From the active repository root, run
`python3 .journal/bin/journal.py validate` before journal commits.

## Checkpoints and prose

- Never create a parallel checkout, worktree, clone, sibling directory, or
  alternate journal directory for journal isolation. Use one working tree and
  the active repository's one `.journal/` path.
- Before the first journal mutation for new work, leave `main` by creating or
  switching to an authorized non-main topic branch in the same working tree.
  Never commit new journal state on `main`.
- Commit at natural recovery boundaries. Put journal state in branch-local
  journal commits and verified implementation, documentation, tests, or
  migrations in adjacent commits that contain no `.journal/` changes. Each
  commit remains one coherent unit, and the adjacency durably associates the
  operational record with the work without making journal history a
  prerequisite of the implementation commit.
- Never merge or rebase a journal-bearing topic branch into `main`. Promote
  only the journal-free implementation commits by cherry-picking them onto
  `main`, preserving neither the journal commits nor their ancestry. Verify
  the promoted commit and resulting `main` tree contain no topic-branch
  `.journal/` changes.
- Keep the journal-bearing topic branch as the durable operational record
  under the repository's retention policy; it does not require a lingering
  directory or worktree.
- Commit often enough that interruption loses little completed work.
- An interim checkpoint is a continuation boundary, not permission to yield.
  After committing, reread durable state, reassess the queue, and immediately
  resume the next runnable work unless a documented yield condition applies.
- A checkpoint report is only a progress update, even when it names a commit
  or says a coherent unit is complete. Immediately after sending it, reread
  durable state and run `python3 .journal/bin/journal.py yield-check`. If the
  check reports work, continue those tasks in the same turn without waiting
  for acknowledgment. Do not convert the report into a final response.
- Do not mix unrelated work in one commit or create trivial checkpoint noise
  when no coherent unit exists.
- Keep commit subjects imperative and terse. Use a short body only for
  non-obvious rationale, consequences, or required durable trailers.
- Keep code comments terse. Explain only non-obvious intent, constraints, or
  invariants; do not narrate the code.

Explicit persistence language such as `do not stop`, `finish`, or `drain the
queue` reinforces these continuation rules. It does not authorize unrelated,
destructive, unsafe, or externally consequential actions.

## Progress and final responses

- A status or commentary message is a non-terminal progress report, not a
  turn, checkpoint, handoff, or yield boundary. This includes checkpoint
  reports sent immediately after a commit.
- Immediately after sending one, continue pending tool work in the same turn.
  Do not wait for acknowledgment unless user input is genuinely required.
- Pending checkpoints and active queue lanes remain live across progress
  messages until completed, superseded, cancelled, or genuinely blocked.
- If the user asks for status during ongoing work, answer briefly and resume
  unless the user explicitly redirects, pauses, or stops the task.
- Send a self-contained final response only after queue drain or another
  documented yield condition.
- Immediately before any final response, reread durable state and run
  `python3 .journal/bin/journal.py yield-check` from the active repository
  root. A nonzero result prohibits the final response: continue the reported
  tasks in the same turn. Never treat an intended final response, a completed
  lesson or checkpoint, or a prose claim that work will resume as evidence
  that the queue is drained.

## Wrongful-stop correction loop

When the user asks why work stopped and the agent concludes that stopping was
incorrect, treat that conclusion as a discovered guidance or journal-protocol
defect, not merely an explanation or apology.

1. State the concrete cause and the rule or missing safeguard that permitted
   it. Resume all runnable work immediately; diagnosis is not a new boundary.
2. Before final response, submit immutable feedback in the repository that
   owns the defective guidance. Include the evidence, impact, failed rule, and
   a bounded preventative change. Do not silently rewrite protocol while
   unrelated work owns the journal.
3. Route incorporation through that repository's active, leased maintenance
   task, with an immutable decision, review disposition, validation, and
   coherent commit. Reassess the queue and continue independent work while the
   maintenance change is pending.
4. Keep journal ownership strict. The user's active repository journal records
   its work; generic-guidance maintenance uses the generic guidance
   repository's own journal only as a separately scoped task. Never use the
   dotfiles journal as fallback state for another repository.
5. If the owning repository or maintenance path is unavailable, durably
   record the proposed correction in the active repository and mark only that
   maintenance action blocked. Do not claim the recurrence is fixed, and do
   not stop other runnable work.

## Execution windows

- Treat time slices, token or context windows, compaction, and automatic
  continuation boundaries as scheduling boundaries, not blockers or handoffs.
- Before a window ends, commit a coherent checkpoint and durably record the
  exact next action and live work. Then continue automatically in the next
  execution turn without waiting for the user.
- Runnable tasks, fresh corrected artifacts, and live runs remain active
  across windows. Re-read their current state and resume or monitor them.
- Do not report a technical blocker merely because a window ended. An
  environment-forced handoff exists only when further execution cannot run or
  be scheduled.

## Clarifications during work

- Treat a user clarification as durable input inside the continuing queue, not
  as a conversational, turn, handoff, or yield boundary.
- Before affected work continues, classify and record it as an amendment,
  decision, control, information, or question. Update task state and record an
  immutable decision when it consequentially changes policy, scope,
  acceptance criteria, dependencies, or scheduling.
- Reassess affected tasks and the queue, then continue every runnable lane in
  the same turn. A brief acknowledgment does not replace ingestion or work.
- Pause, cancel, block, or supersede work only when the clarification
  explicitly requires it or its content creates a documented blocker.

## Required user feedback

When a task cannot advance without user input and no documented safe
assumption resolves it:

- Before marking the task `blocked`, create one durable user-feedback
  requirement for each independently answerable input. State exactly what the
  user must provide and why it is required. Chat or free-form queue prose is
  not the sole record.
- Keep requirements task-scoped, UUID-identified, lock-published, ordered, and
  machine-readable. Pending and completed requirements remain preserved as
  immutable history; do not delete, reopen, or silently rewrite them.
- Ingest the user's resolving message as an immutable event, then complete
  each satisfied requirement with that event reference and a terse response
  summary. Partial answers complete only the satisfied items; materially new
  questions receive new requirement UUIDs.
- On every user message, reconcile relevant pending requirements, reassess
  affected task status and dependencies, and resume work when possible.
  Pending input blocks only its owning task and dependent work; continue all
  independent runnable lanes.
- Use the active repository's aggregate journal command to retrieve all
  pending user feedback before asking for input or yielding. When this
  protocol's helper is present, run
  `python3 .journal/bin/journal.py user-feedback list`; use `--json` for
  machine-readable repository-wide extraction.

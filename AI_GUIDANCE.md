# Global AI contributor guidance

Canonical personal instructions for AI agents. Tool-specific files must point
here, not duplicate it. Repository-local instructions may add narrower rules.

## Journal ownership

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
  repository for one or silently create a journal. Follow local instructions
  and continue without this workflow unless the user authorizes initialization.

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
   authority or an external-state change, or the environment actually prevents
   further execution or continuation. A blocked task does not justify yielding
   while another task is runnable.
   An unexplained artifact blocks only work that could overlap it; preserve it
   and continue independent queue lanes.
8. Before blocking on required user input, record each independently
   answerable requirement durably with the task. Preserve stable IDs and
   pending-to-complete history, and keep all pending requirements
   repository-wide extractable.
9. Commit journal and attributable implementation locally in regular,
   coherent checkpoints. Do not push, change branches, merge, rebase, or
   rewrite history without authority.

When that repository's journal machinery is unclear or defective, publish an
immutable feedback report there with `journal.py feedback submit`. Do not
repair protocol state opportunistically. A leased maintenance task in the
same repository reviews feedback and records incorporation through an
immutable decision.

From the active repository root, run
`python3 .journal/bin/journal.py validate` before journal commits.

## Checkpoints and prose

- Commit at natural recovery boundaries: one coherent behavior, decision,
  migration, or verified implementation unit with its tests and journal
  records. Commit often enough that interruption loses little completed work.
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

## Progress updates

- A status or commentary message is a non-terminal progress report, not a
  turn, checkpoint, handoff, or yield boundary.
- This includes checkpoint reports sent immediately after a commit.
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

## Sub-agent scheduling

When sub-agent tools are available and delegation is permitted, proactively
use all useful parallel capacity without waiting for the user to repeat the
instruction.

- At initial scheduling and every scheduling boundary, decompose runnable work
  into concrete, bounded, independently executable lanes with distinct
  deliverables. Keep active sub-agents at the lesser of available slots and
  useful parallel-safe lanes.
- Treat a sub-agent finishing, blocking, failing, or revealing more work as an
  immediate scheduling boundary. Collect its result promptly and refill every
  safely usable slot in the same turn while parallelizable work remains.
- Keep the coordinating agent advancing orchestration, integration, or its own
  nonconflicting lane while delegates run. Review and integrate every result;
  do not abandon delegated work.
- Give mutating lanes exclusive ownership of files and mutable resources.
  Prefer read-only delegates for overlapping inspection or review, and
  serialize unresolved dependencies or shared-worktree conflicts. Designate
  one coordinator for integration, commits, pushes, and other repository-wide
  or externally consequential actions.
- Do not manufacture work, fragment indivisible work, create unjustified
  duplicate lanes, or spend more coordination than the delegation can save
  merely to occupy slots.
- Capacity may remain idle only when no additional useful parallel-safe lane
  exists or delegation is unavailable or prohibited. Record the concrete
  constraint in durable task state and reassess it when state changes.

Dependencies, user scope, safety rules, authority, leases, and higher-priority
instructions remain controlling. Delegation never broadens authority.

## Collaboration

Be candid and evidence-oriented. Optimize for the result, not agreement.

- Test proposals for material risks, contradictions, costs, and stronger
  alternatives. State consequential concerns plainly with reasons.
- Do not flatter, reflexively agree, over-reassure, manufacture objections, or
  perform opposition.
- Distinguish fact, inference, uncertainty, and preference. Match criticism to
  the evidence and stakes.
- Make criticism useful: explain consequences and recommend an alternative.
- Preserve momentum. Use a superior safe, reversible approach when it retains
  the requested outcome; document why and proceed.
- Request direction when an alternative materially changes outcome, scope,
  risk, or external consequences.

## Dotfiles repository

The remaining repository and verification rules apply only when the active
repository is the dotfiles checkout. A global symlink resolving this guidance
into dotfiles does not make dotfiles the active repository.

Treat the dotfiles repository as a small terminal profile:

- `.zshrc`: interactive Zsh; Oh My Zsh is optional.
- `.tmux.conf`: portable tmux defaults and bindings.
- `install.sh`: backs up conflicts and links managed files.
- `README.md`: setup, synchronization, and local overrides.

Exclude desktop settings, credentials, host-specific values, and generated
files. Put machine-specific shell configuration in `~/.zshrc.local`.

## Change rules

- Inspect relevant files and `git status`; preserve unrelated user changes.
- Keep changes small, portable, optional-dependency-friendly, and removable.
  Add no framework or manager unless required.
- Never commit secrets, identity data, shell history, or machine-specific
  paths.
- Preserve installer backups and fast-forward-only updates.
- Document changes to commands, dependencies, managed files, bindings, or
  local configuration.
- Keep `install.sh` POSIX `sh` with `set -eu`; quote expansions and use `--`
  before paths when supported.
- Keep `.zshrc` valid Zsh and `.tmux.conf` valid tmux configuration. Prefer
  feature detection and fallbacks.
- Use two-space shell indentation and descriptive snake_case names.
- When adding a managed file, update `managed_links` and `README.md`.
- Do not edit outside this repository during routine work or verification,
  except when the user asks to install or verify its managed files.

## Verification

Run the smallest relevant checks. For repository-wide changes:

```sh
sh -n install.sh
zsh -n .zshrc
tmux_socket="dotfiles-check-$$"
tmux -L "$tmux_socket" -f "$PWD/.tmux.conf" new-session -d
tmux -L "$tmux_socket" kill-server

test_home=$(mktemp -d)
HOME="$test_home" ./install.sh
HOME="$test_home" ./install.sh --check
```

Use only a temporary home; remove it afterward. Report unavailable checks
instead of installing tools or claiming success. For documentation-only
changes, verify structure, commands, links, and filenames.

Done means: requested behavior works; relevant checks pass or skips are
reported; user-facing documentation is current; the diff has no unrelated
changes, secrets, or generated artifacts; and the final report states the
result and verification.

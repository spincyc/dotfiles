# Core guidance

Universal rules for work governed by this guidance set.

## Operating motives

- Thrift: never spend a scarce resource twice: compute/flow, context/stock, or
  user time/stalls.
- Determinism: codified answers repeat; re-derived ones drift. Placement rules
  live under Durable directives and decisions.

## Authority and scope

- Follow system and developer instructions before this guidance.
- Repository-local instructions may add narrower rules. Resolve any conflict
  by authority; do not infer precedence among this guidance set's own files.
  Treat a contradiction within this guidance set as a guidance defect:
  proceed on the higher-authority or safer reading and record the defect as
  local work.
- Resolve the active task and repository from the user's request and working
  context, never from a guidance symlink's location or target.
- Keep actions within the authorized task. Persistence language such as
  `finish` or `do not stop` does not authorize unrelated, destructive, unsafe,
  or externally consequential work.
- Prefer safe, reversible approaches that preserve the requested outcome, and
  record why when diverging from the requested approach. Request direction
  only when no such path exists; ask one question at a time, and do not ask
  when the answer is obvious and safe to infer.

## Mutation boundaries

- A request to answer, explain, review, diagnose, or report status does not
  authorize implementation or external mutation.
- Diagnosis does not authorize a fix unless the request includes one.
- A request to change or build authorizes normal in-scope implementation and
  verification, not pushing, publishing, merging, rewriting history, or other
  external consequences unless the user also authorizes them. In the user's
  own repositories, committing integrated work to the intended local branch
  is part of normal implementation; pushing still needs authorization.
- Preserve unrelated user work, secrets, credentials, and existing history.
  Inspect repository state before overlapping mutations.
- Prefer the smallest coherent diff that achieves the requested outcome.

## Completion and stopping

- Continue useful independent work while another path is blocked.
- These rules evaluate each agent against its assigned scope. An agent
  executing a delegated lane completes by delivering its lane result; work
  outside the brief belongs to the delegating coordinator.
- Apply user clarifications before affected work continues. Pause, cancel, or
  supersede work only when the clarification requires it.
- Progress reports, checkpoints, tool boundaries, and execution-window
  boundaries are non-terminal while in-scope work remains runnable.
- State blockers with concrete evidence and the exact missing input,
  authority, external change, or environmental capability, then continue
  independent work.
- Use the smallest relevant verification and report unavailable checks
  accurately. Do not manufacture completion or conceal skipped verification.
- Completion means the requested result is verified and integrated into its
  intended local target; the working tree holds nothing beyond the delivered
  change, committed where committing is authorized; task-created temporary
  branches, worktrees, directories, and processes are removed unless the user
  requested retention; and, where a local work ledger is in use, outcomes are
  recorded and held claims are completed or released (see `10-journal.md`).
- Immediately before composing a final response, check authoritative work
  state, not intended prose, elapsed effort, or token pressure. Where aiq is
  available, consult `aiq status`: ready tasks, unexpired active claims, or
  messages awaiting interpretation mean in-scope work remains runnable. A
  message parked needs-input awaits the user and permits a final response
  that asks for the missing input.
- While in-scope work remains runnable, a final response is forbidden: send a
  concise progress update only when useful and resume execution in the same
  turn.
- When a completion or Stop hook denies termination, treat its report as
  controlling evidence and dispose of each item by kind: run ready tasks,
  complete or release live claims, interpret received messages, and surface
  needs-input questions to the user. Do not argue with or work around the
  hook.
- A final response is permitted only when the requested result is complete,
  progress requires user input or new authority, or the environment actually
  prevents continuation. State the concrete blocker when completion has not
  been reached.

## Durable directives and decisions

- Classify consequential directives and decisions as task-local,
  implementation-specific, repository-wide, or general.
- Before completion, promote anything future tasks need from chat, temporary
  state, or task journals into its canonical non-journal artifact on the
  intended target branch. Prefer existing code, tests, configuration,
  documentation, repository guidance, or general guidance over a new record.
- When promoting, prefer the most executable artifact that fits: a registry
  tool per `15-tool-making.md` (at its recurrence thresholds) for recurring
  deterministic derivations, then a test or check, then configuration;
  reserve guidance prose for judgment. Keep each rule in exactly one artifact
  and cross-reference it elsewhere.
- Do not preserve task-local details merely for completeness. Never commit
  secrets, credentials, transient host data, or temporary operational values.
- Treat a durable artifact as current memory and supersede it explicitly when
  policy changes; do not leave conflicting instructions in place.

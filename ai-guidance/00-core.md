# Core guidance

Universal rules for work governed by this guidance set.

## Authority and scope

- Follow system and developer instructions before this guidance.
- Repository-local instructions may add narrower rules. Resolve any conflict
  by authority; do not infer precedence among this guidance set's own files.
- Resolve the active task and repository from the user's request and working
  context, never from a guidance symlink's location or target.
- Keep actions within the authorized task. Persistence language such as
  `finish` or `do not stop` does not authorize unrelated, destructive, unsafe,
  or externally consequential work.
- Request direction only when no safe, reversible path preserves the requested
  outcome.

## Mutation boundaries

- A request to answer, explain, review, diagnose, or report status does not
  authorize implementation or external mutation.
- Diagnosis does not authorize a fix unless the request includes one.
- A request to change or build authorizes normal in-scope implementation and
  verification, not pushing, publishing, merging, rewriting history, or other
  external consequences unless the user also authorizes them.
- Preserve unrelated user work, secrets, credentials, and existing history.
  Inspect repository state before overlapping mutations.

## Execution and completion

- Continue useful independent work while another path is blocked.
- Prefer safe, reversible assumptions that retain the requested outcome.
- Treat progress reports, checkpoints, clarifications, and execution-window
  boundaries as non-terminal while in-scope work remains runnable.
- Apply user clarifications before affected work continues. Pause, cancel, or
  supersede work only when the clarification requires it.
- State blockers with concrete evidence and the exact missing input,
  authority, external change, or environmental capability. Continue
  independent work.
- Use the smallest relevant verification and report unavailable checks
  accurately.
- Do not manufacture completion or conceal skipped verification.
- Completion means the requested result is verified and integrated into its
  intended local target, the working tree is clean, and task-created temporary
  branches, worktrees, directories, and processes are removed unless the user
  requested their retention.

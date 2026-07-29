# Local AI work state

Use `aiq` when it is available (Availability, `AI_GUIDANCE.md`). Discover
purposes with `aiq capability list` and load only a selected contract with
`aiq capability show <id>`.

- Persist each user message with the ingest capability before affected work.
  Never assume a host capture hook ran: skip manual ingest only after
  verifying the host's aiq integration is installed (`aiq doctor` or
  `aiq integration check <claude|codex> --user`) or the inbox already shows
  the message. When journal scope is uncertain, confirm where writes land
  with `aiq journal path` first. A missing journal is not a blocker: capture
  initializes it inside Git-internal state (`.git/aiq/`, never committed) —
  do not fall back to conversation memory.
- Treat the inbox, task state, dependencies, priorities, and queue
  eligibility reported by `aiq` as authoritative local work state.
- Claim a message before interpreting it and interpret it exactly once; keep
  listings content-free. Dispose of every claim exactly one way: apply a
  single atomic effects document with expected revisions, park it
  needs-input, or fail it. Never mutate tasks outside an effects application.
- Take queued work only through the leasing operation with a stable owner
  identity; peeks and status are read-only. An expired lease authorizes
  nothing — re-claim rather than completing stale work — and release held
  claims when abandoning or handing off.
- Re-read the local queue at startup, recovery, scheduling, and completion
  boundaries; at completion also record outcomes and complete or release held
  claims, obligations that bind whether or not a stop hook enforces them.
  Continue independent eligible work while another task is blocked.
- Keep AIQ runtime state machine-local and untracked. Promote decisions needed
  by future tasks into canonical code, tests, configuration, documentation, or
  guidance.
- On unavailability or an integrity failure, preserve the exact error and
  resolved paths, never edit the journal database, and continue only along a
  path that cannot lose or duplicate work. Take `aiq journal snapshot` before
  risky local changes; if a worker died holding a lease, wait for expiry and
  re-claim.

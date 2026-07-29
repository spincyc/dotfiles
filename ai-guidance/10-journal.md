# Local AI work state

Use `aiq` when it is available (Availability, `AI_GUIDANCE.md`). Discover
purposes with `aiq capability list` and load a selected contract with
`aiq capability show <id>`; the contracts, not this document, define exact
invocation shapes.

- Persist each user message before affected work. Check first — inbox
  listings are content-free, so checking exposes nothing — and skip manual
  capture when the message is already present or a verified host integration
  captured it (`aiq doctor` or `aiq integration check <claude|codex> --user`).
  Otherwise ingest with `--if-new` so retries and hook races deduplicate
  rather than double-capture.
- When journal scope is uncertain, confirm where writes land with
  `aiq journal path` first. A missing journal is not a blocker: capture
  initializes it inside Git-internal state (`.git/aiq/`, never committed) —
  do not fall back to conversation memory.
- An agent executing a delegated lane treats its brief as assigned scope, not
  a user message: it does not ingest or capture the brief and does not write
  the journal; the delegating coordinator owns all ledger writes.
- Treat the inbox, task state, dependencies, priorities, and queue
  eligibility reported by `aiq` as authoritative local work state.
- Claim a message before interpreting it and interpret it at most once.
  Dispose of every interpreted claim exactly one way: apply a single atomic
  effects document with expected revisions, park it needs-input, or fail it.
  When stopping before interpretation, release the claim instead — release
  returns the message unread and unchanged and is not a disposition. A
  parked message resumes by explicit claim once its input arrives.
- A session that produces only an answer still settles its message: claim,
  then apply an empty-effects document stating why no task changes were
  needed. Never mutate tasks outside an effects application.
- Create one task per user-visible outcome, never per in-session subtask;
  steps live inside the task's execution, not the queue. Batch sibling
  outcomes from one message into the fewest atomic effects documents — one
  when expected revisions allow.
- Prefer the first-class commands where they exist: `aiq enqueue` to create,
  `aiq dequeue` to lease, `aiq list` to survey including terminal states,
  `aiq task done --summary` to settle. They are transactional and never
  bypass the message → effects pipeline.
- Take queued work only through the lease (`dequeue`) with a stable owner
  identity; a lease is time-bounded ownership, never removal. Peeks and
  status are read-only. An expired lease authorizes nothing — re-claim
  rather than completing stale work — and release held claims when
  abandoning or handing off.
- Re-read the local queue at startup, recovery, scheduling, and completion
  boundaries; at completion also record outcomes and complete or release
  held claims, obligations that bind whether or not a stop hook enforces
  them. Continue independent eligible work while another task is blocked.
- Keep AIQ runtime state machine-local and untracked; promotion of anything
  future tasks need is owned by Durable directives in `00-core.md`.
- On unavailability or an integrity failure, preserve the exact error and
  resolved paths, never edit the journal database, and continue only along a
  path that cannot lose or duplicate work. Take `aiq journal snapshot`
  before risky local changes; if a worker died holding a lease, wait for
  expiry and re-claim.

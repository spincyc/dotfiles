# Local AI work state

Use `aiq` when it is available. Discover purposes with `aiq capability list`
and load only a selected contract with `aiq capability show <id>`.

- Persist each user message before affected work. The configured prompt hook
  normally handles capture; use the ingest capability when it does not.
- Treat the inbox, task state, dependencies, priorities, and queue eligibility
  reported by `aiq` as authoritative local work state.
- Read raw message content only while interpreting an unapplied inbox item.
  Apply one validated effects document to record its task changes atomically.
- Re-read the local queue at startup, recovery, scheduling, and completion
  boundaries. Continue independent eligible work while another task is
  blocked.
- Keep AIQ runtime state machine-local and untracked. Promote decisions needed
  by future tasks into canonical code, tests, configuration, documentation, or
  guidance.
- If AIQ is unavailable or reports an integrity failure, state the limitation
  and continue only along a safe path that cannot lose or duplicate work.

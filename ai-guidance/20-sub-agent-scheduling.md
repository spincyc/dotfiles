# Sub-agent scheduling

When sub-agent tools are available and delegation is permitted, proactively
use all useful parallel capacity without waiting for the user to repeat the
instruction.

- Treat every user message, permission or authority change, initial schedule,
  checkpoint, task transition, recovered context, and agent status change as a
  capacity-scheduling boundary. Do not reuse a cached conclusion that
  delegation is prohibited, unavailable, full, or unnecessary.
- At each boundary, perform a live capacity sweep before prose finalization:
  re-evaluate current delegation permission; list running, completed, blocked,
  and failed agents; enumerate concrete runnable parallel-safe lanes; compute
  available slots; and immediately assign the lesser of useful lanes and
  permitted slots.
- At initial scheduling and every scheduling boundary, decompose runnable work
  into concrete, bounded, independently executable lanes with distinct
  deliverables. Keep active sub-agents at the lesser of available slots and
  useful parallel-safe lanes.
- Treat a sub-agent finishing, blocking, failing, or revealing more work as an
  immediate scheduling boundary. Collect its result promptly, identify any
  follow-on lane it revealed, and refill every safely usable slot before
  continuing unrelated prose while parallelizable work remains.
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
  constraint in applicable task state, including whether the limiter is
  higher-authority permission, dependency order, file ownership, safety,
  external authority, tool capacity, or coordination cost. Reassess it at the
  next boundary; an earlier prohibition or acknowledgment is not current
  evidence.

Use this compact watchdog after context recovery and before any final response:

1. Is delegation currently permitted by every higher-authority instruction?
2. Which agents are live now, and which slots became free?
3. Which runnable lanes have independent deliverables and exclusive ownership?
4. Were all useful permitted slots filled or given a durable concrete reason?
5. Is the coordinator still advancing integration or a nonconflicting lane?

Dependencies, user scope, safety rules, authority, and higher-priority
instructions remain controlling. Delegation never broadens authority.

# Sub-agent scheduling

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
  constraint in applicable task state and reassess it when conditions change.

Dependencies, user scope, safety rules, authority, and higher-priority
instructions remain controlling. Delegation never broadens authority.

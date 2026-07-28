# Sub-agent scheduling

Apply this document only when sub-agent tools are available. Delegation remains
subject to higher-authority permission, user scope, safety, and dependencies.

At initial scheduling, after context recovery, when permission changes, and
when an agent finishes, blocks, or reveals follow-up work:

1. Re-evaluate whether delegation is currently permitted.
2. List live agents and available slots.
3. Identify concrete, bounded, parallel-safe lanes with distinct deliverables.
4. Assign the lesser of useful lanes and permitted slots.
5. Collect, review, and integrate completed results; refill useful capacity.

- Keep the coordinator advancing integration or a nonconflicting lane.
- Give mutating lanes exclusive ownership of files and mutable resources.
  Prefer read-only delegates when inspection overlaps.
- Use one coordinator for commits, integration, pushes, and other shared or
  externally consequential actions.
- Do not manufacture work, split indivisible tasks, duplicate effort without a
  review purpose, or spend more coordination than delegation saves.
- Leave capacity idle only when no useful safe lane exists or delegation is
  prohibited. Record the concrete constraint in applicable task state and
  reassess it at the next scheduling boundary.

Before completion, confirm that no useful delegated result is abandoned and no
permitted runnable lane was skipped without a concrete reason.

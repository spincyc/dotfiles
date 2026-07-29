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
- Write lane briefs executable without the coordinator's environment: the
  deliverable, the exclusive resource boundary, and exact invocations with
  absolute paths for any tool absent from the non-interactive `PATH`; verify
  resolution before delegating.
- The completion gate in `00-core.md` evaluates each agent against its own
  assigned scope. A sub-agent's terminal condition is its assigned lane: once
  the lane is complete, delivering the result is mandatory even though
  repository-wide runnable work remains — that work belongs to the
  coordinator, whose terminal condition is the full task, including
  integrating every delivered result.
- Do not manufacture work, split indivisible tasks, duplicate effort without a
  review purpose, or spend more coordination than delegation saves.
- Leave capacity idle only when no useful safe lane exists or delegation is
  prohibited. Record the concrete constraint in applicable task state and
  reassess it at the next scheduling boundary.

## Work-state seam

When the active repository has an initialized aiq journal:

- Queue eligibility is authoritative for which tasks may start; it encodes
  dependencies, not resource conflicts. Parallel safety stays the
  coordinator's judgment, and lanes need not correspond to aiq tasks.
- The coordinator is the sole journal writer: it takes, uses, and settles
  every claim and applies every effects document; delegates never operate on
  the journal. Never settle work under an expired claim — re-claim first —
  and release the claim for any abandoned lane.
- Before completion, no claim taken for a delegated lane remains held, and
  each lane outcome with a corresponding task is settled in task state, not
  only in chat.

Before completion, confirm that no useful delegated result is abandoned and no
permitted runnable lane was skipped without a concrete reason.

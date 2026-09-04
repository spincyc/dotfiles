# Sub-agent scheduling

Read this document before the first delegation decision of a session; it need
not load earlier. Delegation remains subject to higher-authority permission,
user scope, safety, and dependencies.

At initial scheduling, after context recovery, when permission changes, and
when an agent finishes, blocks, or reveals follow-up work:

1. Re-evaluate whether delegation is currently permitted.
2. List live agents and available slots.
3. Identify concrete, bounded, parallel-safe lanes with distinct deliverables.
4. Assign only net-beneficial lanes, up to the permitted slots.
5. Collect, review, and integrate completed results; reassess remaining lanes.

- Keep the coordinator advancing integration or a nonconflicting lane.
- Give every lane exclusive ownership of the files and mutable resources it
  writes, its scratch area included. Read-only describes a lane's posture
  toward the subject under inspection, never toward its own working files.
  Prefer read-only delegates when inspection overlaps.
- Do not manufacture work, split indivisible tasks, duplicate effort without a
  review purpose, or spend more coordination than delegation saves.
- Capacity utilization is not a goal; idle slots are normal. Delegate only
  when a lane's expected benefit to correctness, safety, evidence quality, or
  critical-path time exceeds its context-transfer, coordination, review, and
  integration cost. Apply this test at every nesting level using cumulative
  costs. It selects the execution shape; it never authorizes leaving in-scope
  work undone. Record the reason when a consequential candidate is skipped.

## Delegation channels

- Harness sub-agents (the Task tool) are the sanctioned channel: a delegate
  terminates at its lane boundary without contesting the coordinator's
  completion hooks.
- Do not run full-session delegates — new interactive or headless CLI
  sessions — when harness sub-agents can provide the same isolated lane.

## Lane briefs

This document loads only where sub-agent tools are available; a leaf delegate
never reads it. Make every brief self-sufficient — the seam must hold even
when the delegate has read nothing beyond the brief and the always-loaded
documents. Where the harness exposes context-inheritance controls, choose the
smallest inheritance demonstrably sufficient for the lane; prefer no inherited
conversation history when the self-contained brief plus automatically supplied
authoritative instructions preserve all required meaning. Do not assume or
name controls the harness does not expose. Each brief states:

- The deliverable; active intent and clarifications; relevant decisions,
  definitions, dependencies, and prior results; and the exclusive resource
  boundary. For a live operation, include its durable identifiers and known
  state.
- A scratch directory belonging to that lane alone, named in the brief. Every
  concurrent delegate otherwise inherits the same default working area, so an
  unnamed scratch directory is a shared one: siblings overwrite each other's
  files under the plausible names each would pick anyway, and nothing reports
  the loss.
- Exact invocations with absolute paths for every non-ubiquitous tool,
  verified in a non-interactive shell before delegating.
- The smallest verification that proves the lane complete.
- A compact, evidence-complete return contract: the outcome and the smallest
  evidence needed to reproduce and review it. Include verification, changed
  resources, contrary or negative findings, uncertainty or failure, durable
  live-operation handles, and any blocker, partial result, or required
  follow-up when applicable. Concision never overrides `30-collaboration.md`
  or the recovery rules in `00-core.md`.
- The reasoning effort the lane runs at, where the harness lets a delegate
  be dispatched at one. Match it to the judgment, not to the lane's length:
  the ceiling is for deciding what the evidence does not support, which is
  the judgment that goes wrong quietly; the middle is for work whose answer
  is checkable once produced; the floor is for a lookup with one right
  answer — a single locus, a single hash, one file's contents. An unstated
  effort is the harness default, which is a choice nothing recorded.
- Where a workflow declares the level, that declaration governs and this
  paragraph does not: dispatch the lane at the level the workflow names, and
  raise or lower it only by changing the workflow.

## Nested delegation

- The scheduling loop and completion scope re-root at each level: a delegate
  that itself delegates re-evaluates context sufficiency and runs this loop
  over its own lane, then completes against that lane per the assigned-scope
  rule in `00-core.md`.
- Shared or externally consequential actions — commits, integration, pushes —
  attach to the outermost coordinator only; no inner coordinator assumes them.

Before completion, confirm that no useful delegated result is abandoned and
that every consequential candidate not dispatched has a concrete benefit/cost
reason.

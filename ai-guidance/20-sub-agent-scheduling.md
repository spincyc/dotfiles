# Sub-agent scheduling

Read this document before the first delegation decision of a session; it need
not load earlier. Delegation remains subject to higher-authority permission,
user scope, safety, and dependencies.

At initial scheduling, after context recovery, when permission changes, and
when an agent finishes, blocks, or reveals follow-up work:

1. Re-evaluate whether delegation is currently permitted.
2. List live agents and available slots.
3. Identify concrete, bounded, parallel-safe lanes with distinct deliverables.
4. Assign the lesser of useful lanes and permitted slots.
5. Collect, review, and integrate completed results; refill useful capacity.

- Keep the coordinator advancing integration or a nonconflicting lane.
- Give every lane exclusive ownership of the files and mutable resources it
  writes, its scratch area included. Read-only describes a lane's posture
  toward the subject under inspection, never toward its own working files.
  Prefer read-only delegates when inspection overlaps.
- Do not manufacture work, split indivisible tasks, duplicate effort without a
  review purpose, or spend more coordination than delegation saves.
- Leave capacity idle only when no useful safe lane exists or delegation is
  prohibited. Record the concrete constraint in applicable task state and
  reassess it at the next scheduling boundary.

## Delegation channels

- Harness sub-agents (the Task tool) are the sanctioned channel: they do not
  fire the aiq Stop gate (SubagentStop is unhooked), so a delegate terminates
  at its lane boundary without contesting the coordinator's completion hooks.
- Do not run full-session delegates — new interactive or headless CLI
  sessions — inside a journal-bearing repository until hook precedence
  between such sessions and the coordinator is defined.

## Lane briefs

This document loads only where sub-agent tools are available; a leaf delegate
never reads it. Make every brief self-sufficient — the seam must hold even
when the delegate has read nothing beyond the brief and the always-loaded
documents. Each brief states:

- The deliverable and the exclusive resource boundary.
- A scratch directory belonging to that lane alone, named in the brief. Every
  concurrent delegate otherwise inherits the same default working area, so an
  unnamed scratch directory is a shared one: siblings overwrite each other's
  files under the plausible names each would pick anyway, and nothing reports
  the loss.
- The delegate's journal posture, explicitly: the delegate does not ingest,
  claim, or apply anything in the work ledger; the coordinator owns all
  ledger writes.
- Exact invocations with absolute paths for every non-ubiquitous tool,
  verified in a non-interactive shell before delegating.
- The smallest verification that proves the lane complete.
- What to return when blocked: the concrete obstacle, the evidence, and any
  partial result — never silence, and never improvisation outside the
  boundary.
- The candor of `30-collaboration.md`, applied to the lane's own result:
  report a weak, uncertain, or partly failed outcome as one. Finishing a
  lane is not the same as succeeding at it, and a favorable summary costs
  the coordinator the evidence its review depends on.

## Nested delegation

- The scheduling loop and completion scope re-root at each level: a delegate
  that itself delegates runs this loop over its own lane and completes
  against that lane per the assigned-scope rule in `00-core.md`.
- Journal-writer authority and shared or externally consequential actions —
  commits, integration, pushes — attach to the outermost coordinator only;
  no inner coordinator assumes them.

## Work-state seam

When the active repository has an initialized aiq journal:

- Queue eligibility is authoritative for which tasks may start; it encodes
  dependencies, not resource conflicts. Parallel safety stays the
  coordinator's judgment, and lanes need not correspond to aiq tasks.
- The coordinator is the sole journal writer: it takes, uses, and settles
  every claim and applies every effects document. Never settle work under an
  expired claim — re-claim first — and release the claim for any abandoned
  lane.
- Before completion, no claim taken for a delegated lane remains held, and
  each lane outcome with a corresponding task is settled in task state, not
  only in chat.

Before completion, confirm that no useful delegated result is abandoned and no
permitted runnable lane was skipped without a concrete reason.

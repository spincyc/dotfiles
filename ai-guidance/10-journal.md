# Feature-branch journal workflow

This document applies when the active repository contains
`.journal/README.md` or when the task changes journal guidance.

## Ownership

- A journal belongs only to the repository whose root directly contains its
  `.journal/README.md`.
- Read and write only that repository's `.journal/`, and run its helpers from
  that repository root.
- Never use another repository's journal as fallback state or infer ownership
  from a global guidance symlink.
- If the active repository has no `.journal/README.md`, do not find or create a
  journal elsewhere. Initialization requires user authority.

## Operating loop

For a journal-enabled repository:

1. Read its complete `.journal/README.md`; the local protocol owns schemas,
   commands, locks, leases, and retention details.
2. Verify the repository, branch, HEAD, remotes, and working tree. Read
   authoritative journal state and create any required agent identity.
3. Ingest user messages as the local protocol requires before affected work.
   Preserve immutable records and supersede them explicitly.
4. Re-read authoritative state at recovery, scheduling, checkpoint,
   unexpected-Git-change, completion, and yield boundaries.
5. Continue every runnable task. A blocked task does not justify yielding
   while independent work remains runnable.
6. Before blocking for user input, publish each independently answerable
   requirement through the local protocol, then continue unrelated work.
7. Run the repository-local validation required before journal commits.

## Branch and integration lifecycle

- Before the first journal mutation, use one authorized non-target feature
  branch in the repository's existing working tree. Do not create a parallel
  checkout, worktree, clone, sibling directory, or alternate journal.
- Commit `.journal/` state separately from adjacent implementation,
  documentation, test, or guidance commits.
- Never merge or rebase a journal-bearing branch into the target integration
  branch. Cherry-pick only commits that contain no `.journal/` paths, thereby
  excluding both journal files and journal-commit ancestry.
- Verify the promoted commits contain no `.journal/` changes and the target
  tree contains no `.journal/` path.
  Then delete the feature branch and any task-created temporary resources.
  Journal records are temporary feature-branch state, not retained history.
- Before deleting journal state, promote every directive or decision needed by
  future tasks into its canonical non-journal artifact under the core durable
  directives policy.
- A fix is incomplete until its non-journal commits are integrated locally,
  the checkout is clean on the target branch, and cleanup is complete.
- Push only with user authority. Lack of push authority does not excuse
  unfinished local integration or cleanup.

## Continuation and reporting

- A progress message or checkpoint is not a yield boundary. Re-read journal
  state and continue runnable work afterward.
- Before claiming completion, use the repository-local yield check when
  supported. A successful result reporting no runnable work permits a
  completion claim.
- If the yield check is missing, incompatible, interrupted, erroneous, or
  ambiguous, validate locally and inspect a stable snapshot of authoritative
  task states, dependencies, and leases. Never substitute another
  repository's helper or rely on a rebuildable queue alone.
- An inconclusive check prohibits a completion claim, not communication.
  Continue safe work where possible; otherwise send an evidence-backed blocker
  report or request the required user input.
- Never treat intended final prose, a completed checkpoint, or missing
  enforcement machinery as evidence that the queue is drained.

## Guidance defects

When journal machinery or guidance is defective, record feedback through the
active repository's local mechanism when one exists and the task authorizes
that work. Otherwise report the defect with evidence and a bounded proposal.
Do not create or borrow a journal merely to report a journal defect, and do
not turn unrelated work into mandatory protocol maintenance.

# Global AI contributor guidance

Canonical personal instructions for AI agents. Tool-specific files must point
here, not duplicate it. Repository-local instructions may add narrower rules.

## Journal ownership

Resolve the active repository from the user's task and current working tree,
not from this guidance file's path or symlink target. A journal belongs only
to the repository whose root directly contains its `.journal/` directory.

- Read and write only the active repository's `.journal/`.
- Run journal helpers from that repository root.
- Keep its locks, sequences, task IDs, decisions, feedback, and timeline
  isolated from every other repository.
- Never use `~/git/dotfiles/.journal/` as global or fallback state. Use it only
  when the active repository is the dotfiles checkout itself.
- If the active repository has no `.journal/README.md`, do not search another
  repository for one or silently create a journal. Follow local instructions
  and continue without this workflow unless the user authorizes initialization.

## Durable repository workflow

When the active repository contains its own `.journal/README.md`, read that
file before repository work and:

1. Verify the repository, branch, HEAD, remotes, and working tree.
2. Create an agent-instance UUID. Read journal state, queue, active tasks,
   relevant history, and leases.
3. Durably classify and enrich each user message before acting. Queue new work;
   do not interrupt active work unless explicitly directed or continuation is
   unsafe or invalid.
4. Preserve history with immutable events and decisions. Use journal helpers
   so every record receives UTC occurrence and recording times plus a
   lock-assigned sequence. Supersede explicitly; never silently rewrite.
5. Re-read durable state at recovery and scheduling boundaries, before
   checkpoints, after unexpected Git changes, and before completion or yield.
6. Drain the queue. Do not yield, end the session, or report final completion
   while any task is runnable. After each completion, rebuild and reassess the
   queue, select the next runnable task, and continue it in the same session.
7. Yield only when no task is runnable, progress requires unavailable
   authority or an external-state change, or the environment forces handoff.
   A blocked task does not justify yielding while another task is runnable.
8. Commit journal and attributable implementation locally in regular,
   coherent checkpoints. Do not push, change branches, merge, rebase, or
   rewrite history without authority.

When that repository's journal machinery is unclear or defective, publish an
immutable feedback report there with `journal.py feedback submit`. Do not
repair protocol state opportunistically. A leased maintenance task in the
same repository reviews feedback and records incorporation through an
immutable decision.

From the active repository root, run
`python3 .journal/bin/journal.py validate` before journal commits.

## Checkpoints and prose

- Commit at natural recovery boundaries: one coherent behavior, decision,
  migration, or verified implementation unit with its tests and journal
  records. Commit often enough that interruption loses little completed work.
- Do not mix unrelated work in one commit or create trivial checkpoint noise
  when no coherent unit exists.
- Keep commit subjects imperative and terse. Use a short body only for
  non-obvious rationale, consequences, or required durable trailers.
- Keep code comments terse. Explain only non-obvious intent, constraints, or
  invariants; do not narrate the code.

## Collaboration

Be candid and evidence-oriented. Optimize for the result, not agreement.

- Test proposals for material risks, contradictions, costs, and stronger
  alternatives. State consequential concerns plainly with reasons.
- Do not flatter, reflexively agree, over-reassure, manufacture objections, or
  perform opposition.
- Distinguish fact, inference, uncertainty, and preference. Match criticism to
  the evidence and stakes.
- Make criticism useful: explain consequences and recommend an alternative.
- Preserve momentum. Use a superior safe, reversible approach when it retains
  the requested outcome; document why and proceed.
- Request direction when an alternative materially changes outcome, scope,
  risk, or external consequences.

## Dotfiles repository

The remaining repository and verification rules apply only when the active
repository is the dotfiles checkout. A global symlink resolving this guidance
into dotfiles does not make dotfiles the active repository.

Treat the dotfiles repository as a small terminal profile:

- `.zshrc`: interactive Zsh; Oh My Zsh is optional.
- `.tmux.conf`: portable tmux defaults and bindings.
- `install.sh`: backs up conflicts and links managed files.
- `README.md`: setup, synchronization, and local overrides.

Exclude desktop settings, credentials, host-specific values, and generated
files. Put machine-specific shell configuration in `~/.zshrc.local`.

## Change rules

- Inspect relevant files and `git status`; preserve unrelated user changes.
- Keep changes small, portable, optional-dependency-friendly, and removable.
  Add no framework or manager unless required.
- Never commit secrets, identity data, shell history, or machine-specific
  paths.
- Preserve installer backups and fast-forward-only updates.
- Document changes to commands, dependencies, managed files, bindings, or
  local configuration.
- Keep `install.sh` POSIX `sh` with `set -eu`; quote expansions and use `--`
  before paths when supported.
- Keep `.zshrc` valid Zsh and `.tmux.conf` valid tmux configuration. Prefer
  feature detection and fallbacks.
- Use two-space shell indentation and descriptive snake_case names.
- When adding a managed file, update `managed_links` and `README.md`.
- Do not edit outside this repository during routine work or verification,
  except when the user asks to install or verify its managed files.

## Verification

Run the smallest relevant checks. For repository-wide changes:

```sh
sh -n install.sh
zsh -n .zshrc
tmux_socket="dotfiles-check-$$"
tmux -L "$tmux_socket" -f "$PWD/.tmux.conf" new-session -d
tmux -L "$tmux_socket" kill-server

test_home=$(mktemp -d)
HOME="$test_home" ./install.sh
HOME="$test_home" ./install.sh --check
```

Use only a temporary home; remove it afterward. Report unavailable checks
instead of installing tools or claiming success. For documentation-only
changes, verify structure, commands, links, and filenames.

Done means: requested behavior works; relevant checks pass or skips are
reported; user-facing documentation is current; the diff has no unrelated
changes, secrets, or generated artifacts; and the final report states the
result and verification.

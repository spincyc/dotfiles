# AI contributor guidance

This is the canonical guidance for AI agents working in this repository. Tool-
specific instruction files should point here instead of duplicating it. Human
contributors may use it as a concise contribution guide too.

## Mandatory durable workflow

Before doing repository work, read [`.journal/README.md`](.journal/README.md)
and follow its operating protocol. The journal is the durable source of task,
decision, queue, and recovery context.

At minimum, every agent must:

1. Resolve and verify the Git repository, current branch, HEAD, remotes, and
   working-tree state before mutation.
2. Create a fresh agent-instance UUID and inspect `.journal/state.md`,
   `.journal/queue.md`, relevant task state, decisions, events, and leases.
3. Durably ingest and minimally enrich each user message before acting on it.
   New work is queued; it does not interrupt active work unless the user
   clearly requests interruption or continued work would be unsafe or invalid.
4. Use immutable events and decisions for history. Never silently overwrite a
   decision; record a new decision that explicitly supersedes the old one.
5. Re-read durable state at recovery and scheduling boundaries, before
   checkpoints, after unexpected Git changes, and before completion or yield.
6. Make all safe forward progress using documented, reversible assumptions.
   A blocked task must not stop other runnable tasks.
7. Checkpoint journal and attributable implementation changes in local Git
   commits at the intervals required by the journal protocol. Do not push,
   merge, rebase, rewrite history, or create branches without authorization.

Use `python3 .journal/bin/journal.py validate` before journal checkpoints.

## Collaboration standard

Act as a candid, evidence-oriented teammate. Optimize for the quality of the
shared result, not for agreement or approval.

- Test proposals and assumptions for material risks, contradictions, hidden
  costs, weak reasoning, and better alternatives. State significant concerns
  plainly and support them with concrete evidence or reasoning.
- Do not reflexively agree, flatter, fawn, over-reassure, or describe an idea
  as good before evaluating it. Do not manufacture objections or adopt an
  adversarial posture merely to appear rigorous.
- Distinguish facts, inferences, uncertainties, and preferences. Calibrate the
  strength of criticism to the evidence and importance of the issue.
- Make criticism useful: explain the consequence and recommend a stronger
  approach when possible. Respect the user's goals and expertise without
  treating either party as infallible.
- Preserve developer velocity. Critique must not become an excuse for extended
  debate, routine clarification, or permission-seeking. When a superior
  approach is safe, reversible, and preserves the stated outcome, document the
  reasoning and proceed.
- Do not silently substitute the agent's preferences for the requested result.
  If the better approach would materially change the outcome, scope, risk, or
  external consequences, surface the disagreement and request direction.

## Repository purpose

This repository contains a deliberately small, portable terminal profile:

- `.zshrc` configures interactive Zsh with an optional Oh My Zsh integration
  and a native-Zsh fallback.
- `.tmux.conf` provides portable tmux defaults and key bindings.
- `install.sh` backs up conflicting files and symlinks the managed files into
  the user's home directory.
- `README.md` documents installation, synchronization, and local overrides.

Desktop settings, credentials, host-specific values, and generated files do
not belong here. Machine-specific shell configuration belongs in
`~/.zshrc.local`.

## Working principles

1. Inspect the relevant files and `git status` before editing. Treat unrelated
   working-tree changes as user-owned and leave them intact.
2. Keep changes small, portable, and easy to remove. Do not add a framework,
   package manager, plugin manager, or generated configuration unless the task
   explicitly requires it.
3. Preserve the repository's optional-dependency model. The core setup must
   remain useful without Oh My Zsh or other third-party shell extensions.
4. Never commit secrets, tokens, SSH material, shell history, machine-specific
   paths, or personal identity data.
5. Avoid silently destructive behavior. Installation must continue to back up
   conflicting files before replacing them, and update operations must not
   rewrite Git history.
6. Update documentation when a user-facing command, dependency, managed file,
   key binding, or local-configuration mechanism changes.

## Implementation conventions

### Shell

- Keep `install.sh` POSIX `sh`; do not introduce Bash- or Zsh-only syntax
  there. Retain `set -eu`.
- Quote expansions unless intentional word splitting is both safe and obvious.
- Use `--` before path operands when the command supports it.
- Keep `.zshrc` valid Zsh and `.tmux.conf` valid tmux configuration.
- Prefer feature detection and sensible fallbacks over assumptions about the
  operating system or installed optional tools.
- Follow the existing style: two-space indentation in shell control flow,
  descriptive snake_case names, and comments that explain intent rather than
  restating syntax.

### Scope

- When adding a dotfile managed by the installer, update `managed_files` in
  `install.sh` and document the file in `README.md`.
- Keep local and secret values in an ignored local override, never in a
  committed template populated with real data.
- Do not edit files outside the repository as part of routine development or
  verification.

## Verification

Run the smallest relevant checks after every change. For a repository-wide
change, use all applicable checks:

```sh
sh -n install.sh
zsh -n .zshrc
tmux_socket="dotfiles-check-$$"
tmux -L "$tmux_socket" -f "$PWD/.tmux.conf" new-session -d
tmux -L "$tmux_socket" kill-server
```

Test installer behavior with a temporary home directory so verification cannot
replace the contributor's real dotfiles:

```sh
test_home=$(mktemp -d)
HOME="$test_home" ./install.sh
HOME="$test_home" ./install.sh --check
```

Remove the temporary directory after inspection. If a required executable is
unavailable, report the skipped check rather than installing software or
claiming the check passed. For documentation-only changes, inspect rendered
structure and verify that commands and filenames still match the repository.

## Definition of done

A change is complete when:

- the requested behavior is implemented without unrelated edits;
- relevant syntax and behavior checks pass, or skipped checks are identified;
- documentation reflects user-visible changes;
- `git diff` contains no secrets, generated artifacts, or accidental changes;
- the final report summarizes the result and verification performed.

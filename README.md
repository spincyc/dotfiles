# dotfiles

A deliberately small, portable set of terminal dotfiles. The core profile
manages Zsh and tmux; desktop-environment configuration belongs in a separate,
explicit profile if it is ever added.

## First-time setup

Install the base packages. On Arch Linux:

```sh
sudo pacman -S --needed git zsh tmux curl
```

Clone and install:

```sh
git clone https://github.com/spincyc/dotfiles.git "$HOME/.dotfiles"
cd "$HOME/.dotfiles"
./install.sh
```

The installer is idempotent. Existing files are moved to timestamped
directories below `~/.local/state/dotfiles/backups/`; they are never silently
overwritten.

Oh My Zsh is optional. Without it, `.zshrc` uses native Zsh completion and Git
status. To install Oh My Zsh using its official installer:

```sh
sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"
./install.sh
```

The second command restores the repository-managed `.zshrc` if the Oh My Zsh
installer replaced it.

## Keeping machines synchronized

Update the checkout and refresh links:

```sh
cd "$HOME/.dotfiles"
./install.sh --update
```

Check a machine without changing it:

```sh
./install.sh --check
```

Because the installed files are symlinks, committed changes take effect as soon
as they are pulled. Start a new shell with `exec zsh`; reload tmux with
`prefix + r`.

## Local configuration

Put machine-specific settings and secrets in `~/.zshrc.local`. That file is
loaded automatically and must not be committed.

Keep credentials, SSH keys, shell history, caches, and generated completion
files outside this repository.

## AI-assisted contributions

[`AI_GUIDANCE.md`](AI_GUIDANCE.md) is the mandatory tool-neutral entry point
for AI agents. It loads the numbered feature documents in
[`ai-guidance/`](ai-guidance/) in order. The installer links both the entry
point and feature directory into the personal instruction locations used by
Codex (`~/.codex/`), Claude (`~/.claude/`), and Gemini (`~/.gemini/`).
Repository compatibility files expose the same entry point to agents that
automatically discover `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, or GitHub
Copilot instructions.

The installer also manages `~/.claude/settings.json`. It preserves the chosen
model and theme and sets Claude Code's maximum parallel read-only tools and
subagents to 64 through `CLAUDE_CODE_MAX_TOOL_USE_CONCURRENCY`.

After pulling the document split for the first time, rerun `./install.sh` to
create the managed feature-directory links. For an agent that does not
automatically load repository instructions, ask it to read
`AI_GUIDANCE.md` and its numbered documents before making changes. Keep the
entry point concise and put each policy in its owning feature document so the
compatibility entry points do not drift apart.

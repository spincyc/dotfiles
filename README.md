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

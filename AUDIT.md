# Dotfiles coverage audit (2026-07-28)

Compared the tracked repository with `/home/ksh`, `~/.config`, and the active ML4W tree. The repository intentionally tracks the portable layer and a small explicit ML4W overlay; it does not mirror the vendor tree.

## Current coverage

- Core portable files: `.zshrc` and `.tmux.conf` are tracked and installed as symlinks.
- ML4W: the legacy `2.9.9.5` profile tracks customized Hyprland, Kitty, SwayNC, and Waybar files, including the ultrawide host monitor/binding overlay.
- Vendor/generated state is excluded: caches, histories, completion dumps, theme/color outputs, wallpaper assets, updater state, and the full ML4W checkout.
- Secrets are excluded: SSH/GPG material, GitHub `hosts.yml`, WireGuard profiles, certificates, browser state, and cookies.

## Candidates outside Git

`~/.config/nvim/init.vim` and `~/.config/glow/glow.yml` are portable configuration and are the clearest optional overlays. `~/.gitconfig` is also portable only after review; the current file configures GitHub's `gh` credential helper and should not acquire identity, signing, or machine-specific paths. `~/.bash_profile` and `~/.bash_logout` are minimal and matter only if Bash is a supported login shell. `~/.config/gh/config.yml` is optional; `hosts.yml` must remain untracked because it contains credentials.

`mimeapps.list`, `user-dirs.dirs`, WireGuard GUI scripts, and the remaining regular files under `~/.config` are host-local application state, operational scripts, or sensitive state and should remain out of the repository unless explicitly reviewed.

## Arch Linux boundary

Pacman owns packaged programs and system files under `/usr` and `/etc`; it does not own this user's home configuration. This host currently has `hyprland 0.56.1-2`, `waybar 0.15.0-2`, `kitty 0.48.1-1`, and `neovim 0.12.4-1`; their `~/.config` files remain user-managed. Keep a separate reviewed package-name manifest (`pacman -Qqe`, with foreign/AUR packages recorded separately) rather than mixing package installation with dotfile deployment.

## Resolution

The Neovim and Glow overlays and the reviewed portable Git configuration are now
tracked and installed as core symlinks. Bash startup files and `gh` preferences
remain intentionally untracked until there is a demonstrated need to make them
cross-host policy. Do not expand the repository to include the ML4W vendor tree.

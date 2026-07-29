# dotfiles

A small, portable terminal profile plus an explicit, opt-in ML4W desktop
profile. The core manages Zsh and tmux. The desktop profile tracks reviewed
overrides and ML4W selector values rather than copying the unmodified vendor
tree into Git.

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

The core installer is idempotent. Existing core files are moved to timestamped
directories below `~/.local/state/dotfiles/backups/`; they are never silently
overwritten. The optional ML4W profile uses private copies in the same backup
hierarchy before atomic replacement.

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

Because the portable core files are symlinks, committed core changes take
effect as soon as they are pulled. Start a new shell with `exec zsh`; reload
tmux with `prefix + r`. Copied desktop payloads require another profile install
after a pull.

## ML4W legacy desktop profile

The profile in
`profiles/ml4w/legacy-2.9.9.5/` reconciles the reviewed preferences from the
legacy rolling ML4W installation without tracking its generated files, restored
duplicates, caches, wallpapers, or unmodified vendor tree. It requires:

- an active ML4W profile with ID `com.ml4w.dotfiles` and version `2.9.9.5`;
- the ML4W `config-custom` and `style-custom.css` extension points;
- `jq` and the standard utilities used by `install.sh`; and
- the semantic host profile `ultrawide-desktop`.

On Arch Linux, install the additional parser with:

```sh
sudo pacman -S --needed jq
```

Apply it with:

```sh
cd "$HOME/.dotfiles"
./install.sh --profile ml4w --host-profile ultrawide-desktop
```

Check both the desktop files and portable core without changing them:

```sh
./install.sh --check --profile ml4w \
  --host-profile ultrawide-desktop
```

Pull a fast-forward update and reapply both profiles:

```sh
./install.sh --update --profile ml4w \
  --host-profile ultrawide-desktop
```

`--update` is deliberately bound to a clean `main` worktree tracking
`spincyc/dotfiles` at `origin/main`; it refuses a different remote, branch, or
dirty tree before pulling.

Unlike the portable core links, the desktop payload is copied as regular files
into `~/.mydotfiles/com.ml4w.dotfiles/`. The strict manifest, ownership checks,
and exact ML4W version/schema gate prevent an overlay from being written into
an unreviewed layout. Differing desktop files are copied first to the same
private backup hierarchy used by the core installer, then atomically replaced.
This profile is not an ML4W installer or upgrader. ML4W and host packages must
already provide the referenced commands and schemas, including Quickshell,
Rofi, Waypaper, PulseAudio tools, Brightnessctl, Playerctl, Hyprlock, and the
configured applications.

Replacement is atomic per desktop file, but the 15-file manifest is not one
all-or-nothing transaction. If the process or session is interrupted, rerun
`--check` and then the install command; preserved backups retain the prior
content and mode.

Git is authoritative for all manifest-listed desktop files. Inline ML4W
Settings, Hyprland, or Waybar edits appear as drift; reconcile wanted changes
into this repository before reinstalling, because reinstall backs up and
replaces the deployed copy. After an ML4W update, run `--check`. If its
metadata or schema no longer passes, reconcile the profile for that release
instead of bypassing the gate. In particular, Git owns the custom Waybar module
list and geometry. ML4W may continue updating its generated palette and base
glass theme, but its module enable/disable switches do not rewrite the active
`config-custom`.

The desktop profile preserves the established physical Hyprland key chords,
removes the random-wallpaper action, disables Kitty's cursor trail, and keeps
machine-specific monitor and binding selections in the named host layer.
That host layer specifically selects built-in `eDP-1`, ultrawide `DP-3` at
`5120x1440@239.76Hz`, and the `tpacpi::kbd_backlight` device. Review it before
using the profile on different hardware.

The exact gate follows the active installer's `2.9.9.5` identity and
`.config/ml4w/version/name`, even though a later mixed rolling file reported a
`2.12.0` marker. The profile does not claim that the source tree was a pristine
release. Upstream identity and the mixed legacy baseline are documented in
`profiles/ml4w/legacy-2.9.9.5/PROVENANCE.md`; the derived payload's GPL boundary
is documented in `profiles/ml4w/legacy-2.9.9.5/LICENSES/README.md`.

Run the isolated installer regression suite with:

```sh
./tests/install.sh
```

It covers manifest deployment, idempotence, backups, drift, compatibility
gates, installer locking, core-parent isolation, and path/link safety. Any
`--check` command exits nonzero when it reports missing, unmanaged, or drifted
files.

## Local configuration

Put machine-specific settings and secrets in `~/.zshrc.local`. That file is
loaded automatically and must not be committed.

Keep credentials, SSH keys, shell history, caches, and generated completion
files outside this repository.

Machine-specific desktop values belong in a reviewed semantic host layer under
`profiles/`, not in `.zshrc.local`.

## Local verification

On Arch Linux, install every declared dependency:

```sh
make install-packages
```

Agents add newly required packages to the Makefile but leave this privileged
target for the user to run. Check the local environment and run the complete
verification suite with:

```sh
make sanity-check
make verify
```

## Local AI queue and journal

AIQ is maintained as a separate project. Install it from source, then let its
reversible integration lifecycle manage the Codex prompt hook:

```sh
git clone https://github.com/spincyc/aiq.git "$HOME/git/aiq"
make -C "$HOME/git/aiq" install-packages
pipx install "$HOME/git/aiq"
aiq integration plan codex --user
aiq integration install codex --user
aiq integration check codex --user
```

See the [AIQ source-install and integration
documentation](https://github.com/spincyc/aiq) for prerequisites, updates, and
uninstallation. This dotfiles installer provides personal agent guidance but
does not install AIQ or manage its integration files.

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

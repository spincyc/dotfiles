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

## ML4W desktop profile

The profiles under `profiles/ml4w/` reconcile the reviewed preferences from an
ML4W installation without tracking its generated files, restored duplicates,
caches, wallpapers, or unmodified vendor tree. Two layers are maintained:

| Layer | ML4W release | Hyprland configuration |
| --- | --- | --- |
| `legacy-2.9.9.5/` | `2.9.9.5` | hyprlang `.conf` |
| `2.15/` | `2.15` | Lua |

You do not choose between them. The installer selects the layer from the
Hyprland configuration format actually deployed: `hyprland.lua` picks the Lua
layer, `hyprland.conf` the hyprlang one, and Lua wins when both are present
because an upgrade leaves the old file behind. It deliberately does not read a
version marker - ML4W writes `config.dotinst` and `.config/ml4w/version/name`
once at first install and never rewrites them, and upstream ships
`.config/ml4w/version.json` stale, so no marker on disk identifies the
installed release.

Hyprland removes the `.conf` format in 0.57, which is why the Lua layer exists
ahead of the upgrade. `profiles/ml4w/MIGRATION.md` records the evidence, the
hyprlang-to-Lua mapping, and the remaining steps.

The profile requires:

- an active ML4W profile with ID `com.ml4w.dotfiles` and a supported version;
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

Replacement is atomic per desktop file, but the 16-file manifest is not one
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

The status bar runs as a vertical column on the left edge. On a 5120x1440
ultrawide the scarce axis is vertical, so the bar spends 80px of abundant
horizontal space instead of 37px of scarce vertical and windows keep the full
screen height. ML4W 2.15 defaults to a floating Quickshell strip across the
top; `.config/ml4w/settings/statusbar` selects Waybar instead and is tracked,
because that selector being untracked is how an upgrade silently replaced a
configured bar. Note that 2.15 also writes an empty
`.config/ml4w/settings/waybar-disabled` flag that suppresses Waybar entirely; a
manifest deploys files and cannot deploy an absence, so remove that file by
hand if a future upgrade restores it.

The bar adds privacy (microphone and screenshare), media, brightness, and CPU
temperature readouts, which depend on PipeWire, Playerctl, Brightnessctl, and
a `coretemp` hwmon source respectively.

The desktop profile preserves the established physical Hyprland key chords,
removes the random-wallpaper action, disables Kitty's cursor trail, pins Kitty's
two green palette slots so a generated low-contrast green cannot hide added
lines in `git diff`, and keeps machine-specific monitor and binding selections
in the named host layer.
That host layer specifically selects built-in `eDP-1`, ultrawide `DP-3` at
`5120x1440@239.76Hz`, and the `tpacpi::kbd_backlight` device. Review it before
using the profile on different hardware.

`config.dotinst` still identifies the profile, its upstream, and its subfolder,
and the gate checks all three; only its version field goes stale. Each layer's
`profile.conf` records the release it was derived from as provenance rather than
as something compared against the live tree. Neither profile claims that its
source tree was a pristine release. Upstream identity, the mixed legacy baseline, and the
derivation of the Lua layer are documented in each layer's `PROVENANCE.md`; the
derived payloads' GPL boundary is documented in each layer's
`LICENSES/README.md`.

Run the isolated installer regression suite with:

```sh
./tests/install.sh
```

It covers manifest deployment, idempotence, backups, drift, compatibility
gates, installer locking, core-parent isolation, and path/link safety. It
requires `jq`. Any `--check` command exits nonzero when it reports missing,
unmanaged, or drifted files.

## Agent workspaces: `wt`

`wt` runs an AI agent in a throwaway workspace under `~/git/worktrees`. A
workspace is a plain directory holding several independent clones, each parked
at `<owner>/<repo>`. It is not a repository, and it is not a `git worktree` of
a canonical clone under `~/git`; the clones inside it are independent, so work
done there never reaches the canonical checkouts.

```sh
wt claude feature/telos-sync    # create or reuse the workspace, run claude in it
wt codex feature/telos-sync     # the same workspace, a different agent
wt telos-sync                   # bare names take the feature/ prefix
```

Creating a workspace writes `AGENTS.md` there, with `CLAUDE.md` and
`GEMINI.md` deferring to it, so every agent is told to clone into that
directory owner-prefixed. The files are written once; `wt new --force`
rewrites them after the template changes.

```sh
wt ls                                   # every workspace and the repos it holds
wt clone feature/telos-sync spincyc/telos
wt status feature/telos-sync            # branch, cleanliness, ahead/behind
wt git feature/telos-sync -- log --oneline -3
wt fetch feature/telos-sync             # or pull, --ff-only
wt agents                               # occupied and free agent slots
wt check                                # environment and layout sanity check
wt rm feature/telos-sync                # refuses uncommitted, unpushed, or stashed work
```

A verb reads its first argument as the workspace when that workspace already
exists, or when the current directory is not inside one; otherwise it acts on
the workspace you are standing in. `wt` cannot change the calling shell's
directory, so use `cd "$(wt path feature/telos-sync)"`.

Concurrent agents are capped. Each launch holds one slot as an open `flock`
descriptor that survives the exec into the agent, so the kernel releases it
when the agent exits however it exits, and there is no stale state to clean
up. `wt agents` reports the slots; a launch past the cap is refused.

| Variable | Default | Purpose |
| --- | --- | --- |
| `WT_ROOT` | `~/git/worktrees` | Workspace root |
| `WT_NAMESPACE` | `feature` | Prefix applied to bare names |
| `WT_AGENT` | `claude` | Agent used when none is named |
| `WT_MAX_AGENTS` | `4` | Concurrent agent slots |
| `WT_FORGE` | `https://github.com` | Base URL for `owner/repo` clones |

Bare `owner/repo` clones go through `gh` when it is installed, so private
repositories need no separate credential setup; explicit URLs always go
through `git clone`.

`bin/wt` is a thin entry point over the `wt` package in `python/`, which the
installer links to `~/.local/lib/python/wt`. `.zshenv` puts that directory on
`PYTHONPATH`, so other scripts can reuse the pieces directly:

```python
from wt.config import Config
from wt import repos, workspaces

config = Config.from_env()
for workspace in workspaces.listing(config):
    print(workspace.name, [status.branch for status in workspace.statuses()])
```

The modules are separated so each is usable alone: `wt.config` settings,
`wt.names` name and path safety, `wt.gitcmd` a git runner, `wt.repos`
discovery and status, `wt.clone` clone specs, `wt.guidance` the workspace
documents, `wt.workspaces` creation and resolution, `wt.slots` the flock
concurrency limit, `wt.checks` the sanity check, and `wt.cli` the command
line. Nothing outside `wt.cli` prints.

Run the isolated `wt` suite, which uses temporary roots and local origins and
never touches `~/git` or the network, with:

```sh
./tests/wt.sh
```

## Local configuration

Put machine-specific settings and secrets in `~/.zshrc.local`. That file is
loaded automatically and must not be committed.

The managed `.zshenv` prepends `~/.local/bin` to `PATH` for every Zsh
invocation, so pipx-installed tools such as `aiq` and `tmt` resolve in
non-interactive shells, hooks, and agent sessions, not only in interactive
terminals. It also prepends `~/.local/lib/python` to `PYTHONPATH` for the
repository-managed Python packages, dropping empty entries so the current
directory never joins `sys.path` by accident.

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

The installer seeds `~/.claude/settings.json` from `claude/settings.json`
only when it does not exist and never overwrites it: Claude Code rewrites the
live file in place, and the AIQ and tmt integrations layer their own hook
groups onto it, so the live copy is runtime state that must not be symlinked
or reclaimed. `tools/claude-settings-check` reports drift between the seed's
base keys and the live file.

After pulling the document split for the first time, rerun `./install.sh` to
create the managed feature-directory links. For an agent that does not
automatically load repository instructions, ask it to read
`AI_GUIDANCE.md` and its numbered documents before making changes. Keep the
entry point concise and put each policy in its owning feature document so the
compatibility entry points do not drift apart.

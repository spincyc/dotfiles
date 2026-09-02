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
in the named host layer. A common `pipewire.conf.d` drop-in adds 44100 Hz to
`default.clock.allowed-rates`, so 44.1 kHz sources play at their own rate
instead of being resampled to the 48 kHz default.
That host layer specifically selects built-in `eDP-1`, the ultrawide by
description (`desc:Samsung Electric Company Odyssey G95C`) at
`5120x1440@239.76Hz`, and the `tpacpi::kbd_backlight` device. The ultrawide is
matched on its description rather than its DisplayPort connector name because
the connector re-enumerates across sessions, and the panel is pinned at
`5120x0` so it always sits to the right of the ultrawide at `0x0`. Review it
before using the profile on different hardware.

It also handles clamshell operation. With the lid shut, Hyprland stops driving
the built-in panel but leaves `eDP-1` enabled at a `0x0` mode positioned at
`0,0`, on top of the ultrawide's origin. Clients see a zero-size output covering the
ultrawide's corner, and Firefox constrains its menu popups to that empty
rectangle, so dropdown menus stop rendering entirely. The host monitor variant
therefore disables `eDP-1` outright while the lid is closed and restores it on
open, reconciling on startup and monitor hotplug as well as on the lid
transition, and never disabling the panel while it is the only monitor left.
No reconcile runs until Xwayland has been up for a full poll interval, or 15
seconds elapse: disabling an output destroys its `wl_output` global, and
destroying one while Xwayland binds the registry kills Xwayland, after which
every X11 client hangs forever connecting to `:0`. This adds two `Lid Switch`
binds and reads `/proc/acpi/button/lid/*/state` and `pgrep -x Xwayland`.

The same reconcile also repins the default audio sink, because the
`HiFi__HDMI1/2/3` sink names track ALSA PCM indices that rebind to physical
connectors on hotplug, so a stored default can silently point at a dead pin
while the sound server still reports it running. On every monitor add/remove,
`.config/hypr/scripts/default_sink_by_eld.sh` instead selects the display
sink whose `/proc/asound/card*/eld*` entry is valid, matching on the ELD
monitor name, and moves live streams to it.

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
workspace leaf is named `<project>/<slug>[/<child>...]` — the project the
work belongs to followed by the complete slug stack for one line of work —
and is a plain directory holding several independent clones, each parked at
`<owner>/<repo>`. It is not a repository, and it is not a `git worktree` of a
canonical clone under `~/git`; the clones inside it are independent, so work
done there never reaches the canonical checkouts.

```sh
wt claude telos/agent-sync      # create or reuse the workspace, run claude in it
wt codex telos/agent-sync       # the same workspace, a different agent
wt droid telos/agent-sync       # and a third
wt agent-sync                   # a bare slug takes $WT_PROJECT
```

The project only groups workspaces and names nothing on a forge; the
repositories a workspace holds are still cloned explicitly.

A launch can also hand the agent the prompt to open with, so that creating
the workspace and starting the work is one command rather than a launch
followed by a paste:

```sh
wt claude telos/agent-sync --seed 'read docs/PLAN.md and start at step 1'
wt claude telos/agent-sync --seed-file ./brief.txt   # the same, from a file
wt codex telos/agent-sync --seed-file -              # or from stdin
```

`--seed` and `--seed-file` are `wt`'s own and may be typed either side of the
workspace name. `--` ends them and hands everything after it to the agent
untouched, the way it does for `wt git` and `wt exec`, so an agent with a
`--seed` flag of its own is still reachable as `wt claude ws -- --seed x`. The
prompt is appended as the agent's trailing positional argument, which `claude`,
`codex` and `droid` each read as the prompt to open with. `wt` never echoes it
— a handoff is for the agent to read, not for the terminal to keep — and
reports only its length.

Prefer `--seed-file` for anything generated. Text written by another agent is
exactly what should not be interpreted by a shell on its way to the agent that
will act on it, and a file or a heredoc keeps it out of shell quoting
altogether. `-` reads stdin and then reopens the controlling terminal for the
agent, so a heredoc still leaves an interactive session to type into:

```sh
wt claude telos/agent-sync --seed-file - <<'PROMPT'
read https://raw.githubusercontent.com/spincyc/dotfiles/relay-v6/relay/PROTOCOL.md
and execute the brief it points at
PROMPT
```

Surrounding whitespace is stripped, and an empty prompt is refused rather than
launching an agent with nothing to do.

A launch continues where that agent left off. A workspace is one line of work,
so running the same agent in it again almost always means carrying on, and
`--new` is how you say otherwise:

```sh
wt claude telos/agent-sync          # resumes the last claude session here
wt claude --new telos/agent-sync    # starts a fresh one
wt codex telos/agent-sync           # codex resumes its own session, not that one
```

Resuming is the one place `wt` has to know an agent's own flags, because there
is no shared spelling for it and an agent asked to continue a session it never
had reports that instead of starting one. So `wt` notes which agents have run
in a workspace, in a `.wt-agents` file beside `.wt-workspace`, and offers each
of them the incantation it understands: `--continue` for `claude`,
`resume --last` for `codex`, `--resume` for `droid`. A first launch has nothing
to continue and is fresh; so is any agent not in that list, since guessing a
flag wrong costs a session that will not start. Losing the record costs a
resume and never work.

Only `claude` can be resumed and seeded at once. `codex resume` reads its first
positional as a session id and droid's `--resume` takes an optional session id,
so in both a seed prompt would be read as a session to resume; `wt` refuses
that combination and names `--new` rather than launching something that
resumes nothing. A `--relay` turn is the exception: its prompt is derived
rather than typed, so there is no combination for you to resolve and it opens
a fresh session, saying so. Every brief is self-sufficient at its pinned
commit, which is why the protocol calls `state: resume` a cost hint rather
than a requirement.

`--new` is also what to pass when you are driving the agent's own session
flags: `wt claude --new telos/agent-sync -- --resume <id>` picks the session
yourself, where without `--new` `wt` would add its `--continue` alongside.

### Opening a relay turn in one command

`--relay` is what a [`relay-v6`](relay/PROTOCOL.md) launch handoff invokes. It
takes a run pointer — the repository, and the commit the brief was published
in — and needs `-b` for the branch the handoff names:

```sh
wt claude relay/2026-09-02-01 -b feat/relay --relay spincyc/dotfiles@<40-hex sha>
```

`wt` creates the workspace pinned to that branch, clones the repository onto
it, fetches, finds the one brief that commit published, and reads the run, the
turn, the turn to claim, and the protocol version out of that brief's own
front matter.

It then **performs** the steps the protocol puts before the work rather than
describing them: workspace initialization, the pure fast-forward preflight
step 7 names, preflight itself, and the claim — which reaches `origin` before
any session starts. What the agent is finally handed is the brief at its
pinned bytes and the exact commands that publish the turn:

```
Everything the protocol puts before the work is done: the checkout is
initialized on feat/relay, preflight passed, and turn 002 is claimed and
published. Do not repeat any of it…

  relay prepare --protocol relay-v6 --branch feat/relay \
      --brief <sha> --brief-path .agent/runs/2026-09-02-01/001-brief.md
```

The result's front matter is given the same way — every field but `base` is
settled the moment the turn is claimed, so the agent is handed them rather
than left to derive them into a file that becomes immutable the moment it
reaches `origin`. Only the body, which is judgement, is left to the protocol's
own section.

That is the point of the form. A step described in prose is a step the agent
reconstructs, and a reconstructed step is where a run improvises; the brief is
the only thing left for it to read, and `wt` never summarises that.

Nothing is guessed. A pointer that is not `<owner>/<repo>@<40-hex sha>`, a
commit that publishes no brief or more than one, a brief whose `protocol:` is
not the one this build implements, or a `branch:` disagreeing with `-b` all
stop the launch and say which. That last one is the protocol's rule, not a
preference: the brief is the authority, and a difference there is a violation
to report rather than something to reconcile.

A stop the protocol names prints its blocked-channel line on stdout and exits
`3`, **before any agent session is opened** — a failed preflight or a replayed
claim used to cost a whole session to discover:

```
relay blocked 2026-09-02-01 002 claim-replay
```

Because a relay turn ends in something the user owes the planner, this is the
one launch `wt` waits for instead of becoming. When the session ends it checks
whether the result actually reached `origin` and prints the acknowledgement on
stdout, by itself so it can be copied:

```
wt: the relay-v6 session for run 2026-09-02-01 has ended, and .agent/runs/2026-09-02-01/002-result.md is at origin. Tell the planner:
done 2026-09-02-01 002
```

The acknowledgement still asserts only that the session ended — the planner
reads the result file itself and never infers an outcome. Saying whether the
file is there is for you, so you know before the planner asks whether to
expect a `relay blocked …` line instead. An unreachable `origin` is reported
as its own answer rather than as an absence, since a fetch that failed never
looked.

Ctrl-C belongs to the agent throughout: it reaches the whole foreground group,
the agent decides what it means, and `wt` simply waits again so it is still
there to make the report.

The next turn is the same command with the next brief's sha. It resumes the
session already holding the run rather than opening a second one, which is
what the protocol asks for and, for `codex` and `droid`, is why seeding a
resumed session is refused — pass `--new` there. `wt agents` names the run and
turn each worker is on, so several of them are told apart at a glance:

```
slot 1   agent=claude workspace=relay/2026-09-02-01 run=2026-09-02-01 turn=002 pid=… started=…
```

`--relay` needs the `relay` package, which the installer links alongside `wt`;
everything else in `wt` works without it.

Slug components can also group a replay stack. Treat the intermediate path as
a group and put each replay in its own leaf:

```sh
wt codex telos/agent-sync/replay-1
wt codex telos/agent-sync/replay-2
# branches: feature/agent-sync/replay-1 and feature/agent-sync/replay-2
```

This keeps every replay's directory, agent slot, and branch isolated. The
intermediate `telos/agent-sync` need not be a workspace itself. That matters
to Git: a branch named `feature/agent-sync` cannot coexist with a branch below
it such as `feature/agent-sync/replay-1`, while the sibling replay branches
above can coexist. `wt` therefore refuses to launch an intermediate group as
a workspace, and refuses to put a child below a path that is already a
workspace. Put any base pass in its own leaf, such as
`telos/agent-sync/baseline`.

`wt` records leaf and intermediate directories with small `.wt-workspace` and
`.wt-group` marker files. They let listing and current-directory detection
distinguish a stack group from a workspace without scanning into the clones.
Existing two-component workspaces need no migration; the next `wt new` or
launch that reuses one adds its leaf marker.

Every clone in a workspace works on one branch,
`feature/<slug>[/<child>...]`. `wt clone` creates it and, until it is
published, points it at the branch the clone arrived on, so `wt status` and
`wt sync` stay meaningful, `wt rm` can still tell saved work from unsaved,
and a bare `git push` refuses instead of sending the work to the default
branch. That refusal is why the managed `.gitconfig` pins
`push.default = simple` rather than trusting the Git default. Publishing is
therefore explicit: `wt push`, or `git push -u origin "$WT_BRANCH"` inside
one clone. `wt check` warns about a repository that has left the branch, and
`WT_BRANCH_PREFIX` renames the `feature` half.

One launch opens a whole line of work. `-b` names the branch, `-r` clones what
the work needs onto it, `-x` prepares it, and `--seed` says what to do there:

```sh
wt claude triptych/proper-54 -b impl/proper-54-production \
  -r spincyc/triptych --seed-file ~/p54.md \
  -x ./tools/tpt proper 54-fourteenth-after-pentecost seed --provider claude
```

That was four commands before these options existed — `wt new`, `wt clone -w`,
`wt exec -w`, then the launch — chained with `&&` and repeating the workspace
name each time.

`-r` is repeatable, takes anything `wt clone` takes (`owner/repo`, a URL, or a
path on this disk), and is a benign skip for a repository already there. A spec
`wt` cannot read an owner and repository out of is refused before the workspace
is created. `wt new` takes `-b` and `-r` the same way, for opening a workspace
without starting an agent.

`-x` (`--exec`) runs its command exactly where `wt exec` runs one: in every
clone, with `$WT_REPO` naming each, which is what makes a repository-relative
`./tools/…` resolve. It takes **the rest of the line**, because a command is a
list and there is no second separator to end one with — so it goes last, and
trailing words that look like `wt` options are the command's. A failing `-x`
stops the launch: nothing starts on a workspace that was only half prepared.
It is a launch option only, since a terminal option on `wt new` would swallow
the workspace name people put last.

Running the setup step here rather than asking the agent to run it is the same
argument as everywhere else in `wt`: a step described to an agent is a step it
has to get right, and this one either worked or the launch stopped.

`-b` (`--branch`) works on `wt new`, `wt clone` and a launch, and is recorded
in the workspace's `.wt-workspace`, so a workspace can work on a branch it did
not derive:

```sh
wt new -b relay/2026-09-02-01 telos/relay-run
wt clone telos/relay-run spincyc/telos   # lands on relay/2026-09-02-01
wt claude telos/relay-run                # so does everything after it
```

That is what every verb then means by "the workspace branch": the guidance
written into `AGENTS.md`, the branch `wt clone` checks out, the one `wt push`
publishes and `wt status` compares against, and the one `wt check` warns a
clone has left. Without it a run on someone else's branch leaves every clone
permanently "off the workspace branch", which makes `wt push` skip it and the
upstream column say the wrong thing.

The branch is chosen when the workspace is created and not afterwards: naming
a different one for an existing workspace is refused, since the clones already
in it are on the branch it was created with. Naming the one it already works on
is not a change and is allowed.

`wt push` publishes only where there is something to publish: it skips a
clone that has left the workspace branch, and one whose commits a remote
already has. A blanket `git push -u` across the workspace would create a
remote branch for every clone the agent never touched and retarget their
upstreams, after which the upstream column of `wt status` could no longer
say which clone holds the work.

Creating a workspace writes `AGENTS.md` there, with `CLAUDE.md` and
`GEMINI.md` deferring to it, so every agent is told to clone into that
directory owner-prefixed and to commit on the workspace branch. `droid` reads
`AGENTS.md` itself and needs no pointer of its own. The files are
written once; `wt new --force [<workspace>]` rewrites them after the template
changes, so an existing workspace keeps the instructions it was created with
until then.

That guidance also gives transient work a home. Notes, logs, scratch scripts,
downloaded samples, and experiment output belong under `.scratch`, in two
places and no others: `<workspace>/.scratch` for anything that is not about
one repository, and `<owner>/<repo>/.scratch` at the top of a clone. `wt
clone` adds `.scratch/` to each new clone's `.git/info/exclude`, so scratch
there stays out of `git status`, out of `git add .`, and out of the way of
`wt sweep`. That exclusion is local and is never committed, so it costs the
cloned repository nothing. A clone made by hand has none until a real
`wt tidy` gives it one, and a repository that already tracks something under
`.scratch` is not covered at all — `wt tidy` reports those and leaves them
alone. `wt tidy` is what empties the rest.

A workspace keeps no work ledger. `wt` exports `AIQ_DISABLE=1` into the agent,
which switches the installed AIQ hooks off for that session, and the workspace
guidance plus [`ai-guidance/10-journal.md`](ai-guidance/10-journal.md) and
[`15-tool-making.md`](ai-guidance/15-tool-making.md) tell the agent not to use
`aiq` or `tmt` there. Both halves are needed: the environment variable stops
prompt capture and the completion gate, and the guidance stops the agent
looking for work state that is deliberately absent. Without the variable a
workspace root, not being a Git repository, would fall back to AIQ's user
scope and capture every prompt.

`AIQ_DISABLE` needs an AIQ newer than `0.3.0a1`, currently only from source. An
older AIQ ignores the variable and keeps capturing, so until the installed AIQ
is refreshed the guidance half works and the mechanical half does not. Check
with `aiq --version`, and see the AIQ changelog before upgrading across a
release: `aiq doctor` reports the switch on its `capture` line once it is
supported.

```sh
wt claude proj/slug -b impl/x -r own/repo --seed-file ./b.md -x ./setup.sh
wt ls                                   # every workspace and the repos it holds
wt ls -q                                # bare names, one per line, for scripts
wt clone telos/agent-sync spincyc/telos # cloned onto feature/agent-sync
wt clone -w telos/agent-sync ~/git/spincyc/telos   # or from a path on this disk
wt clone -w telos/agent-sync -o spincyc ~/mirror/telos  # naming the owner
wt pwd                                  # the workspace holding this directory
wt branch telos/agent-sync              # the workspace branch
wt status telos/agent-sync              # branch, upstream, cleanliness, ahead/behind
wt status -q telos/agent-sync           # one tab-separated line per repo
wt log telos/agent-sync                 # the commits of this line of work
wt git telos/agent-sync -- log --oneline -3
wt exec telos/agent-sync -- rg -n TODO  # any command, in every clone
wt fetch telos/agent-sync               # git fetch --prune in every clone
wt sync telos/agent-sync                # fetch, then rebase onto the default branch
wt push telos/agent-sync                # publish where there is work to publish
wt agents                               # the agents running right now
wt check                                # environment and layout sanity check
wt rm telos/agent-sync                  # refuses uncommitted, unpushed, or stashed work
wt sweep --dry-run                      # the workspaces a sweep would remove
wt tidy --dry-run telos/agent-sync      # what tidy would delete, ignored files too
```

An existing workspace does not require an exact full-name spelling. `wt`
accepts its full branch (`feature/agent-sync/replay-1`), its slug stack without
the project (`agent-sync/replay-1`), a unique final slug (`replay-1`), or an
unambiguous component prefix (`tel/ag/repl-1`). Matching ignores case and the
differences among `-`, `_`, and `.`. Exact full workspace names win first; a
short selector that matches more than one leaf is refused and prints every
candidate. Commands that can create a workspace still create a selector that
matches nothing, so use `wt new` when a deliberately new name is a prefix of
an existing one.

`wt sync` fetches and rebases each clone onto its default branch. `wt pull`
is deliberately *not* an alias for it: `git pull --ff-only` never rewrote
anything, `sync` rebases, and pointing fifteen years of muscle memory at a
history rewrite without asking is not a rename. `wt pull` refuses and names
`wt sync` instead.

`wt clone` reads `owner/repo`, a URL, or a path on this disk — `/…`, `~/…`,
`./…` or `../…` — and clones a local path from where it is, which is both
legitimate and faster than going back to the forge. Because a clone spec and
a workspace name look alike, `clone` takes `-w <workspace>` to name one
explicitly rather than guessing.

A verb reads its first argument as the workspace when that workspace already
exists, or when the current directory is not inside one; otherwise it acts on
the workspace you are standing in. `wt pwd` is the exception that never reads
an argument: it answers *where am I*, printing the root of the workspace the
current directory belongs to and failing outside `WT_ROOT`. `new`, `sweep`
and `tidy` never infer: they take a workspace name or none at all, `sweep`
and `tidy` fail on a name that does not exist, and `wt sweep` inside a
workspace still considers all of them, keeping the one you are standing in.
`wt` cannot change the calling shell's directory, so `.zshrc` defines `wtcd`
over it: `wtcd telos/agent-sync` goes to that workspace and a bare `wtcd`
climbs to the top of the one you are already in, over `cd "$(wt path ...)"`
and `cd "$(wt pwd)"`. It is a separate name on purpose — shadowing `wt` with
a shell function would break `command -v wt`, non-interactive callers, and
the workspace guidance that tells agents to invoke `wt` directly.

Zsh completion lives in `zsh/_wt`, which `.zshrc` puts on `fpath` from this
checkout, so it needs no reinstall and has no `managed_links` entry:
completions are Zsh-only, unlike the `bin/` tools. It completes the verbs
and, more usefully, canonical workspace names taken live from `wt ls -q`. On a
launch it also completes `--new`, `--seed` and `--seed-file`, and files after
`--seed-file`.

`--force` (`-f`) and `--dry-run` (`-n`) are read from wherever in the
arguments they were typed, so `wt rm telos/demo -f` works as readily as
`wt rm -f telos/demo`.

`wt rm` and `wt sweep` divide the work of throwing a workspace away. `wt rm`
disposes of one named workspace and takes `--force`; `wt sweep` sweeps, and
with no argument considers every workspace under `WT_ROOT`. It removes each
workspace whose work is already saved, by the test `wt rm` uses: nothing
uncommitted and nothing untracked, since a stray untracked file counts as
work; nothing stashed; and every local branch has an upstream it is not
ahead of. It keeps, and reports the reason for, any workspace that holds
unsaved work, currently runs an agent, contains the current directory, or
holds anything `wt` cannot account for — a clone at the wrong depth, or a
file left at the top instead of under `.scratch`. It then
removes any project directory it has emptied, and exits nonzero if it refused
a workspace outright, as it does for one reached through a symlink. It has no
`--force`: discarding unsaved work stays an explicit, single-workspace
decision. `--dry-run` (or `-n`) reports what it would remove and removes
nothing.

`wt tidy` deletes Git-ignored files as well as `.scratch`, and ignored does
not mean disposable — a virtualenv and `node_modules` cost time to rebuild,
and a local `.env` may not be recoverable at all — so run `--dry-run` first.
It keeps the workspace and deletes the workspace's own `.scratch`, each
clone's `.scratch`, and every ignored file in each clone through
`git clean -Xd`, which leaves tracked files, unignored untracked files, and
nested repositories alone. A `.scratch` the repository tracks is reported and
kept, and a clone that is only a symlink is skipped. A real run also gives
each clone the `.scratch/` exclusion if it is missing, before deleting
anything; `--dry-run` writes nothing at all. Given a workspace it tidies that
one, otherwise the workspace you are standing in, otherwise every workspace;
either way it spares a workspace with an agent running in it, unless that
workspace is the one you are standing in.

Nothing caps how many agents run at once: that is decided by how many you
start. Each launch does take a slot in `$WT_ROOT/.agents`, held as an open
`flock` descriptor that survives the exec into the agent, so the kernel
releases it when the agent exits however it exits, and there is no stale
state to clean up. The slot is not a quota; it is how `wt tidy`, `wt sweep`
and `wt rm` know a workspace is occupied, and `wt agents` lists what is
running. A registry `wt` cannot read stops those three verbs outright, since
an unreadable registry is not an empty one.

The exit statuses are the ordinary ones: 2 for a usage error, 1 for a
failure, 130 for an interrupt, and 141 for a closed pipe, so `wt ls | head`
stays quiet. A relay launch adds 3, for a stop the protocol's blocked channel
names, matching `relay`'s own code for it.

| Variable | Default | Purpose |
| --- | --- | --- |
| `WT_ROOT` | `~/git/worktrees` | Workspace root |
| `WT_PROJECT` | none | Project applied to a bare slug |
| `WT_BRANCH_PREFIX` | `feature` | Prefix of the workspace branch |
| `WT_AGENT` | `claude` | Agent used when none is named |
| `WT_FORGE` | `https://github.com` | Base URL for `owner/repo` clones |

`WT_ROOT` is the only location in the contract: everything `wt` creates lives
under it, the agent slots included, in `$WT_ROOT/.agents`. Two shells pointed
at different roots therefore keep separate registries, and neither can report
an agent running in the other's workspaces.

Bare `owner/repo` clones go through `gh` when it is installed, so private
repositories need no separate credential setup; explicit URLs and local
paths always go through `git clone`.

Five variables go the other way, exported into the agent `wt` launches and
into nothing else — a shell you opened yourself has none of them:

| Variable | Value |
| --- | --- |
| `WT_WORKSPACE` | The complete workspace leaf name |
| `WT_WORKSPACE_DIR` | Its absolute path, the directory the agent starts in |
| `WT_BRANCH` | The workspace branch, for `git push -u origin "$WT_BRANCH"` |
| `WT_AGENT_SLOT` | Which agent slot this session holds |
| `AIQ_DISABLE` | Set to `1`: a workspace keeps no work ledger |

The package needs Python 3.11 or newer (`enum.StrEnum`).

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
`wt.errors` the user-facing error types, `wt.names` name and path safety,
`wt.gitcmd` a git runner, `wt.repos` discovery, status, the default branch
and the questions that decide whether a clone holds unsaved work,
`wt.branches` the workspace branch and its upstream, `wt.clone` clone specs
including local paths, `wt.guidance` the workspace documents, `wt.scratch`
the `.scratch` convention and its local Git exclusion, `wt.sessions` which
agents have run in a workspace and how each is asked to continue,
`wt.workspaces` creation, resolution and the one disposal gate every
destructive verb goes through, `wt.slots` the flock registry of running
agents, `wt.checks` the
sanity check, and `wt.cli` the command line, whose `agent_environment` is the
exported-variable contract above. Nothing outside `wt.cli` prints: the only
output another module produces is a child git's own, on the terminal it was
handed.

Run the isolated `wt` suites, which use temporary roots and local origins and
never touch `~/git`, your real `HOME`, or the network, with:

```sh
./tests/wt.sh        # end to end, through bin/wt
./tests/wt_unit.py   # the seams a shell cannot reach
```

`make verify` runs both. The unit suite covers what a shell test cannot: the
`LC_ALL=C` pin that keeps `git clean` parseable, the slot survey and what it
refuses to guess, and the unsaved-work oracle failing closed on a repository
git cannot read.

## Agent relay: `relay`

`relay` performs the mechanical steps of the agent relay protocol documented
in [`relay/PROTOCOL.md`](relay/PROTOCOL.md). A relay run pairs a planning
agent that reaches the repository only through git with an executing CLI
agent that has a shell; they trade turns as files on the work branch. Most of
what the protocol asks of the executor is git bookkeeping — is the tree
clean, is the branch the one I was sent to, has origin moved under me, which
turn number am I allowed to write. `relay` makes those steps deterministic,
so preflight, sync, claim, and publish are exit codes rather than prose
followed by hand.

```sh
relay init        # switch a fresh checkout onto the branch the handoff names
relay preflight   # the every-turn checks, before any edit
relay sync        # reconcile with origin, preserving intentional merges
relay claim       # take the turn by pushing its claim file
relay prepare     # sync, re-verify the pinned brief, print the final shas
relay publish     # commit the written result and push work and result together
relay lint        # check turn files against the protocol's grammar
relay --version   # the protocol version this build implements
```

It runs inside whatever repository a relay run targets, not only inside this
one, so the installer links `bin/relay` to `~/.local/bin/relay` and the
`relay` package to `~/.local/lib/python/relay`, the same pair `wt` uses.

Each build is pinned to exactly one protocol version. `--protocol` states the
version a caller expects, and `relay` refuses a mismatch rather than
half-implementing another revision; `relay --version` reports the one it
implements.

The document is immutable per version, so each version is tagged at the commit
that completed it — `relay-v1` through `relay-v6` — and the tag is what the
canonical URL pins. A planner is given the URL of the version its run will
use, and both sides then read identical rules. Releasing a version is
therefore an annotated tag on the commit where the document, the templates and
the tool agree, not a branch to maintain.

`relay-v6` adds the launch handoff: alongside the portable `#` line the
planner may emit one command the user runs directly.

```
wt claude relay/2026-09-02-01 -b feat/relay --relay spincyc/dotfiles@<40-hex sha>
```

That line carries no brief, no prompt, and no prose — only a workspace, a
branch, a repository, and the commit the brief was published in. Everything
else, including the prompt itself, `wt` derives from the brief's own front
matter at that commit, which is what keeps generated text out of shell
quoting. The portable line is still emitted for every turn and is still
sufficient on its own, so a machine without `wt` loses nothing.

The exit statuses carry the outcome: `0` success, `2` a usage error, `3`
blocked, and `5` lint findings. A blocked run prints a `blocked: <token>`
line naming which precondition stopped it, so the caller can act on the token
instead of parsing the message.

## Agent status lines: `agent-statusline`

The terminal agents installed here show the same facts in the same order, so
switching between them costs no re-reading:

```
~/git/dotfiles · main* · gpt-5.6-sol xhigh · Context 100% left
```

The fields are the working directory, the Git branch with `*` when the tree is
dirty, the model with its reasoning level, and how much of the context window
is still free.

Codex builds that line itself from a fixed item set, selected in
`~/.codex/config.toml` (`/statusline` writes the same key):

```toml
[tui]
status_line = ["current-dir", "git-branch", "model-with-reasoning", "context-remaining"]
```

Claude Code and Droid instead spawn a command and pipe a JSON snapshot of the
session to it. `bin/agent-statusline` reads either payload — the two differ in
shape, and Droid reports the context share used where Claude Code reports the
share left — and prints the line above, copying Codex's separator and wording.
The installer links it to `~/.local/bin/agent-statusline`, which both hosts
reference through `$HOME` so the setting stays portable:

```json
"statusLine": { "type": "command", "command": "$HOME/.local/bin/agent-statusline" }
```

That block lives in `claude/settings.json` for Claude Code, so a fresh machine
is seeded with it, and in `~/.factory/settings.json` for Droid. `droid
statusline-probe` runs the configured command under Droid's own execution
budget and reports what it rendered, which is the cheapest check after an edit.

A field the host does not report is dropped rather than faked: Claude Code
sends no reasoning level for models that have none, and no branch shows
outside a repository. Set `NO_COLOR` to get the same line unstyled.

OpenCode is not wired up. It renders its status bar internally and exposes no
command or item selection to configure, so there is nothing to align.

## Local configuration

Put machine-specific settings and secrets in `~/.zshrc.local`. That file is
loaded automatically and must not be committed.

The managed `.zshenv` prepends `~/.local/bin` to `PATH` for every Zsh
invocation, so pipx-installed tools such as `aiq` and `tmt` resolve in
non-interactive shells, hooks, and agent sessions, not only in interactive
terminals.

It also *appends* this repository's own `bin/` directory, so a tool added
there is on `PATH` in the next Zsh shell with no reinstall. That is a
convenience, not a substitute for installing it: a tool meant to be a
portable command still gets a `managed_links` entry, which is what makes it
resolve outside Zsh and puts it in `~/.local/bin` ahead of this entry. `wt`
has both. The location is resolved from `.zshenv` through its symlink, so the
checkout works wherever it lives. Appending rather than prepending keeps
repository tools from shadowing a system command of the same name; a tool
that must win needs an explicit `~/.local/bin` link. Two consequences worth
knowing: anything executable that lands in `bin/` becomes a command, including
on a branch checkout, and `tools/` is deliberately left off `PATH` because
those are repository checks run as `tools/<id>` or through `make`, with names
like `verify` that should not become global commands. It also prepends
`~/.local/lib/python` to `PYTHONPATH` for the repository-managed Python
packages, dropping empty entries so the current directory never joins
`sys.path` by accident.

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

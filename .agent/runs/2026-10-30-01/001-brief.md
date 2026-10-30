---
protocol: relay-v6
run: 2026-10-30-01
turn: 001
role: planner
agent: droid
subagents: 0
branch: fix/kitty-repaint-delay
base: 772c642f00691b93c44b3d6e85470a1bb6512880
---

Objective: On the ML4W desktop, a kitty window showing a tmux session over
SSH stops showing stale panes, late refreshes, and half-drawn frames while
terminal UIs stream output and while the user switches tmux panes and
windows. The fix is a kitty profile setting the user has confirmed by eye.

Scope boundary: The executor owns
`profiles/ml4w/2.15/common/.config/kitty/custom.conf` and the `README.md`
paragraph that lists the desktop profile's Kitty overrides. Do not change
`.tmux.conf`, any other profile file, any manifest, or the `legacy-2.9.9.5`
profile. The user has not authorized deployment: do not run `./install.sh`
in any mode, and do not edit the live kitty configuration in the home
directory. Starting a separate kitty process with a command-line `-o`
override for the comparison below is in scope, because it changes no file.

Acceptance criteria:

1. The result records `kitty --version`, `$XDG_SESSION_TYPE`, and the
   effective `repaint_delay` and `sync_to_monitor` of the live
   configuration, as printed by the first verification command. Work
   proceeds only when kitty is 0.49.2 or a later 0.49.x release, the session
   type is `wayland`, `repaint_delay` is nonzero, and `sync_to_monitor` is
   `True`.
2. The user compares two kitty windows, each connected over SSH to the tmux
   host and attached to the same session, while terminal UIs stream output
   and while switching panes and windows. One is an ordinary kitty window;
   the executor starts the other, detached, with `kitty -o repaint_delay=0`.
   The result quotes the user's verdict. Only the user's verdict decides;
   the executor cannot see the display.
3. Only if the user reports that the `repaint_delay=0` window fixes or
   clearly reduces the problem: `custom.conf` sets `repaint_delay 0` under a
   comment in the file's existing style that states the reason and the
   removal condition from Context.
4. In that case, the `README.md` paragraph listing the desktop profile's
   Kitty overrides also names the repaint-delay workaround and when to
   remove it.
5. The result tells the user that the deployed desktop copy changes only
   after they run
   `./install.sh --profile ml4w --host-profile ultrawide-desktop`
   themselves.

Verification:

- Live configuration, read-only, before any change:
  `kitty +runpy 'import os; from kitty.config import load_config; o = load_config(os.path.expanduser("~/.config/kitty/kitty.conf")); print(o.repaint_delay, o.sync_to_monitor)'`
- The payload after the change prints `0 True`:
  `kitty +runpy 'import sys; from kitty.config import load_config; o = load_config(sys.argv[-1]); print(o.repaint_delay, o.sync_to_monitor)' profiles/ml4w/2.15/common/.config/kitty/custom.conf`
- `sh -n tests/install.sh && ./tests/install.sh`
- `git diff --cached --check` on the staged change before committing.

Delegation plan: 0. The change is one configuration line and one README
paragraph, gated on the user's visual verdict. There is no parallel-safe
second lane, and a delegate cannot see the display either.

Context:

- `AGENTS.md` defers to `AI_GUIDANCE.md`; its dotfiles rules govern this
  work, including documenting changes to managed files.
- The diagnosis is settled and binds this run: the fault is in kitty, not
  tmux. kitty 0.49.2 began parsing small program output immediately
  (upstream pull request 10560), which exposes this bug: on Wayland with
  `sync_to_monitor` on, a window that is waiting for a render frame still
  resets its last-render time, so a frame that arrives within
  `repaint_delay` is ignored and the window is painted only by the next
  program output, sometimes in the middle of an update. Upstream fixed this
  in kovidgoyal/kitty commit `6294070d06423682a3c22ba535aa4a816f361bc2`
  (issue 10749), which no release up to 0.49.2 contains. With
  `repaint_delay 0` the check that drops that paint never applies.
- Removal condition for the comment and the README note: kitty 0.50.0, or
  any build that contains that upstream commit.
- Copied desktop payloads change only on a profile install, per
  `README.md`; this run changes the repository only.

When blocked: If any precondition in criterion 1 fails, or the user sees no
improvement in the `repaint_delay=0` window, change nothing outside the run
directory and report `status: blocked` with the observed values or the
user's description in `needs:`. Do not try other kitty options, tmux
settings, or a deployment in search of a fix; the planner decides the next
step.

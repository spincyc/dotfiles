#!/bin/sh
# Isolated checks for bin/wt. Everything happens under a temporary root with
# local origins and a temporary home, so the suite never touches ~/git, the
# developer's Git configuration, or the network.
set -eu

# Git's environment outranks every config file, so pinning the files is only
# half the job. GIT_DIR is exported by every git hook and by the bare-repo
# dotfiles idiom; GIT_INDEX_FILE by every hook. Each one aims the suite's git
# at a repository that is not the one under test, and the failures land as
# bare `fatal:` lines before the harness can attribute them.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY \
  GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_COMMON_DIR GIT_NAMESPACE \
  GIT_TEMPLATE_DIR GIT_CONFIG GIT_CONFIG_COUNT

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
wt="$repo_dir/bin/wt"
test_root=$(mktemp -d "${TMPDIR:-/tmp}/dotfiles-wt-test.XXXXXX")
# Resolved once, here: the fake agent reports `pwd -P`, and on any system
# where TMPDIR reaches through a symlink — /var on macOS — an unresolved
# root would never match it.
test_root=$(CDPATH= cd -- "$test_root" && pwd -P)
origins="$test_root/origins"
work="$test_root/worktrees"
state="$test_root/state"
fake_bin="$test_root/bin"
home="$test_root/home"
gitconfig="$home/gitconfig"

cleanup() {
  # A held agent waits for a sentinel under $test_root; removing the root
  # without releasing it would leave the process spinning forever.
  : >"$test_root/slow-release" 2>/dev/null || true
  kill "${first_agent:-}" "${second_agent:-}" 2>/dev/null || true
  case "$test_root" in
    "${TMPDIR:-/tmp}"/dotfiles-wt-test.*)
      # A failure takes its evidence with it: the tree the check ran
      # against is deleted before anyone can look at it. WT_TEST_KEEP=1
      # keeps it and says where, for the one run you are debugging.
      if [ -n "${WT_TEST_KEEP:-}" ]; then
        printf 'kept %s\n' "$test_root" >&2
      else
        rm -rf -- "$test_root"
      fi
      ;;
    *)
      printf 'refusing to remove unexpected test path: %s\n' \
        "$test_root" >&2
      ;;
  esac
}

trap cleanup 0
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

fail() {
  printf 'not ok - %s\n' "$*" >&2
  exit 1
}

# The one place the suite's environment is built. Every wt and every git the
# suite runs goes through here, so the isolation cannot be forgotten: a real
# ~/.gitconfig carrying core.excludesFile, commit.gpgsign, core.hooksPath,
# init.templateDir, or url.*.insteadOf otherwise reaches into every temporary
# repository and can break the suite before its first section.
env_run() {
  HOME="$home" \
  XDG_CONFIG_HOME="$home/.config" \
  XDG_STATE_HOME="$state" \
  GIT_CONFIG_GLOBAL="$gitconfig" \
  GIT_CONFIG_NOSYSTEM=1 \
  GIT_ATTR_NOSYSTEM=1 \
  GIT_TERMINAL_PROMPT=0 \
  GIT_ASKPASS=/bin/false \
  WT_ROOT="${wt_root:-$work}" \
  WT_AGENT="${wt_agent:-fake-agent}" \
  WT_PROJECT="${wt_project:-}" \
  WT_BRANCH_PREFIX="${wt_branch_prefix:-feature}" \
  WT_FORGE="${wt_forge:-file://$origins}" \
  PATH="$fake_bin:$PATH" \
    "$@"
}

# gh is bypassed by giving every clone an explicit file:// URL or local path,
# so the suite stays offline and independent of the caller's credentials.
wt_run() {
  env_run "$wt" "$@"
}

# wt run from somewhere else, under the same isolated environment. Building
# the environment inline at each call site is how a piece of it gets left out.
wt_at() {
  wt_at_dir=$1
  shift
  (cd -- "$wt_at_dir" && wt_run "$@")
}

# Every git in the suite, isolated the same way. `command` keeps this from
# calling itself.
git() {
  env_run command git "$@"
}

branch_of() {
  git -C "$1" rev-parse --abbrev-ref HEAD
}

upstream_of() {
  git -C "$1" rev-parse --abbrev-ref '@{upstream}' 2>/dev/null || printf 'none'
}

assert_contains() {
  printf '%s' "$1" | grep -Fq -- "$2" ||
    fail "output does not contain: $2"
}

# The stand-in agent prints its arguments last, so this is the whole of what
# a launch handed it. A workspace named for the test would otherwise match
# these greps through the workspace= field.
agent_args() {
  # Anchored on the stand-in's own line: a setup command's output can carry
  # an args= of its own, and an unanchored match would splice the two.
  printf '%s\n' "$1" | sed -n 's/^agent=.* args=//p'
}
assert_agent_args() {
  [ "$(agent_args "$1")" = "$2" ] || {
    printf 'not ok - agent arguments were %s, not %s\n' \
      "$(agent_args "$1")" "$2"
    exit 1
  }
}

assert_missing() {
  printf '%s' "$1" | grep -Fq -- "$2" &&
    fail "output unexpectedly contains: $2"
  return 0
}

# An anchored, whole-line match, for the reports where a bare substring says
# nothing about which repository or workspace it came from.
assert_matches() {
  printf '%s\n' "$1" | grep -Eq -- "$2" ||
    fail "output has no line matching: $2"
}

assert_status() {
  assert_status_want=$1
  shift
  assert_status_got=0
  "$@" >/dev/null 2>&1 || assert_status_got=$?
  [ "$assert_status_got" -eq "$assert_status_want" ] ||
    fail "expected exit $assert_status_want, got $assert_status_got: $*"
}

# POSIX sleep counts whole seconds, so each poll costs one; the condition is
# tested first, and one that already holds costs nothing at all.
wait_for() {
  wait_for_left=30
  until eval "$1"; do
    wait_for_left=$((wait_for_left - 1))
    [ "$wait_for_left" -gt 0 ] || fail "timed out waiting for: $1"
    sleep 1
  done
}

make_origin() {
  origin_name=$1
  origin_path="$origins/$origin_name"
  mkdir -p -- "$origin_path"
  git init --quiet --bare -- "$origin_path"
  seed="$test_root/seed-$(printf '%s' "$origin_name" | tr / -)"
  git init --quiet -- "$seed"
  git -C "$seed" config user.email wt-test@example.invalid
  git -C "$seed" config user.name 'wt test'
  printf 'seed\n' >"$seed/README.md"
  git -C "$seed" add README.md
  git -C "$seed" commit --quiet -m 'seed'
  git -C "$seed" branch -M main
  git -C "$seed" remote add origin "file://$origin_path"
  git -C "$seed" push --quiet -u origin main
  # The bare repository's default HEAD may still name another branch, which
  # would leave every clone without a checkout.
  git -C "$origin_path" symbolic-ref HEAD refs/heads/main
  rm -rf -- "$seed"
}

command -v git >/dev/null 2>&1 || fail "git is required"
command -v flock >/dev/null 2>&1 || fail "flock is required"

mkdir -p -- "$origins" "$state" "$fake_bin" "$home/.config"

# The temporary home's Git configuration: an identity for the commits the
# suite makes, and nothing else. GIT_CONFIG_GLOBAL and GIT_CONFIG_NOSYSTEM
# keep the real global and system files out of reach entirely, so no setting
# has to be counteracted one key at a time.
cat >"$gitconfig" <<'EOF'
[user]
  name = wt test
  email = wt-test@example.invalid
[init]
  defaultBranch = main
[commit]
  gpgsign = false
[tag]
  gpgsign = false
[advice]
  detachedHead = false
[protocol "file"]
  allow = always
EOF

# A stand-in agent that records where it was launched and what it received.
cat >"$fake_bin/fake-agent" <<'EOF'
#!/bin/sh
printf 'agent=%s cwd=%s slot=%s workspace=%s dir=%s branch=%s aiq_disable=%s args=%s\n' \
  "$(basename -- "$0")" "$(pwd -P)" "${WT_AGENT_SLOT:-}" "${WT_WORKSPACE:-}" \
  "${WT_WORKSPACE_DIR:-}" "${WT_BRANCH:-}" "${AIQ_DISABLE:-unset}" "$*"
EOF
chmod 755 -- "$fake_bin/fake-agent"

# Stand-ins for the installed agents. Without them the suite passes only on a
# machine that happens to have a real claude, codex, or droid, and `wt check`
# fails on a clean CI box for a reason that has nothing to do with wt.
for agent_name in claude codex droid; do
  # A plain copy is enough now that the script reports its own $0: identical
  # copies that said nothing made `wt claude X` and `wt X` indistinguishable,
  # so the dispatch test could not fail.
  cp -- "$fake_bin/fake-agent" "$fake_bin/$agent_name"
  chmod 755 -- "$fake_bin/$agent_name"
done

# A stand-in gh. Bare owner/repo clones are the one path that would otherwise
# reach the network, so this serves them from the local origins instead and
# refuses everything else: the suite stays offline by construction rather
# than by never exercising the path.
cat >"$fake_bin/gh" <<EOF
#!/bin/sh
if [ "\$1" = repo ] && [ "\$2" = clone ]; then
  exec git clone --quiet -- "file://$origins/\$3" "\$4"
fi
printf 'gh: the wt suite is offline: %s\n' "\$*" >&2
exit 1
EOF
chmod 755 -- "$fake_bin/gh"

# A stand-in agent that holds its slot until a sentinel file appears. Each
# one announces itself under its own slot number: a single shared sentinel
# cannot tell one agent having started from both of them having started.
cat >"$fake_bin/slow-agent" <<EOF
#!/bin/sh
printf 'started\n' >"$test_root/slow-started-\${WT_AGENT_SLOT:-0}"
while [ ! -e "$test_root/slow-release" ]; do
  sleep 1
done
EOF
chmod 755 -- "$fake_bin/slow-agent"

make_origin spincyc/alpha
make_origin spincyc/beta

printf '# usage and dispatch\n'
usage_out=$(wt_run help)
assert_contains "$usage_out" 'wt claude telos/agent-sync'
assert_contains "$usage_out" 'feature/<slug>'
if bad_option=$(wt_run --nope 2>&1); then
  fail "unknown option was accepted"
fi
assert_contains "$bad_option" 'unknown option: --nope'

printf '# workspace creation seeds guidance\n'
created=$(wt_run new telos/demo 2>/dev/null)
[ "$created" = "$work/telos/demo" ] ||
  fail "unexpected workspace path: $created"
[ -f "$work/telos/demo/AGENTS.md" ] || fail "AGENTS.md was not written"
[ -f "$work/telos/demo/CLAUDE.md" ] || fail "CLAUDE.md was not written"
[ -f "$work/telos/demo/GEMINI.md" ] || fail "GEMINI.md was not written"
assert_contains "$(cat "$work/telos/demo/AGENTS.md")" \
  'wt clone telos/demo spincyc/telos'
assert_contains "$(cat "$work/telos/demo/AGENTS.md")" \
  'Every repository lives at `<owner>/<repo>`'
assert_contains "$(cat "$work/telos/demo/AGENTS.md")" 'Do not use `aiq`'
assert_contains "$(cat "$work/telos/demo/AGENTS.md")" 'AIQ_DISABLE'

printf '# guidance names the workspace branch\n'
assert_contains "$(cat "$work/telos/demo/AGENTS.md")" \
  'Commit to `feature/demo`'
assert_contains "$(cat "$work/telos/demo/AGENTS.md")" \
  'git push -u origin feature/demo'
[ "$(wt_run branch telos/demo)" = "feature/demo" ] ||
  fail "branch reported the wrong workspace branch"

printf '# a bare slug needs a project\n'
if bare_out=$(wt_run new bare 2>&1); then
  fail "a bare slug was accepted without WT_PROJECT"
fi
assert_contains "$bare_out" 'WT_PROJECT'
[ ! -e "$work/feature/bare" ] || fail "a bare slug created a feature/ workspace"
wt_project=telos wt_run new bare >/dev/null 2>&1
[ -d "$work/telos/bare" ] || fail "WT_PROJECT was not applied to a bare slug"

printf '# the branch prefix is configurable\n'
prefix_out=$(wt_branch_prefix=work wt_run branch telos/demo)
[ "$prefix_out" = "work/demo" ] ||
  fail "WT_BRANCH_PREFIX was not applied: $prefix_out"
[ "$(wt_run branch telos/demo)" = "feature/demo" ] ||
  fail "WT_BRANCH_PREFIX leaked out of the call that set it"

printf '# guidance is preserved unless --force\n'
printf 'local note\n' >>"$work/telos/demo/AGENTS.md"
wt_run new telos/demo >/dev/null 2>&1
assert_contains "$(cat "$work/telos/demo/AGENTS.md")" 'local note'
rm -f -- "$work/telos/demo/CLAUDE.md"
wt_run new telos/demo >/dev/null 2>&1
[ -f "$work/telos/demo/CLAUDE.md" ] ||
  fail "a deleted pointer file was not written back"
assert_contains "$(cat "$work/telos/demo/AGENTS.md")" 'local note'
wt_run new --force telos/demo >/dev/null 2>&1
assert_missing "$(cat "$work/telos/demo/AGENTS.md")" 'local note'

printf '# unsafe names are refused, and say why\n'
if escape_out=$(wt_run new ../escape 2>&1); then
  fail "traversal name was accepted"
fi
assert_contains "$escape_out" 'not a usable workspace name: ../escape'
[ ! -e "$work/../escape" ] || fail "traversal created a directory"

printf '# workspace names stack and accept unambiguous selectors\n'
wt_root="$test_root/stacks"
stacked=$(wt_run new telos/high-level-vision/replay-one 2>/dev/null)
[ "$stacked" = "$test_root/stacks/telos/high-level-vision/replay-one" ] ||
  fail "unexpected stacked workspace path: $stacked"
[ ! -e "$test_root/stacks/telos/high-level-vision/AGENTS.md" ] ||
  fail "a stack group was turned into a workspace"
[ -f "$test_root/stacks/telos/high-level-vision/.wt-group" ] ||
  fail "a stack group was not marked"
if group_launch=$(wt_run telos/high-level-vision 2>&1); then
  fail "a stack group was launched as a workspace"
fi
assert_contains "$group_launch" 'is a stack group; name a workspace leaf'
[ "$(wt_run branch tel/high/rep-o)" = \
    "feature/high-level-vision/replay-one" ] ||
  fail "an abbreviated stacked selector found the wrong branch"
[ "$(wt_run path feature/high-level-vision/replay-one)" = "$stacked" ] ||
  fail "a branch name did not select its workspace"
[ "$(wt_run path HIGH_LEVEL_VISION/REPLAY_ONE)" = "$stacked" ] ||
  fail "a separator-insensitive slug stack did not select its workspace"
launch_stack=$(wt_run tel/high/rep-o 2>/dev/null)
assert_contains "$launch_stack" 'workspace=telos/high-level-vision/replay-one'
[ ! -e "$test_root/stacks/tel/high/rep-o" ] ||
  fail "launch created an abbreviation instead of reusing its workspace"
wt_run new telos/high-level-vision/replay-two >/dev/null 2>&1
[ "$(wt_run path replay-t)" = \
    "$test_root/stacks/telos/high-level-vision/replay-two" ] ||
  fail "a second replay did not stack under the same vision"
[ "$(wt_run ls -q)" = "telos/high-level-vision/replay-one
telos/high-level-vision/replay-two" ] ||
  fail "a stack group was listed as a workspace"
wt_run new other/high-level-vision/replay-one >/dev/null 2>&1
if ambiguous=$(wt_run path replay-o 2>&1); then
  fail "an ambiguous leaf selector was accepted"
fi
assert_contains "$ambiguous" 'ambiguous workspace replay-o'
assert_contains "$ambiguous" 'other/high-level-vision/replay-one'
assert_contains "$ambiguous" 'telos/high-level-vision/replay-one'
stack_sweep=$(wt_run sweep)
assert_contains "$stack_sweep" \
  'pruned   telos/high-level-vision  empty group'
[ ! -e "$test_root/stacks/telos" ] ||
  fail "sweep left the emptied replay stack behind"
wt_root="$work"

printf '# names that are not usable as branches are refused\n'
if lock_out=$(wt_run new telos/demo.lock 2>&1); then
  fail ".lock slug was accepted"
fi
assert_contains "$lock_out" 'not a usable workspace name: telos/demo.lock'
if hidden_out=$(wt_run new telos/.hidden 2>&1); then
  fail "dot-leading slug was accepted"
fi
assert_contains "$hidden_out" 'not a usable workspace name: telos/.hidden'
[ ! -e "$work/telos/demo.lock" ] || fail ".lock slug created a directory"

printf '# clone lands at owner/repo on the workspace branch\n'
clone_out=$(wt_run clone telos/demo "file://$origins/spincyc/alpha" 2>&1) ||
  fail "clone from a URL failed"
assert_contains "$clone_out" 'cloned   spincyc/alpha  on feature/demo'
[ -d "$work/telos/demo/spincyc/alpha/.git" ] ||
  fail "clone did not land at spincyc/alpha"
[ "$(branch_of "$work/telos/demo/spincyc/alpha")" = "feature/demo" ] ||
  fail "clone did not land on the workspace branch"
# The fresh branch tracks the branch the clone arrived on, so status, sync,
# and the unsaved-work test keep working before anything is pushed.
[ "$(upstream_of "$work/telos/demo/spincyc/alpha")" = "origin/main" ] ||
  fail "the workspace branch does not track origin/main"
clone_again=$(wt_run clone telos/demo "file://$origins/spincyc/alpha" 2>&1)
assert_contains "$clone_again" 'ok       spincyc/alpha'

printf '# a workspace can be pinned to a branch it did not derive\n'
# A relay run works on the branch the planner named, which no slug derives.
pinned_out=$(wt_run new -b relay/run-01 telos/pinned 2>&1)
assert_contains "$pinned_out" 'branch relay/run-01'
assert_contains "$(cat "$work/telos/pinned/.wt-workspace")" \
  'branch: relay/run-01'
assert_contains "$(wt_run branch telos/pinned)" 'relay/run-01'
grep -Fq 'relay/run-01' "$work/telos/pinned/AGENTS.md" ||
  fail "the workspace guidance names the derived branch, not the pinned one"
wt_run clone telos/pinned "file://$origins/spincyc/alpha" >/dev/null 2>&1 ||
  fail "cloning into a pinned workspace failed"
[ "$(branch_of "$work/telos/pinned/spincyc/alpha")" = "relay/run-01" ] ||
  fail "the clone did not land on the pinned branch"

printf '# one launch opens the whole line of work\n'
# The branch, the repositories the work needs on it, and what to do there,
# without new, clone and launch in sequence.
open_out=$(wt_run claude triptych/proper-54 -b impl/proper-54 \
  -r "file://$origins/spincyc/alpha" --clone "file://$origins/spincyc/beta" \
  --seed 'take it to production' 2>&1)
assert_contains "$open_out" 'cloned   spincyc/alpha  on impl/proper-54'
assert_contains "$open_out" 'cloned   spincyc/beta  on impl/proper-54'
assert_agent_args "$open_out" 'take it to production'
opened_clone="$work/triptych/proper-54/spincyc/alpha"
[ "$(branch_of "$opened_clone")" = "impl/proper-54" ] ||
  fail "the launch clone is not on the branch the launch named"
# A clone already there is a benign skip, not a second clone.
assert_contains \
  "$(wt_run claude triptych/proper-54 -r "file://$origins/spincyc/alpha" \
    2>&1)" \
  'ok       spincyc/alpha'
printf '# -x prepares the clones before the agent, and takes the line\n'
# The setup step is repository tooling, so it runs where wt exec runs it:
# in every clone, with $WT_REPO naming each. Trailing words are the
# command's, including ones that look like wt options.
for prepared_repo in alpha beta; do
  mkdir -p "$work/triptych/proper-54/spincyc/$prepared_repo/tools"
  cat >"$work/triptych/proper-54/spincyc/$prepared_repo/tools/tpt" <<'TPT'
#!/bin/sh
printf 'tpt repo=%s args=%s\n' "$WT_REPO" "$*"
TPT
  chmod 755 -- "$work/triptych/proper-54/spincyc/$prepared_repo/tools/tpt"
done
prepared=$(wt_run claude --new triptych/proper-54 --seed 'after the setup' \
  -x ./tools/tpt proper 54-fourteenth seed --provider claude 2>&1)
assert_contains "$prepared" 'tpt repo=spincyc/alpha'
assert_contains "$prepared" 'tpt repo=spincyc/beta'
assert_contains "$prepared" 'args=proper 54-fourteenth seed --provider claude'
assert_agent_args "$prepared" 'after the setup'

printf '# --seed-exec makes what the setup printed the opening prompt\n'
# A tool that seeds a run and prints the instructions for it is the whole
# reason: printed to the terminal they reach nobody who can act on them.
for prepared_repo in alpha beta; do
  cat >"$work/triptych/proper-54/spincyc/$prepared_repo/tools/tpt" <<'TPT'
#!/bin/sh
printf 'progress in %s\n' "$WT_REPO" >&2
printf '{"stage": "seed", "repo": "%s"}\n' "$WT_REPO"
TPT
done
seeded=$(wt_run claude --new triptych/proper-54 \
  --seed-exec ./tools/tpt proper 54 seed --provider claude 2>&1)
# stdout becomes the prompt; stderr still reaches the terminal.
assert_contains "$seeded" 'progress in spincyc/alpha'
# Captured, so these appear only in what the agent was handed, and every
# clone's output is in it.
assert_contains "$seeded" 'args={"stage": "seed", "repo": "spincyc/alpha"}'
assert_contains "$seeded" '{"stage": "seed", "repo": "spincyc/beta"}'

printf '# a launch takes one prompt and runs one command before the agent\n'
if two_prompts=$(wt_run claude triptych/proper-54 --seed mine \
  --seed-exec ./tools/tpt 2>&1); then
  fail "a typed prompt and a printed one were accepted together"
fi
assert_contains "$two_prompts" 'would give the agent a second one'
# A second -x cannot be a second command: it is inside the first one's
# arguments, because the first took the rest of the line.
assert_contains \
  "$(wt_run claude --new triptych/proper-54 -x echo --seed-exec here 2>&1)" \
  '--seed-exec here'
if silent=$(wt_run claude --new triptych/proper-54 --seed-exec true 2>&1); then
  fail "a setup command that printed nothing still opened an agent"
fi
assert_contains "$silent" 'printed nothing'

printf '# a failing -x stops the launch instead of half-preparing it\n'
if half=$(wt_run claude triptych/proper-54 -x sh -c 'exit 3' 2>&1); then
  fail "a failing setup command still started an agent"
fi
assert_contains "$half" 'was not started in triptych/proper-54'
if printf '%s\n' "$half" | grep -Fq 'agent=claude'; then
  fail "a failing setup command still started an agent"
fi
if bare_exec=$(wt_run claude triptych/proper-54 -x 2>&1); then
  fail "-x with no command was accepted"
fi
assert_contains "$bare_exec" 'the rest of the line'

printf '# wt new opens one the same way, without an agent\n'
new_out=$(wt_run new -b impl/proper-55 -r "file://$origins/spincyc/alpha" \
  triptych/proper-55 2>&1)
assert_contains "$new_out" 'cloned   spincyc/alpha  on impl/proper-55'
printf '# a repository wt cannot name is refused before anything is made\n'
if bad_repo=$(wt_run claude triptych/proper-56 -r nonsense 2>&1); then
  fail "a clone spec with no owner/repo was accepted"
fi
assert_contains "$bad_repo" 'cannot derive owner/repo'
[ ! -e "$work/triptych/proper-56" ] ||
  fail "a refused clone spec still created the workspace"
wt_run rm -f triptych/proper-54 >/dev/null 2>&1
wt_run rm -f triptych/proper-55 >/dev/null 2>&1

printf '# the pin is what check, status and push mean by the branch\n'
wt_run check >/dev/null 2>&1 || fail "a pinned workspace failed the check"
assert_contains "$(wt_run status telos/pinned)" 'relay/run-01'
printf 'pinned work\n' >"$work/telos/pinned/spincyc/alpha/WORK.md"
git -C "$work/telos/pinned/spincyc/alpha" add WORK.md
git -C "$work/telos/pinned/spincyc/alpha" commit --quiet -m 'pinned work'
assert_contains "$(wt_run push telos/pinned 2>/dev/null)" \
  'pushed   spincyc/alpha  relay/run-01'
[ "$(upstream_of "$work/telos/pinned/spincyc/alpha")" = \
  "origin/relay/run-01" ] || fail "push did not publish the pinned branch"

printf '# the branch is chosen when the workspace is, not after\n'
if repin=$(wt_run new -b relay/run-02 telos/pinned 2>&1); then
  fail "a pinned workspace was repinned"
fi
assert_contains "$repin" 'already works on relay/run-01'
if repin_plain=$(wt_run new -b relay/run-02 telos/demo 2>&1); then
  fail "an unpinned workspace was pinned after the fact"
fi
assert_contains "$repin_plain" 'already works on feature/demo'
# Naming the branch it already works on is not a change, so it is allowed.
wt_run new -b relay/run-01 telos/pinned >/dev/null 2>&1 ||
  fail "re-stating a workspace's own branch was refused"
wt_run new -b feature/demo telos/demo >/dev/null 2>&1 ||
  fail "re-stating a derived branch was refused"
if no_branch=$(wt_run new -b telos/late 2>&1); then
  fail "-b swallowed the workspace name and created one"
fi
wt_run rm -f telos/pinned >/dev/null 2>&1

printf '# workspace is inferred from the current directory\n'
wt_at "$work/telos/demo/spincyc/alpha" \
  clone "file://$origins/spincyc/beta" >/dev/null 2>&1 ||
  fail "clone from inside the workspace failed"
[ -d "$work/telos/demo/spincyc/beta/.git" ] ||
  fail "inferred clone did not land at spincyc/beta"
[ "$(branch_of "$work/telos/demo/spincyc/beta")" = "feature/demo" ] ||
  fail "inferred clone did not land on the workspace branch"

printf '# ls reports workspaces and repos\n'
ls_out=$(wt_run ls)
assert_contains "$ls_out" 'telos/demo'
assert_contains "$ls_out" 'telos/bare'
# Anchored, so each state belongs to a named repository on a named branch;
# a bare "clean" somewhere in the blob ties nothing to anything.
assert_matches "$ls_out" '^  spincyc/alpha +feature/demo +clean +origin/main'
assert_matches "$ls_out" '^  spincyc/beta +feature/demo +clean +origin/main'
assert_contains "$ls_out" '(no repositories)'

printf '# ls reports a dirty worktree, and only the dirty one\n'
printf 'change\n' >>"$work/telos/demo/spincyc/alpha/README.md"
dirty_ls=$(wt_run ls)
assert_matches "$dirty_ls" '^  spincyc/alpha +feature/demo +dirty '
assert_matches "$dirty_ls" '^  spincyc/beta +feature/demo +clean '

printf '# ls -q prints bare workspace names\n'
quiet_ls=$(wt_run ls -q)
[ "$quiet_ls" = "telos/bare
telos/demo" ] || fail "ls -q printed more than the names: $quiet_ls"

printf '# pwd reports the workspace holding the current directory\n'
mkdir -p -- "$work/telos/demo/spincyc/alpha/deep/deeper"
pwd_out=$(wt_at "$work/telos/demo/spincyc/alpha/deep/deeper" pwd) ||
  fail "pwd failed inside a clone"
[ "$pwd_out" = "$work/telos/demo" ] ||
  fail "pwd returned the wrong directory: $pwd_out"
rm -rf -- "$work/telos/demo/spincyc/alpha/deep"
if outside_out=$(wt_at "$test_root" pwd 2>&1); then
  fail "pwd answered outside the workspace root"
fi
assert_contains "$outside_out" 'not inside a workspace under'
if project_out=$(wt_at "$work/telos" pwd 2>&1); then
  fail "pwd answered in a project directory"
fi
assert_contains "$project_out" 'not inside a workspace under'
if pwd_arg=$(wt_run pwd telos/demo 2>&1); then
  fail "pwd accepted an argument"
fi
assert_contains "$pwd_arg" 'pwd takes no arguments'

printf '# path resolves a workspace\n'
[ "$(wt_run path telos/demo)" = "$work/telos/demo" ] ||
  fail "path returned the wrong directory"
if absent_out=$(wt_run path telos/absent 2>&1); then
  fail "path accepted a missing workspace"
fi
assert_contains "$absent_out" 'no such workspace: telos/absent'

printf '# exit codes tell a usage error from a failure\n'
assert_status 0 wt_run help
assert_status 2 wt_run ls extra
assert_status 2 wt_run pwd telos/demo
assert_status 2 wt_run rm
assert_status 1 wt_run path telos/absent
usage_err=$(wt_run ls extra 2>&1 >/dev/null) || true
assert_contains "$usage_err" 'ls takes no arguments'
assert_contains "$usage_err" 'Usage: wt'

printf '# git verbs fan out over every repo, headers on stderr\n'
# The header names the repository the output came from, so it is narration:
# on stdout it would end up in whatever the caller is piping git into.
git_out=$(wt_run git telos/demo -- rev-parse --is-bare-repository 2>/dev/null)
[ "$git_out" = "false
false" ] || fail "wt git put more than git's output on stdout: $git_out"
git_err=$(wt_run git telos/demo -- rev-parse --abbrev-ref HEAD 2>&1 >/dev/null)
assert_contains "$git_err" '== spincyc/alpha'
assert_contains "$git_err" '== spincyc/beta'
git_both=$(wt_run git telos/demo -- rev-parse --abbrev-ref HEAD 2>&1)
assert_contains "$git_both" 'feature/demo'

printf '# exec runs any command in every repo\n'
if exec_bare=$(wt_run exec telos/demo 2>&1); then
  fail "exec accepted no command"
fi
assert_contains "$exec_bare" 'exec needs a command'
exec_out=$(wt_run exec telos/demo -- pwd -P 2>/dev/null)
alpha_real=$(cd -- "$work/telos/demo/spincyc/alpha" && pwd -P)
beta_real=$(cd -- "$work/telos/demo/spincyc/beta" && pwd -P)
[ "$exec_out" = "$alpha_real
$beta_real" ] || fail "exec did not run in each repo: $exec_out"

printf '# fetch brings the remote down and prunes what is gone\n'
git -C "$origins/spincyc/beta" branch gone main
wt_run fetch telos/demo >/dev/null 2>&1 || fail "fetch failed"
git -C "$work/telos/demo/spincyc/beta" rev-parse --verify --quiet \
  refs/remotes/origin/gone >/dev/null ||
  fail "fetch did not bring a new remote branch down"
git -C "$origins/spincyc/beta" branch -D gone >/dev/null
fetch_err=$(wt_run fetch telos/demo 2>&1 >/dev/null)
assert_contains "$fetch_err" '== spincyc/beta'
if git -C "$work/telos/demo/spincyc/beta" rev-parse --verify --quiet \
  refs/remotes/origin/gone >/dev/null; then
  fail "fetch did not prune a deleted remote branch"
fi
fetch_out=$(wt_run fetch telos/demo 2>/dev/null)
# stdout must be empty, not merely free of headers: assert_missing is
# satisfied by empty input, so it passed whatever fetch did.
[ -z "$fetch_out" ] || fail "fetch put something on stdout: $fetch_out"

printf '# status reports branch, upstream, and what changed\n'
status_out=$(wt_run status telos/demo)
assert_matches "$status_out" \
  '^spincyc/alpha +feature/demo +dirty +origin/main +ahead 0 behind 0'
assert_matches "$status_out" \
  '^spincyc/beta +feature/demo +clean +origin/main +ahead 0 behind 0'
assert_contains "$status_out" 'M README.md'

printf '# a failing git command is reported, not fatal\n'
if git_fail=$(wt_run git telos/demo -- no-such-subcommand 2>&1); then
  fail "a failing git command reported success"
fi
assert_contains "$git_fail" '== spincyc/beta'
assert_contains "$git_fail" 'wt: failed in spincyc/beta'

printf '# check passes on a healthy layout\n'
check_out=$(wt_run check) || fail "check failed on a healthy layout: $check_out"
assert_contains "$check_out" 'wt check passed.'
assert_contains "$check_out" '0 agents running'

printf '# check fails on an invalid workspace marker\n'
printf 'not a wt marker\n' >"$work/telos/demo/.wt-workspace"
if marker_out=$(wt_run check 2>&1); then
  fail "check accepted an invalid workspace marker"
fi
assert_contains "$marker_out" 'telos/demo has an invalid .wt-workspace'
printf 'wt-workspace-v1\nlanguage: en\n' >"$work/telos/demo/.wt-workspace"
if wt_run check >/dev/null 2>&1; then
  fail "check accepted a marker key it does not know"
fi
printf 'wt-workspace-v1\nbranch:\n' >"$work/telos/demo/.wt-workspace"
if wt_run check >/dev/null 2>&1; then
  fail "check accepted a marker naming no branch"
fi
# A branch beginning with a dash reaches git as an option, not a branch, so
# a marker wt did not write must not be able to smuggle one in.
printf 'wt-workspace-v1\nbranch: --upload-pack=touch\n' \
  >"$work/telos/demo/.wt-workspace"
if dash_marker=$(wt_run branch telos/demo 2>&1); then
  fail "a marker naming an option-shaped branch was accepted"
fi
assert_contains "$dash_marker" 'unusable branch'
printf 'wt-workspace-v1\n' >"$work/telos/demo/.wt-workspace"

printf '# check warns about a repository off the workspace branch\n'
git -C "$work/telos/demo/spincyc/beta" checkout --quiet main
assert_contains "$(wt_run check)" \
  'telos/demo/spincyc/beta is on main, not feature/demo'
wt_run check >/dev/null || fail "an off-branch repository failed the check"
git -C "$work/telos/demo/spincyc/beta" checkout --quiet feature/demo

printf '# check fails on a misplaced repository\n'
mkdir -p -- "$work/telos/bad"
git init --quiet -- "$work/telos/bad/spincyc"
if bad_out=$(wt_run check 2>&1); then
  fail "check passed with a repository in an owner directory"
fi
assert_contains "$bad_out" 'is a repository, not an owner directory'
rm -rf -- "$work/telos/bad"

printf '# check ignores whatever lives under .scratch\n'
git init --quiet -- "$work/telos/demo/.scratch"
wt_run check >/dev/null 2>&1 ||
  fail "a repository under .scratch failed the check"
rm -rf -- "$work/telos/demo/.scratch"

printf '# check fails when the default agent is missing\n'
if missing_out=$(wt_agent=absent-agent wt_run check 2>&1); then
  fail "check passed with a missing default agent"
fi
assert_contains "$missing_out" 'default agent is not installed: absent-agent'

printf '# launching runs the agent in the workspace\n'
launch_out=$(wt_run telos/demo --flag value 2>/dev/null)
assert_contains "$launch_out" "cwd=$work/telos/demo"
assert_contains "$launch_out" 'workspace=telos/demo'
assert_contains "$launch_out" 'branch=feature/demo'
assert_contains "$launch_out" 'args=--flag value'
assert_contains "$launch_out" 'slot=1'

printf '# a named agent is launched by name\n'
named_out=$(wt_run claude telos/demo 2>/dev/null)
# The stand-ins name themselves, so this distinguishes `wt claude X` from
# `wt X`; identical copies made the two indistinguishable and the section
# unable to fail.
assert_contains "$named_out" 'agent=claude'
assert_contains "$named_out" 'workspace=telos/demo'
assert_contains "$named_out" "cwd=$work/telos/demo"
assert_contains "$(wt_run codex telos/demo 2>/dev/null)" 'agent=codex'
assert_contains "$(wt_run droid telos/demo 2>/dev/null)" 'agent=droid'
assert_contains "$(wt_run telos/demo 2>/dev/null)" 'agent=fake-agent'

printf '# the launched agent keeps no work ledger\n'
assert_contains "$launch_out" 'aiq_disable=1'

# The stand-in agent has no resume spelling, so these read the seed alone.
printf '# a seed prompt opens the agent, after the agent arguments\n'
seed_out=$(wt_run --seed 'read the protocol and claim 002' \
  telos/demo --flag value 2>/dev/null)
assert_contains "$seed_out" 'args=--flag value read the protocol and claim 002'
assert_contains "$seed_out" 'workspace=telos/demo'

printf '# --seed=<text> spells the same thing\n'
assert_contains "$(wt_run --seed=inline telos/demo 2>/dev/null)" 'args=inline'

printf '# a seed prompt comes from a file without passing through the shell\n'
printf 'brief 001, claim 002\n' >"$test_root/seed-prompt.txt"
assert_contains \
  "$(wt_run --seed-file "$test_root/seed-prompt.txt" telos/demo 2>/dev/null)" \
  'args=brief 001, claim 002'

printf '# a seed prompt comes from stdin, under $WT_AGENT\n'
# The trailing newline a heredoc leaves is not part of the prompt.
stdin_out=$(printf 'from stdin\n' |
  wt_run --seed-file - telos/demo 2>/dev/null)
assert_contains "$stdin_out" 'agent=fake-agent'
assert_contains "$stdin_out" 'args=from stdin'

printf '# a seed option reads the same after the workspace as before it\n'
assert_contains "$(wt_run telos/demo --seed after 2>/dev/null)" 'args=after'
assert_contains \
  "$(wt_run telos/demo --flag value --seed after 2>/dev/null)" \
  'args=--flag value after'

printf '# -- ends wt options and hands the rest to the agent untouched\n'
# Otherwise wt would quietly eat an agent flag that happens to share a name.
assert_contains "$(wt_run telos/demo -- --seed mine 2>/dev/null)" \
  'args=--seed mine'
assert_contains "$(wt_run telos/demo -- --new 2>/dev/null)" 'args=--new'

printf '# a seed prompt is named once, is not empty, and is not bare\n'
if wt_run claude --seed one --seed-file "$test_root/seed-prompt.txt" \
  telos/demo >/dev/null 2>&1; then
  fail "two seed options named one prompt"
fi
if empty_seed=$(wt_run --seed '  ' telos/demo 2>&1); then
  fail "an empty seed prompt was accepted"
fi
assert_contains "$empty_seed" 'empty seed prompt'
if missing_seed=$(wt_run claude --seed telos/demo 2>&1); then
  fail "a seed option with no workspace after it launched"
fi
assert_contains "$missing_seed" 'claude needs a workspace'
if unreadable_seed=$(wt_run --seed-file "$test_root/absent" \
  telos/demo 2>&1); then
  fail "an unreadable seed file was accepted"
fi
assert_contains "$unreadable_seed" 'cannot read the seed prompt'

printf '# a launch resumes the session that agent last had here\n'
# The first launch of an agent has nothing to continue; the next one does.
assert_agent_args "$(wt_run claude telos/carry-on 2>/dev/null)" ''
assert_agent_args \
  "$(wt_run claude telos/carry-on --flag value 2>/dev/null)" \
  '--continue --flag value'

printf '# each agent resumes only its own session, in its own spelling\n'
assert_agent_args "$(wt_run codex telos/carry-on 2>/dev/null)" ''
assert_agent_args "$(wt_run codex telos/carry-on 2>/dev/null)" 'resume --last'
assert_agent_args "$(wt_run droid telos/carry-on 2>/dev/null)" ''
assert_agent_args "$(wt_run droid telos/carry-on 2>/dev/null)" '--resume'

printf '# an agent wt has no resume spelling for is always fresh\n'
wt_run telos/carry-on >/dev/null 2>&1
assert_agent_args "$(wt_run telos/carry-on 2>/dev/null)" ''

printf '# --new forces a fresh session\n'
assert_agent_args "$(wt_run claude --new telos/carry-on 2>/dev/null)" ''
assert_agent_args "$(wt_run claude telos/carry-on 2>/dev/null)" '--continue'

printf '# an agent that cannot resume with a prompt opens a fresh session\n'
# codex reads a trailing prompt as the session to resume, so it cannot be
# given both. A prompt that reaches nobody is the worse failure, so the
# prompt wins and the session is fresh; refusing left a generated prompt
# with nowhere to go and nobody able to retype it.
codex_seeded=$(wt_run codex --seed 'the next brief' telos/carry-on 2>&1)
assert_contains "$codex_seeded" 'starts a fresh session'
assert_agent_args "$codex_seeded" 'the next brief'
assert_agent_args \
  "$(wt_run claude --seed 'the next brief' telos/carry-on 2>/dev/null)" \
  '--continue the next brief'

printf '# the resume record is wt bookkeeping, not a stray\n'
[ -f "$work/telos/carry-on/.wt-agents" ] ||
  fail "no launch record was written"
assert_contains "$(wt_run check 2>&1)" 'ok'
if printf '%s\n' "$(wt_run sweep -n 2>&1)" | grep -Fq '.wt-agents'; then
  fail "the launch record was reported as unaccounted for"
fi
wt_run rm -f telos/carry-on >/dev/null 2>&1

printf '# a launch handoff opens an agent on the brief a commit published\n'
# The whole point of the form: the line carries a pointer, and everything
# else — run, turns, protocol, prompt — comes out of the brief's front
# matter at that commit.
make_origin spincyc/relayed
relay_seed="$test_root/relay-seed"
git clone --quiet -- "file://$origins/spincyc/relayed" "$relay_seed"
git -C "$relay_seed" switch --quiet -c feat/relay
mkdir -p "$relay_seed/.agent/runs/2026-09-02-01"
cat >"$relay_seed/.agent/runs/2026-09-02-01/001-brief.md" <<'BRIEF'
---
protocol: RELAY_VERSION
run: 2026-09-02-01
turn: 001
role: planner
agent: claude-web
subagents: 0
branch: feat/relay
base: 0000000000000000000000000000000000000000
---

Objective: the executor lands on this brief and no other.
BRIEF
relay_version=$(python3 -c 'import sys
sys.path.insert(0, "python")
import relay
print(relay.PROTOCOL_VERSION)')
sed -i "s/RELAY_VERSION/$relay_version/" \
  "$relay_seed/.agent/runs/2026-09-02-01/001-brief.md"
git -C "$relay_seed" add .agent
git -C "$relay_seed" commit --quiet -m 'brief 001'
git -C "$relay_seed" push --quiet -u origin feat/relay
relay_sha=$(git -C "$relay_seed" rev-parse HEAD)

# The planner's next brief, published the way a planner would.
publish_brief() {
  git -C "$relay_seed" pull --quiet --ff-only
  sed "s/^turn: 001$/turn: $1/" \
    "$relay_seed/.agent/runs/2026-09-02-01/001-brief.md" \
    >"$relay_seed/.agent/runs/2026-09-02-01/$1-brief.md"
  git -C "$relay_seed" add .agent
  git -C "$relay_seed" commit --quiet -m "brief $1"
  git -C "$relay_seed" push --quiet origin feat/relay
  git -C "$relay_seed" rev-parse HEAD
}

relay_out=$(wt_run claude relay/2026-09-02-01 -b feat/relay \
  --relay "spincyc/relayed@$relay_sha" 2>&1)
assert_contains "$relay_out" "$relay_version run 2026-09-02-01, brief 001"
assert_contains "$relay_out" 'claim 002, on feat/relay'
assert_contains "$relay_out" '/relay/PROTOCOL.md'
# The clone is on the branch the handoff named, not on one derived from the
# workspace name, which is what keeps status, push and check meaningful.
relay_clone="$work/relay/2026-09-02-01/spincyc/relayed"
[ "$(branch_of "$relay_clone")" = "feat/relay" ] ||
  fail "the relay clone is not on the handoff branch"

printf '# the mechanical steps are done before the agent, not described\n'
# The claim reaches origin before the session starts, so a replay or a
# failed preflight costs no session at all.
assert_contains "$relay_out" 'claimed  .agent/runs/2026-09-02-01/002-claim.md'
git -C "$origins/spincyc/relayed" cat-file -e \
  "feat/relay:.agent/runs/2026-09-02-01/002-claim.md" ||
  fail "the claim was not published before the agent started"
assert_contains "$relay_out" 'turn 002 is claimed and published'
# The brief arrives verbatim rather than as somewhere to look it up.
assert_contains "$relay_out" 'the executor lands on this brief and no other'
assert_contains "$relay_out" "pinned at $relay_sha"
assert_contains "$relay_out" 'relay prepare --protocol'
assert_contains "$relay_out" \
  '--result .agent/runs/2026-09-02-01/002-result.md'

printf '# a relay launch waits, then says what the planner is owed\n'
assert_contains "$relay_out" 'done 2026-09-02-01 002'
# The stand-in agent publishes nothing, and wt says so rather than
# implying a result the planner would then fail to find.
assert_contains "$relay_out" '002-result.md is NOT at origin'

printf '# a turn already claimed at origin stops without a session\n'
replay_code=0
replay_out=$(wt_run claude relay/replay -b feat/relay \
  --relay "spincyc/relayed@$relay_sha" 2>&1) || replay_code=$?
[ "$replay_code" = 3 ] ||
  fail "a claim replay exited $replay_code, not 3"
assert_contains "$replay_out" 'relay blocked 2026-09-02-01 002 claim-replay'
if printf '%s\n' "$replay_out" | grep -Fq 'You are the executor'; then
  fail "a claim replay still started an agent session"
fi
wt_run rm -f relay/replay >/dev/null 2>&1

printf '# the brief is the authority for the branch, not the handoff\n'
if wrong_branch=$(wt_run claude relay/wrong -b feat/other \
  --relay "spincyc/relayed@$relay_sha" 2>&1); then
  fail "a handoff disagreeing with its brief was accepted"
fi
assert_contains "$wrong_branch" 'the brief at'
wt_run rm -f relay/wrong >/dev/null 2>&1

printf '# a run pointer is checked before anything is cloned\n'
if bad_sha=$(wt_run claude relay/bad -b feat/relay \
  --relay spincyc/relayed@nope 2>&1); then
  fail "a short sha was accepted as a run pointer"
fi
assert_contains "$bad_sha" '40-character sha'
if bad_shape=$(wt_run claude relay/bad -b feat/relay \
  --relay spincyc/relayed 2>&1); then
  fail "a pointer with no sha was accepted"
fi
assert_contains "$bad_shape" '<owner>/<repo>@<sha>'
if no_branch=$(wt_run claude relay/bad \
  --relay "spincyc/relayed@$relay_sha" 2>&1); then
  fail "a launch handoff without -b was accepted"
fi
assert_contains "$no_branch" 'needs the branch the handoff names'
if both=$(wt_run claude relay/bad -b feat/relay --seed mine \
  --relay "spincyc/relayed@$relay_sha" 2>&1); then
  fail "a launch handoff and a seed prompt were accepted together"
fi
assert_contains "$both" 'would give the executor a second one'
relay_parent=$(git -C "$relay_seed" rev-parse HEAD~1)
if plain_commit=$(wt_run claude relay/plain -b main \
  --relay "spincyc/relayed@$relay_parent" 2>&1); then
  fail "a commit publishing no brief was accepted"
fi
assert_contains "$plain_commit" 'publishes no brief'
wt_run rm -f relay/bad >/dev/null 2>&1
wt_run rm -f relay/plain >/dev/null 2>&1

printf '# wt agents names the run and turn a relay worker is on\n'
# The next turn of the same run: turn 002 is claimed, so this needs its own
# brief, exactly as the planner would publish one.
relay_next=$(publish_brief 003)
rm -f -- "$test_root/slow-release" "$test_root"/slow-started-*
wt_agent=slow-agent wt_run relay/2026-09-02-01 -b feat/relay \
  --relay "spincyc/relayed@$relay_next" >"$test_root/relay-next.log" 2>&1 &
relay_agent=$!
wait_for 'wt_run agents | grep -Fq "run=2026-09-02-01"'
relay_agents=$(wt_run agents)
assert_contains "$relay_agents" 'workspace=relay/2026-09-02-01'
assert_contains "$relay_agents" 'run=2026-09-02-01 turn=004'
# This second turn's clone was behind origin by the first turn's claim.
# Preflight stops hard on a stale base and names the pure fast-forward as
# the fix, so it is taken before preflight rather than left to a hand.
assert_contains "$(cat "$test_root/relay-next.log")" \
  'fast-forwarded to origin/feat/relay'
: >"$test_root/slow-release"
wait "$relay_agent" 2>/dev/null || true
rm -f -- "$test_root/slow-release" "$test_root"/slow-started-*
wait_for 'wt_run agents | grep -Fq "no agents running"'
wt_run rm -f relay/2026-09-02-01 >/dev/null 2>&1

printf '# a relay turn an agent cannot resume and seed opens fresh\n'
# Typed together, --seed and a resume are a choice for the user to resolve.
# Derived by --relay there is no choice to offer, and every brief is
# self-sufficient at its pinned commit, so refusing would only strand the
# run. codex cannot carry a prompt into a resumed session, so it says so
# and starts one.
codex_first=$(publish_brief 007)
wt_run codex relay/fresh -b feat/relay --relay "spincyc/relayed@$codex_first" \
  >/dev/null 2>&1 || fail "the first codex relay turn failed"
codex_next=$(publish_brief 009)
codex_relay=$(wt_run codex relay/fresh -b feat/relay \
  --relay "spincyc/relayed@$codex_next" 2>&1) ||
  fail "the second codex relay turn failed: $codex_relay"
assert_contains "$codex_relay" 'starts a fresh session'
if printf '%s\n' "$codex_relay" | grep -Fq 'args=resume --last'; then
  fail "codex was resumed with a prompt it reads as a session id"
fi
wt_run rm -f relay/fresh >/dev/null 2>&1

printf '# a relay session keeps the SIGINT the key is meant to reach\n'
# wt waits for the agent instead of becoming it, and a wt that ignored
# SIGINT would hand the agent SIG_IGN across the exec, since SIG_IGN
# survives one: the key would then do nothing at all in the very session
# it is meant to interrupt.
cat >"$fake_bin/signal-agent" <<EOF
#!/usr/bin/env python3
import pathlib
import signal

pathlib.Path("$test_root/relay-sigint").write_text(
    "ignored"
    if signal.getsignal(signal.SIGINT) is signal.SIG_IGN
    else "reaches the agent"
)
EOF
chmod 755 -- "$fake_bin/signal-agent"
wt_agent=signal-agent wt_run relay/signals -b feat/relay \
  --relay "spincyc/relayed@$(publish_brief 011)" >/dev/null 2>&1
[ "$(cat "$test_root/relay-sigint")" = "reaches the agent" ] ||
  fail "the relay agent inherited an ignored SIGINT"
wt_run rm -f relay/signals >/dev/null 2>&1

printf '# launching creates the workspace, a near-miss name included\n'
# A slug one character from an existing one used to be refused as a typo,
# which made `wt new` a required first step for the next lane of work.
wt_root="$test_root/near"
wt_run new lanes/meridian-lane-2 >/dev/null 2>&1
lane_out=$(wt_run lanes/meridian-lane-3 2>/dev/null) ||
  fail "a launch was refused a name close to an existing workspace"
assert_contains "$lane_out" 'workspace=lanes/meridian-lane-3'
assert_contains "$lane_out" "cwd=$test_root/near/lanes/meridian-lane-3"
[ -f "$test_root/near/lanes/meridian-lane-3/AGENTS.md" ] ||
  fail "the launch did not create the workspace it was given"
wt_root="$work"

printf '# slots are released when the agent exits\n'
agents_out=$(wt_run agents)
assert_contains "$agents_out" 'no agents running'
# The registry lives under the root, and nowhere else.
[ -d "$work/.agents" ] || fail "the registry is not under the workspace root"

printf '# every agent holds its own slot, and nothing caps them\n'
wt_agent=slow-agent wt_run telos/demo >/dev/null 2>&1 &
first_agent=$!
wt_agent=slow-agent wt_run telos/bare >/dev/null 2>&1 &
second_agent=$!
# Each agent has its own sentinel, and the verdict comes from wt rather than
# from a fixed sleep: under load the second slot is not taken the moment the
# first one is, and a shared sentinel cannot tell the two apart.
wait_for '[ -e "$test_root/slow-started-1" ] &&
  [ -e "$test_root/slow-started-2" ]'
wait_for 'wt_run agents | grep -Fq "2 agents running"'
busy_out=$(wt_run agents)
assert_contains "$busy_out" '2 agents running'
assert_contains "$busy_out" 'workspace=telos/demo'
assert_contains "$busy_out" 'workspace=telos/bare'
# A further launch is not rationed: how many agents run at once is decided by
# how many are started, so this one takes the next slot and runs.
third_out=$(wt_run telos/demo 2>/dev/null) ||
  fail "a third agent was refused"
assert_contains "$third_out" 'slot=3'
assert_contains "$third_out" 'workspace=telos/demo'
# A workspace an agent is running in is not swept out from under it.
assert_contains "$(wt_run sweep telos/demo)" 'an agent is running here'
[ -d "$work/telos/demo" ] || fail "sweep removed a workspace holding an agent"
# Nor are its transient files swept by a tidy nobody aimed at it.
mkdir -p -- "$work/telos/demo/.scratch"
busy_tidy=$(wt_run tidy)
assert_contains "$busy_tidy" 'kept     telos/demo  an agent is running here'
assert_contains "$busy_tidy" '0 transient paths removed'
[ -d "$work/telos/demo/.scratch" ] ||
  fail "tidy swept a running agent's scratch"
rm -rf -- "$work/telos/demo/.scratch"
# A busy slot that cannot be identified protects every workspace, since the
# one it holds is unknown.
wt_run new telos/idle >/dev/null 2>&1
rm -f -- "$work/.agents/slot-1.info"
unnamed_out=$(wt_run agents)
assert_contains "$unnamed_out" '(unidentified)'
assert_contains "$(wt_run sweep telos/idle)" 'an agent is running here'
[ -d "$work/telos/idle" ] || fail "sweep trusted an unnamed busy slot"
: >"$test_root/slow-release"
wait "$first_agent" || fail "the first held agent failed"
wait "$second_agent" || fail "the second held agent failed"
assert_contains "$(wt_run agents)" 'no agents running'
# Freed slots name nobody, so the workspace the unnamed slot protected is
# now ordinary: clean it up before the sections that count workspaces.
wt_run sweep telos/idle >/dev/null || fail "sweep refused a freed workspace"

printf '# guidance sends transient items to .scratch\n'
wt_run new telos/scratch >/dev/null 2>&1
scratch_ws="$work/telos/scratch"
assert_contains "$(cat "$scratch_ws/AGENTS.md")" \
  'Always put transient items under `.scratch`'
assert_contains "$(cat "$scratch_ws/AGENTS.md")" \
  '`.scratch` at the top of this workspace'
wt_run clone telos/scratch "file://$origins/spincyc/alpha" >/dev/null 2>&1 ||
  fail "clone into the scratch workspace failed"
scratch_repo="$scratch_ws/spincyc/alpha"
assert_contains "$(cat "$scratch_repo/.git/info/exclude")" '.scratch/'

printf '# a .scratch directory does not dirty a clone\n'
mkdir -p -- "$scratch_repo/.scratch" "$scratch_ws/.scratch"
printf 'note\n' >"$scratch_repo/.scratch/note.md"
printf 'note\n' >"$scratch_ws/.scratch/note.md"
[ -z "$(git -C "$scratch_repo" status --porcelain)" ] ||
  fail ".scratch left the clone dirty"

printf '# tidy --dry-run reports without removing\n'
# A local exclude stands in for a project .gitignore: git clean -X removes
# ignored build output, and nothing else.
printf 'build.log\n' >>"$scratch_repo/.git/info/exclude"
printf 'output\n' >"$scratch_repo/build.log"
printf 'keep\n' >"$scratch_repo/untracked.md"
dry_out=$(wt_run tidy --dry-run telos/scratch)
assert_contains "$dry_out" 'would rm telos/scratch/.scratch'
assert_contains "$dry_out" 'would rm telos/scratch/spincyc/alpha/.scratch'
assert_contains "$dry_out" 'would rm telos/scratch/spincyc/alpha/build.log'
assert_missing "$dry_out" 'untracked.md'
[ -f "$scratch_repo/build.log" ] || fail "tidy --dry-run removed a file"
[ -d "$scratch_repo/.scratch" ] || fail "tidy --dry-run removed .scratch"

printf '# tidy removes scratch and ignored files only\n'
tidy_out=$(wt_run tidy telos/scratch)
assert_contains "$tidy_out" 'removed  telos/scratch/.scratch'
assert_contains "$tidy_out" '3 transient paths removed'
[ ! -e "$scratch_ws/.scratch" ] || fail "tidy left the workspace .scratch"
[ ! -e "$scratch_repo/.scratch" ] || fail "tidy left a clone .scratch"
[ ! -e "$scratch_repo/build.log" ] || fail "tidy left an ignored file"
[ -f "$scratch_repo/untracked.md" ] || fail "tidy removed an untracked file"
[ -f "$scratch_repo/README.md" ] || fail "tidy removed tracked content"
rm -f -- "$scratch_repo/untracked.md"

printf '# tidy gives a hand-made clone the .scratch exclusion\n'
mkdir -p -- "$scratch_ws/spincyc/gamma"
git clone --quiet "file://$origins/spincyc/beta" \
  "$scratch_ws/spincyc/gamma" 2>/dev/null
gamma_exclude="$scratch_ws/spincyc/gamma/.git/info/exclude"
[ -f "$gamma_exclude" ] || fail "the hand-made clone has no exclude file"
assert_missing "$(cat "$gamma_exclude")" '.scratch/'
wt_run tidy telos/scratch >/dev/null
assert_contains "$(cat "$gamma_exclude")" '.scratch/'
rm -rf -- "$scratch_ws/spincyc/gamma"

printf '# tidy with no workspace tidies the one you are standing in\n'
mkdir -p -- "$scratch_repo/.scratch"
printf 'note\n' >"$scratch_repo/.scratch/note.md"
here_tidy=$(wt_at "$scratch_repo" tidy)
assert_contains "$here_tidy" 'removed  telos/scratch/spincyc/alpha/.scratch'
assert_contains "$here_tidy" '1 transient path removed'
[ ! -e "$scratch_repo/.scratch" ] || fail "tidy inside a clone left .scratch"

printf '# tidy does not follow a .scratch symlink out of the workspace\n'
mkdir -p -- "$test_root/precious"
printf 'keep\n' >"$test_root/precious/keep.md"
ln -s -- "$test_root/precious" "$scratch_repo/.scratch"
wt_run tidy telos/scratch >/dev/null
[ -f "$test_root/precious/keep.md" ] ||
  fail "tidy deleted through a .scratch symlink"
[ ! -e "$scratch_repo/.scratch" ] || fail "tidy left the .scratch symlink"

printf '# tidy refuses to reach through a symlinked clone\n'
outside_repo="$test_root/outside-repo"
git init --quiet -- "$outside_repo"
printf 'keep.log\n' >>"$outside_repo/.git/info/exclude"
printf 'precious\n' >"$outside_repo/keep.log"
ln -s -- "$outside_repo" "$scratch_ws/spincyc/linked"
link_tidy=$(wt_run tidy telos/scratch)
assert_contains "$link_tidy" 'spincyc/linked  a symlink'
[ -f "$outside_repo/keep.log" ] ||
  fail "tidy cleaned a repository outside the workspace"
# A symlinked clone reads as unsaved work, which would mask the next check.
rm -f -- "$scratch_ws/spincyc/linked"

printf '# a sweep keeps a workspace holding anything wt cannot account for\n'
printf 'plan\n' >"$scratch_ws/notes.md"
stray_sweep=$(wt_run sweep telos/scratch)
assert_contains "$stray_sweep" 'not from wt: notes.md'
[ -d "$scratch_ws" ] || fail "sweep removed a workspace holding stray work"
rm -f -- "$scratch_ws/notes.md"

printf '# a sweep keeps a workspace whose clone has an unpushed side branch\n'
git -C "$scratch_repo" checkout --quiet -b side
printf 'side\n' >"$scratch_repo/side.md"
git -C "$scratch_repo" add side.md
git -C "$scratch_repo" commit --quiet -m side
git -C "$scratch_repo" checkout --quiet feature/scratch
assert_contains "$(wt_run sweep telos/scratch)" 'unsaved: spincyc/alpha'
[ -d "$scratch_ws" ] || fail "sweep discarded an unpushed side branch"
git -C "$scratch_repo" branch --quiet -D side

printf '# a sweep keeps a workspace holding unsaved work\n'
printf 'change\n' >>"$scratch_repo/README.md"
unsaved_sweep=$(wt_run sweep telos/scratch)
assert_contains "$unsaved_sweep" \
  'kept     telos/scratch  unsaved: spincyc/alpha'
assert_contains "$unsaved_sweep" '0 removed, 1 kept'
[ -d "$scratch_ws" ] || fail "sweep removed a workspace holding work"
git -C "$scratch_repo" checkout --quiet -- README.md

printf '# a sweep keeps the workspace holding the current directory\n'
here_sweep=$(wt_at "$scratch_repo" sweep telos/scratch)
assert_contains "$here_sweep" 'kept     telos/scratch  the current directory'
assert_contains "$here_sweep" '0 removed, 1 kept'
[ -d "$scratch_ws" ] || fail "sweep removed the current workspace"

printf '# sweep --dry-run removes nothing\n'
# -n is the synonym, and either may follow the workspace.
dry_sweep=$(wt_run sweep telos/scratch -n)
assert_contains "$dry_sweep" 'would rm telos/scratch'
assert_contains "$dry_sweep" '1 to remove, 0 kept'
[ -d "$scratch_ws" ] || fail "sweep --dry-run removed a workspace"

printf '# a sweep removes a workspace whose work is pushed\n'
sweep_out=$(wt_run sweep telos/scratch)
assert_contains "$sweep_out" 'removed  telos/scratch'
[ ! -e "$scratch_ws" ] || fail "sweep left a pushed workspace in place"
[ -d "$work/telos/demo" ] || fail "sweep touched another workspace"

printf '# tidy leaves a .scratch the repository tracks\n'
wt_run clone telos/tracked "file://$origins/spincyc/alpha" >/dev/null 2>&1
tracked_repo="$work/telos/tracked/spincyc/alpha"
mkdir -p -- "$tracked_repo/.scratch"
printf 'kept\n' >"$tracked_repo/.scratch/keep.md"
git -C "$tracked_repo" add --force .scratch/keep.md
git -C "$tracked_repo" commit --quiet -m tracked
tracked_out=$(wt_run tidy telos/tracked)
assert_contains "$tracked_out" 'spincyc/alpha/.scratch  tracked'
[ -f "$tracked_repo/.scratch/keep.md" ] ||
  fail "tidy deleted a .scratch the repository tracks"
# -f is the short spelling of --force, and either may follow the workspace.
wt_run rm telos/tracked -f >/dev/null || fail "rm -f after a workspace failed"
[ ! -e "$work/telos/tracked" ] || fail "rm -f left the workspace in place"

printf '# a sweep prunes a project directory it emptied, and only that one\n'
wt_run new spare/one >/dev/null 2>&1
mkdir -p -- "$work/stray"
prune_out=$(wt_run sweep spare/one)
assert_contains "$prune_out" 'removed  spare/one'
assert_contains "$prune_out" 'pruned   spare  empty project'
assert_missing "$prune_out" 'pruned   stray'
[ ! -e "$work/spare" ] || fail "sweep left an empty project directory"
[ -d "$work/stray" ] || fail "sweep pruned a project it never touched"
rmdir -- "$work/stray"

printf '# a sweep removes every finished workspace and keeps the rest\n'
# A root of its own, so a sweep that removes things cannot disturb the
# workspaces the sections below still need.
sweep_root="$test_root/sweep"
wt_root="$sweep_root" wt_run new sweep/empty >/dev/null 2>&1
wt_root="$sweep_root" wt_run clone sweep/done \
  "file://$origins/spincyc/alpha" >/dev/null 2>&1 ||
  fail "clone into the swept workspace failed"
wt_root="$sweep_root" wt_run clone hold/work \
  "file://$origins/spincyc/beta" >/dev/null 2>&1 ||
  fail "clone into the held workspace failed"
printf 'change\n' >>"$sweep_root/hold/work/spincyc/beta/README.md"
sweep_all=$(wt_root="$sweep_root" wt_run sweep) ||
  fail "a sweep with nothing to refuse reported failure"
assert_contains "$sweep_all" 'removed  sweep/done'
assert_contains "$sweep_all" 'removed  sweep/empty'
assert_contains "$sweep_all" 'kept     hold/work  unsaved: spincyc/beta'
assert_contains "$sweep_all" 'pruned   sweep  empty project'
assert_contains "$sweep_all" '2 removed, 1 kept'
[ ! -e "$sweep_root/sweep" ] || fail "the sweep left an emptied project behind"
[ -d "$sweep_root/hold/work" ] || fail "the sweep removed unsaved work"
rm -rf -- "$sweep_root"

printf '# rm refuses unsaved work\n'
if rm_out=$(wt_run rm telos/demo 2>&1); then
  fail "rm discarded a dirty worktree"
fi
assert_contains "$rm_out" 'unsaved  spincyc/alpha'
[ -d "$work/telos/demo" ] || fail "rm removed the workspace anyway"

printf '# rm refuses an unpushed commit in any repository\n'
git -C "$work/telos/demo/spincyc/alpha" checkout --quiet -- README.md
printf 'local\n' >"$work/telos/demo/spincyc/beta/local.md"
git -C "$work/telos/demo/spincyc/beta" add local.md
git -C "$work/telos/demo/spincyc/beta" commit --quiet -m 'local'
if rm_out=$(wt_run rm telos/demo 2>&1); then
  fail "rm discarded an unpushed commit"
fi
assert_contains "$rm_out" 'unsaved  spincyc/beta'

printf '# a published workspace branch is resumed by a later clone\n'
git -C "$work/telos/demo/spincyc/beta" push --quiet -u origin feature/demo
wt_run clone other/demo "file://$origins/spincyc/beta" >/dev/null 2>&1 ||
  fail "clone into a second workspace failed"
[ "$(branch_of "$work/other/demo/spincyc/beta")" = "feature/demo" ] ||
  fail "the published branch was not resumed"
[ "$(upstream_of "$work/other/demo/spincyc/beta")" = "origin/feature/demo" ] ||
  fail "the resumed branch does not track origin/feature/demo"
[ -f "$work/other/demo/spincyc/beta/local.md" ] ||
  fail "the resumed clone is missing the published commit"
wt_run rm other/demo >/dev/null || fail "rm refused a resumed workspace"

printf '# rm removes a clean workspace and honours --force\n'
wt_run rm telos/bare >/dev/null || fail "rm refused a clean workspace"
[ ! -e "$work/telos/bare" ] || fail "rm left the workspace in place"
wt_run rm --force telos/demo >/dev/null || fail "rm --force failed"
[ ! -e "$work/telos/demo" ] || fail "rm --force left the workspace in place"

printf '# rm stays inside the workspace root\n'
mkdir -p -- "$test_root/outside"
ln -s -- "$test_root/outside" "$work/telos/linked"
if link_out=$(wt_run rm telos/linked 2>&1); then
  fail "rm followed a symlinked workspace"
fi
assert_contains "$link_out" 'must not be a symlink'
[ -d "$test_root/outside" ] || fail "rm removed the symlink target"

printf '# a sweep reports what it refuses instead of following it\n'
printf 'keep\n' >"$test_root/outside/keep.md"
if sweep_link=$(wt_run sweep 2>&1); then
  fail "sweep followed a symlinked workspace"
fi
assert_contains "$sweep_link" 'must not be a symlink'
assert_contains "$sweep_link" '0 removed, 1 kept'
[ -f "$test_root/outside/keep.md" ] ||
  fail "sweep deleted through the symlink"

# Every section below builds a workspace root of its own, so a destructive
# check cannot reach what another section is still holding. $work is done.

printf '# rm refuses the work a sweep refuses to touch\n'
wt_root="$test_root/strays"
wt_run clone stray/work "file://$origins/spincyc/alpha" >/dev/null 2>&1 ||
  fail "clone into the stray workspace failed"
stray_ws="$wt_root/stray/work"
# None of the three sits at <owner>/<repo>, so none is a clone wt can find,
# and each holds commits no repository in the workspace reports.
git clone --quiet "file://$origins/spincyc/beta" "$stray_ws/loose" 2>/dev/null
mkdir -p -- "$stray_ws/spincyc/deep"
git clone --quiet "file://$origins/spincyc/beta" \
  "$stray_ws/spincyc/deep/beta" 2>/dev/null
git clone --quiet --bare "file://$origins/spincyc/beta" \
  "$stray_ws/spincyc/bare.git" 2>/dev/null
if stray_rm=$(wt_run rm stray/work 2>&1); then
  fail "rm deleted work a sweep refuses to touch"
fi
assert_contains "$stray_rm" 'not from wt:'
assert_contains "$stray_rm" 'loose'
assert_contains "$stray_rm" 'spincyc/bare.git'
assert_contains "$stray_rm" 'spincyc/deep'
[ -d "$stray_ws/loose/.git" ] || fail "rm removed the stray clone anyway"
assert_contains "$(wt_run sweep stray/work)" 'not from wt:'
[ -d "$stray_ws" ] || fail "sweep removed a workspace holding strays"

printf '# rm refuses the directory it was run from, --force included\n'
wt_root="$test_root/inside"
wt_run new inside/here >/dev/null 2>&1
inside_ws="$wt_root/inside/here"
if inside_rm=$(wt_at "$inside_ws" rm inside/here 2>&1); then
  fail "rm removed the workspace it was run from"
fi
assert_contains "$inside_rm" 'the current directory'
# --force waives the questions about the user's own work; standing in the
# directory is not the caller's to discard, so it survives --force too.
if forced_rm=$(wt_at "$inside_ws" rm --force inside/here 2>&1); then
  fail "rm --force removed the workspace it was run from"
fi
assert_contains "$forced_rm" 'the current directory'
mkdir -p -- "$inside_ws/deeper"
if deep_rm=$(wt_at "$inside_ws/deeper" rm inside/here -f 2>&1); then
  fail "rm -f removed the workspace holding the current directory"
fi
assert_contains "$deep_rm" 'the current directory'
[ -d "$inside_ws" ] || fail "rm --force deleted it anyway"
rmdir -- "$inside_ws/deeper"
wt_run rm inside/here >/dev/null || fail "rm refused it from outside"
[ ! -e "$inside_ws" ] || fail "rm from outside left the workspace in place"

printf '# a stash alone is unsaved work\n'
wt_root="$test_root/stash"
wt_run clone stash/work "file://$origins/spincyc/alpha" >/dev/null 2>&1 ||
  fail "clone into the stash workspace failed"
stash_repo="$wt_root/stash/work/spincyc/alpha"
printf 'stashed\n' >>"$stash_repo/README.md"
git -C "$stash_repo" stash push --quiet
[ -z "$(git -C "$stash_repo" status --porcelain)" ] ||
  fail "the stash left the tree dirty"
if stash_rm=$(wt_run rm stash/work 2>&1); then
  fail "rm discarded a stash"
fi
assert_contains "$stash_rm" 'unsaved  spincyc/alpha'
assert_contains "$(wt_run sweep stash/work)" \
  'kept     stash/work  unsaved: spincyc/alpha'
[ -d "$wt_root/stash/work" ] || fail "sweep removed a stashed workspace"

printf '# tidy works under a root reached through a symlinked directory\n'
mkdir -p -- "$test_root/real-parent/roots"
ln -s -- "$test_root/real-parent" "$test_root/linked-parent"
wt_root="$test_root/linked-parent/roots"
wt_run clone link/work "file://$origins/spincyc/alpha" >/dev/null 2>&1 ||
  fail "clone under a symlinked root failed"
link_ws="$wt_root/link/work"
mkdir -p -- "$link_ws/.scratch" "$link_ws/spincyc/alpha/.scratch"
printf 'note\n' >"$link_ws/spincyc/alpha/.scratch/note.md"
printf 'build.log\n' >>"$link_ws/spincyc/alpha/.git/info/exclude"
printf 'output\n' >"$link_ws/spincyc/alpha/build.log"
link_tidy=$(wt_run tidy link/work)
# Every clone read as "a symlink" when any directory above the root was one,
# so the whole tidy was a silent no-op that reported itself as a success.
assert_missing "$link_tidy" 'a symlink'
assert_contains "$link_tidy" 'removed  link/work/.scratch'
assert_contains "$link_tidy" 'removed  link/work/spincyc/alpha/.scratch'
assert_contains "$link_tidy" 'removed  link/work/spincyc/alpha/build.log'
assert_contains "$link_tidy" '3 transient paths removed'
[ ! -e "$link_ws/.scratch" ] || fail "tidy left the workspace .scratch"
[ ! -e "$link_ws/spincyc/alpha/.scratch" ] || fail "tidy left a clone .scratch"
[ ! -e "$link_ws/spincyc/alpha/build.log" ] ||
  fail "tidy reported a removal it never made"

printf '# a sweep refuses a registry it cannot read\n'
wt_root="$test_root/limits"
wt_run new limits/keep >/dev/null 2>&1
# A launch is what creates the registry; this one runs and exits at once,
# leaving the lock files behind for the sections below to break.
wt_run limits/keep >/dev/null 2>&1 || fail "the registry launch failed"
chmod 000 "$wt_root/.agents"
# An unreadable registry is not an empty one. Reading it as empty is what
# swept workspaces out from under live agents.
if blind_sweep=$(wt_run sweep 2>&1); then
  fail "a sweep proceeded without knowing which workspaces hold an agent"
fi
assert_contains "$blind_sweep" 'cannot read the agent slots'
[ -d "$wt_root/limits/keep" ] || fail "the sweep deleted a workspace blind"
if blind_tidy=$(wt_run tidy 2>&1); then
  fail "a tidy proceeded on a registry it cannot read"
fi
assert_contains "$blind_tidy" 'cannot read the agent slots'
if blind_agents=$(wt_run agents 2>&1); then
  fail "agents reported a registry it cannot read"
fi
assert_contains "$blind_agents" 'cannot read the agent slots'
if blind_check=$(wt_run check 2>&1); then
  fail "check passed with a registry it cannot read"
fi
assert_contains "$blind_check" 'cannot read the agent slots'
chmod 700 "$wt_root/.agents"
wt_run check >/dev/null 2>&1 || fail "check failed once the registry was back"

printf '# clean still works, and says on stderr that it is now sweep\n'
wt_root="$test_root/legacy"
wt_run new legacy/gone >/dev/null 2>&1
legacy_err=$(wt_run clean legacy/gone 2>&1 >/dev/null)
assert_contains "$legacy_err" 'clean is now sweep'
[ ! -e "$wt_root/legacy/gone" ] || fail "clean stopped removing workspaces"
wt_run new legacy/again >/dev/null 2>&1
legacy_out=$(wt_run clean legacy/again 2>/dev/null)
assert_contains "$legacy_out" 'removed  legacy/again'
# The note is narration; on stdout it would land in whatever reads the report.
assert_missing "$legacy_out" 'clean is now sweep'

printf '# a clone from a local path comes from that path\n'
wt_root="$test_root/local"
local_src="$test_root/local-src/spincyc/alpha"
mkdir -p -- "$local_src"
git init --quiet -- "$local_src"
printf 'local only\n' >"$local_src/LOCAL-ONLY.md"
git -C "$local_src" add LOCAL-ONLY.md
git -C "$local_src" commit --quiet -m local
git -C "$local_src" branch -M main
# The origins tree holds a different spincyc/alpha, so the marker file says
# which of the two the clone actually came from: a local path used to be
# rewritten into a forge URL and fetched from the network instead.
local_out=$(wt_run clone -w local/work "$local_src" 2>&1) ||
  fail "clone from a local path failed"
assert_contains "$local_out" 'cloned   spincyc/alpha  on feature/work'
local_repo="$wt_root/local/work/spincyc/alpha"
[ -f "$local_repo/LOCAL-ONLY.md" ] ||
  fail "the local clone did not come from the local path"
[ ! -e "$local_repo/README.md" ] || fail "the clone came from the forge origin"
[ "$(git -C "$local_repo" remote get-url origin)" = "$local_src" ] ||
  fail "the clone points somewhere other than the local path"
[ "$(branch_of "$local_repo")" = "feature/work" ] ||
  fail "the local clone did not land on the workspace branch"

printf '# a slug Git cannot use as a branch is refused before anything exists\n'
wt_root="$test_root/naming"
if range_out=$(wt_run new naming/a..b 2>&1); then
  fail "a..b was accepted as a workspace name"
fi
assert_contains "$range_out" 'not a usable branch name: feature/a..b'
[ ! -e "$wt_root/naming/a..b" ] || fail "a..b created a directory"
if range_clone=$(wt_run clone -w naming/a..b "file://$origins/spincyc/alpha" \
  2>&1); then
  fail "a..b was accepted as a clone target"
fi
assert_contains "$range_clone" 'not a usable branch name: feature/a..b'
# The rule belongs to creation: a workspace made before it existed must stay
# reachable, or wt would list directories none of its verbs could touch.
mkdir -p "$wt_root/naming/a..b"
assert_contains "$(wt_run path naming/a..b)" 'naming/a..b'
assert_contains "$(wt_run rm naming/a..b)" 'removed'
[ ! -e "$wt_root/naming/a..b" ] || fail "rm could not reach a legacy name"
# A slug git accepts under the prefix is not refused for standing alone.
wt_run new naming/HEAD >/dev/null || fail "feature/HEAD is a legal branch"

printf '# clone -o files a repository under the owner you name\n'
wt_root="$test_root/owner"
mkdir -p -- "$test_root/mirror"
git clone --quiet "file://$origins/spincyc/alpha" "$test_root/mirror/alpha"
wt_run clone -w ow/work "$test_root/mirror/alpha" >/dev/null 2>&1 ||
  fail "clone from a local path failed"
[ -d "$wt_root/ow/work/mirror/alpha" ] ||
  fail "the default owner is the parent directory"
wt_run clone -w ow/named -o spincyc "$test_root/mirror/alpha" >/dev/null 2>&1 ||
  fail "clone -o failed"
[ -d "$wt_root/ow/named/spincyc/alpha" ] ||
  fail "-o did not file the clone under the named owner"
if wt_run clone -w ow/bad -o 'bad owner' "$test_root/mirror/alpha" \
  >/dev/null 2>&1; then
  fail "-o accepted an owner that is not a usable path component"
fi
if wt_run clone -w ow/many -o spincyc "$test_root/mirror/alpha" \
  "file://$origins/spincyc/beta" >/dev/null 2>&1; then
  fail "-o accepted more than one repository"
fi
wt_root="$work"

printf '# status -q is one tab-separated line per repository\n'
wt_root="$test_root/porcelain"
wt_run clone -w pc/work "file://$origins/spincyc/alpha" \
  "file://$origins/spincyc/beta" >/dev/null 2>&1 ||
  fail "clone into the porcelain workspace failed"
porcelain=$(wt_run status -q pc/work)
# Field by field, because the human form aligns on widths a long name breaks.
assert_matches "$porcelain" '^pc/work	spincyc/alpha	feature/work	origin/main	clean	'
[ "$(printf '%s\n' "$porcelain" | wc -l)" -eq 2 ] ||
  fail "status -q printed something other than one line per repo"
assert_missing "$porcelain" 'ahead 0'
wt_root="$work"

printf '# an empty clone is a benign skip, not a permanent failure\n'
wt_root="$test_root/emptyclone"
mkdir -p -- "$origins/spincyc/unborn"
git init --quiet --bare -- "$origins/spincyc/unborn"
wt_run clone -w ec/work "file://$origins/spincyc/unborn" \
  "file://$origins/spincyc/alpha" >/dev/null 2>&1 ||
  fail "clone of an empty origin failed"
ec_sync=$(wt_run sync ec/work 2>/dev/null) ||
  fail "an empty clone made the whole sync fail"
assert_contains "$ec_sync" 'skipped  spincyc/unborn  no commits yet'
assert_contains "$ec_sync" 'synced   spincyc/alpha'
wt_run log ec/work >/dev/null || fail "an empty clone made log fail"
wt_root="$work"

printf '# an unreadable project directory is reported, not read as empty\n'
wt_root="$test_root/unreadableproject"
wt_run new up/work >/dev/null 2>&1
chmod 000 "$wt_root/up"
up_check=$(wt_run check 2>&1) && fail "check passed over an unreadable project"
assert_contains "$up_check" 'project up cannot be read'
chmod 755 "$wt_root/up"
wt_run check >/dev/null 2>&1 || fail "check failed on a healthy root"
wt_root="$work"

printf '# not knowing which workspace is a usage error, not a missing one\n'
assert_status 1 wt_run path nope/nope
assert_status 2 wt_run rm
(cd / && assert_status 2 wt_run path)

printf '# a commit reachable only from a local tag is unsaved work\n'
wt_root="$test_root/tagged"
wt_run clone -w tag/work "file://$origins/spincyc/alpha" >/dev/null 2>&1 ||
  fail "clone into the tagged workspace failed"
tag_repo="$wt_root/tag/work/spincyc/alpha"
git -C "$tag_repo" push --quiet -u origin feature/work
# Parked the way an agent parks work before switching away: a tag, and no
# branch anywhere pointing at it.
git -C "$tag_repo" checkout --quiet --detach
printf 'parked\n' >"$tag_repo/PARKED.md"
git -C "$tag_repo" add PARKED.md
git -C "$tag_repo" commit --quiet -m 'parked work'
git -C "$tag_repo" tag wip-save
git -C "$tag_repo" checkout --quiet feature/work
tag_rm=$(wt_run rm tag/work 2>&1) && fail "rm discarded a tagged commit"
assert_contains "$tag_rm" 'unsaved  spincyc/alpha'
assert_contains "$(wt_run sweep -n tag/work)" 'kept     tag/work'
git -C "$tag_repo" tag -d wip-save >/dev/null
wt_root="$work"

printf '# a workspace wt cannot read is refused, not read as empty\n'
wt_root="$test_root/unreadable"
wt_run new ur/work >/dev/null 2>&1
chmod 000 "$wt_root/ur/work"
assert_contains "$(wt_run sweep -n ur/work)" 'wt cannot read this directory'
ur_rm=$(wt_run rm ur/work 2>&1) && fail "rm deleted a workspace it cannot read"
assert_contains "$ur_rm" 'wt cannot read this directory'
assert_contains "$(wt_run check 2>&1)" 'ur/work cannot be read'
chmod 755 "$wt_root/ur/work"
wt_root="$work"

printf '# push leaves a clone that has left the workspace branch alone\n'
wt_root="$test_root/offbranch"
wt_run clone -w ob/work "file://$origins/spincyc/alpha" >/dev/null 2>&1 ||
  fail "clone into the offbranch workspace failed"
ob_repo="$wt_root/ob/work/spincyc/alpha"
git -C "$ob_repo" checkout --quiet -b review-someone-else
printf 'x\n' >"$ob_repo/REVIEW.md"
git -C "$ob_repo" add REVIEW.md
git -C "$ob_repo" commit --quiet -m 'a review checkout'
ob_out=$(wt_run push ob/work 2>/dev/null)
assert_contains "$ob_out" 'skipped  spincyc/alpha  on review-someone-else'
assert_contains "$ob_out" '0 repositories published'
git ls-remote --heads "$origins/spincyc/alpha" review-someone-else |
  grep -q . && fail "push published a branch that is not the workspace branch"
wt_root="$work"

printf '# one clone that cannot be tidied does not abandon its siblings\n'
wt_root="$test_root/tidyfail"
wt_run clone -w tf/work "file://$origins/spincyc/alpha" \
  "file://$origins/spincyc/beta" >/dev/null 2>&1 ||
  fail "clone into the tidyfail workspace failed"
tf_alpha="$wt_root/tf/work/spincyc/alpha"
tf_beta="$wt_root/tf/work/spincyc/beta"
mkdir -p "$tf_alpha/.scratch/cache/ro"
printf 'x\n' >"$tf_alpha/.scratch/cache/ro/f"
mkdir -p "$tf_beta/.scratch"
printf 'b\n' >"$tf_beta/.scratch/b.md"
chmod 555 "$tf_alpha/.scratch/cache/ro" "$tf_alpha/.scratch/cache"
tf_out=$(wt_run tidy tf/work 2>&1) && fail "tidy reported success on a failure"
assert_contains "$tf_out" 'failed'
# The sibling is the point: its .scratch must be gone even though alpha blew up.
[ ! -e "$tf_beta/.scratch" ] ||
  fail "one unreadable clone abandoned its siblings"
chmod -R 755 "$tf_alpha/.scratch" 2>/dev/null || true
wt_root="$work"

printf '# a failed clone leaves nothing that pins the workspace\n'
wt_root="$test_root/failedclone"
if wt_run clone -w fc/work "file://$origins/spincyc/nosuch" >/dev/null 2>&1; then
  fail "a clone from a missing origin reported success"
fi
[ ! -d "$wt_root/fc/work/spincyc" ] ||
  fail "a failed clone left an owner directory behind"
assert_contains "$(wt_run sweep -n fc/work)" 'would rm fc/work'
wt_root="$work"

printf '# a misspelled verb is not a workspace name\n'
if verb_out=$(wt_run satus 2>&1); then
  fail "a misspelled verb was accepted"
fi
assert_contains "$verb_out" 'did you mean status'
assert_status 2 wt_run satus

printf '# tidy names a repository under .scratch instead of taking it\n'
wt_root="$test_root/nested"
wt_run clone -w nested/work "file://$origins/spincyc/alpha" >/dev/null 2>&1 ||
  fail "clone into the nested workspace failed"
nested_repo="$wt_root/nested/work/spincyc/alpha"
mkdir -p "$nested_repo/.scratch/experiment"
git init --quiet -- "$nested_repo/.scratch/experiment"
printf 'valuable\n' >"$nested_repo/.scratch/experiment/notes.md"
git -C "$nested_repo/.scratch/experiment" add notes.md
git -C "$nested_repo/.scratch/experiment" commit --quiet -m 'an experiment'
nested_dry=$(wt_run tidy -n nested/work)
nested_real=$(wt_run tidy nested/work)
# git clean refuses to recurse into a repository; rmtree would not, so the
# dry run has to promise exactly what the real run does.
assert_contains "$nested_dry" 'holds a repository'
assert_contains "$nested_real" 'holds a repository'
[ -f "$nested_repo/.scratch/experiment/notes.md" ] ||
  fail "tidy destroyed a repository under .scratch"
wt_root="$work"

printf '# sync fetches and rebases onto the default branch\n'
make_origin spincyc/delta
wt_root="$test_root/sync"
wt_run clone sync/work "file://$origins/spincyc/delta" >/dev/null 2>&1 ||
  fail "clone into the sync workspace failed"
sync_repo="$wt_root/sync/work/spincyc/delta"
# A commit lands on the default branch after the clone was taken.
git clone --quiet "file://$origins/spincyc/delta" "$test_root/delta-upstream"
printf 'newer\n' >"$test_root/delta-upstream/NEWER.md"
git -C "$test_root/delta-upstream" add NEWER.md
git -C "$test_root/delta-upstream" commit --quiet -m newer
git -C "$test_root/delta-upstream" push --quiet origin main
sync_out=$(wt_run sync sync/work 2>/dev/null)
assert_contains "$sync_out" 'synced   spincyc/delta  onto origin/main'
[ -f "$sync_repo/NEWER.md" ] || fail "sync did not bring the new commit down"
[ "$(branch_of "$sync_repo")" = "feature/work" ] ||
  fail "sync left the workspace branch"
# pull is not an alias: sync rebases, so an old habit is asked, not assumed.
pull_out=$(wt_run pull sync/work 2>&1) && fail "pull did not refuse"
assert_contains "$pull_out" 'pull is now sync'
assert_status 2 wt_run pull sync/work

printf '# push ignores work parked on an unrelated branch\n'
git -C "$sync_repo" checkout --quiet -b side-idea
printf 'idea\n' >"$sync_repo/IDEA.md"
git -C "$sync_repo" add IDEA.md
git -C "$sync_repo" commit --quiet -m 'an idea'
git -C "$sync_repo" checkout --quiet feature/work
side_out=$(wt_run push sync/work 2>/dev/null)
assert_contains "$side_out" 'skipped  spincyc/delta  nothing to publish'
assert_contains "$side_out" '0 repositories published'
git ls-remote --heads "$origins/spincyc/delta" feature/work | grep -q . &&
  fail "push published a branch holding no work"
# The side branch is unpublished work, so later sections would inherit it.
git -C "$sync_repo" branch --quiet -D side-idea

printf '# push publishes the workspace branch, and log shows the work\n'
printf 'work\n' >"$sync_repo/WORK.md"
git -C "$sync_repo" add WORK.md
git -C "$sync_repo" commit --quiet -m 'the work'
log_out=$(wt_run log sync/work)
assert_contains "$log_out" 'spincyc/delta'
assert_contains "$log_out" 'the work'
push_out=$(wt_run push sync/work 2>/dev/null)
assert_contains "$push_out" 'pushed   spincyc/delta  feature/work'
assert_contains "$push_out" '1 repository published'
[ "$(upstream_of "$sync_repo")" = "origin/feature/work" ] ||
  fail "push did not retarget the upstream"
push_again=$(wt_run push sync/work 2>/dev/null)
assert_contains "$push_again" 'skipped  spincyc/delta  nothing to publish'
assert_contains "$push_again" '0 repositories published'
status_out=$(wt_run status sync/work)
assert_matches "$status_out" \
  '^spincyc/delta +feature/work +clean +origin/feature/work +ahead 0 behind 0'
# Published work is disposable work.
wt_run rm sync/work >/dev/null || fail "rm refused a published workspace"

printf 'ok - wt\n'

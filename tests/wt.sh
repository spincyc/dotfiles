#!/bin/sh
# Isolated checks for bin/wt. Everything happens under a temporary root with
# local origins, so the suite never touches ~/git or the network.
set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
wt="$repo_dir/bin/wt"
test_root=$(mktemp -d "${TMPDIR:-/tmp}/dotfiles-wt-test.XXXXXX")
origins="$test_root/origins"
work="$test_root/worktrees"
state="$test_root/state"
fake_bin="$test_root/bin"

cleanup() {
  case "$test_root" in
    "${TMPDIR:-/tmp}"/dotfiles-wt-test.*)
      rm -rf -- "$test_root"
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

# gh is bypassed by giving every clone an explicit file:// URL, so the suite
# stays offline and independent of the caller's forge credentials.
wt_run() {
  WT_ROOT="$work" \
  WT_MAX_AGENTS="${wt_max_agents:-2}" \
  WT_AGENT="${wt_agent:-fake-agent}" \
  WT_PROJECT="${wt_project:-}" \
  XDG_STATE_HOME="$state" \
  PATH="$fake_bin:$PATH" \
    "$wt" "$@"
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

assert_missing() {
  printf '%s' "$1" | grep -Fq -- "$2" &&
    fail "output unexpectedly contains: $2"
  return 0
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

mkdir -p -- "$origins" "$state" "$fake_bin"

# A stand-in agent that records where it was launched and what it received.
cat >"$fake_bin/fake-agent" <<'EOF'
#!/bin/sh
printf 'agent cwd=%s slot=%s workspace=%s branch=%s aiq_disable=%s args=%s\n' \
  "$(pwd -P)" "${WT_AGENT_SLOT:-}" "${WT_WORKSPACE:-}" "${WT_BRANCH:-}" \
  "${AIQ_DISABLE:-unset}" "$*"
EOF
chmod 755 -- "$fake_bin/fake-agent"

# A stand-in agent that holds its slot until a sentinel file appears.
cat >"$fake_bin/slow-agent" <<EOF
#!/bin/sh
printf 'started\n' >"$test_root/slow-started"
while [ ! -e "$test_root/slow-release" ]; do
  sleep 0.05
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
prefix_out=$(WT_ROOT="$work" WT_BRANCH_PREFIX=work XDG_STATE_HOME="$state" \
  PATH="$fake_bin:$PATH" "$wt" branch telos/demo)
[ "$prefix_out" = "work/demo" ] ||
  fail "WT_BRANCH_PREFIX was not applied: $prefix_out"

printf '# guidance is preserved unless --force\n'
printf 'local note\n' >>"$work/telos/demo/AGENTS.md"
wt_run new telos/demo >/dev/null 2>&1
assert_contains "$(cat "$work/telos/demo/AGENTS.md")" 'local note'
wt_run new --force telos/demo >/dev/null 2>&1
assert_missing "$(cat "$work/telos/demo/AGENTS.md")" 'local note'

printf '# unsafe names are refused\n'
wt_run new ../escape >/dev/null 2>&1 && fail "traversal name was accepted"
wt_run new a/b/c >/dev/null 2>&1 && fail "two-slash name was accepted"
[ ! -e "$work/../escape" ] || fail "traversal created a directory"

printf '# names that are not usable as branches are refused\n'
wt_run new telos/demo.lock >/dev/null 2>&1 &&
  fail ".lock slug was accepted"
wt_run new telos/.hidden >/dev/null 2>&1 &&
  fail "dot-leading slug was accepted"
[ ! -e "$work/telos/demo.lock" ] || fail ".lock slug created a directory"

printf '# clone lands at owner/repo on the workspace branch\n'
clone_out=$(wt_run clone telos/demo "file://$origins/spincyc/alpha" 2>&1) ||
  fail "clone from a URL failed"
assert_contains "$clone_out" 'cloned   spincyc/alpha  on feature/demo'
[ -d "$work/telos/demo/spincyc/alpha/.git" ] ||
  fail "clone did not land at spincyc/alpha"
[ "$(branch_of "$work/telos/demo/spincyc/alpha")" = "feature/demo" ] ||
  fail "clone did not land on the workspace branch"
# The fresh branch tracks the branch the clone arrived on, so status, pull,
# and the unsaved-work test keep working before anything is pushed.
[ "$(upstream_of "$work/telos/demo/spincyc/alpha")" = "origin/main" ] ||
  fail "the workspace branch does not track origin/main"
clone_again=$(wt_run clone telos/demo "file://$origins/spincyc/alpha" 2>&1)
assert_contains "$clone_again" 'ok       spincyc/alpha'

printf '# workspace is inferred from the current directory\n'
(
  cd "$work/telos/demo/spincyc/alpha"
  WT_ROOT="$work" XDG_STATE_HOME="$state" PATH="$fake_bin:$PATH" \
    "$wt" clone "file://$origins/spincyc/beta" >/dev/null 2>&1
) || fail "clone from inside the workspace failed"
[ -d "$work/telos/demo/spincyc/beta/.git" ] ||
  fail "inferred clone did not land at spincyc/beta"
[ "$(branch_of "$work/telos/demo/spincyc/beta")" = "feature/demo" ] ||
  fail "inferred clone did not land on the workspace branch"

printf '# ls reports workspaces and repos\n'
ls_out=$(wt_run ls)
assert_contains "$ls_out" 'telos/demo'
assert_contains "$ls_out" 'telos/bare'
assert_contains "$ls_out" 'spincyc/alpha'
assert_contains "$ls_out" 'spincyc/beta'
assert_contains "$ls_out" 'clean'
assert_contains "$ls_out" '(no repositories)'

printf '# ls reports a dirty worktree\n'
printf 'change\n' >>"$work/telos/demo/spincyc/alpha/README.md"
assert_contains "$(wt_run ls)" 'dirty'

printf '# pwd reports the workspace holding the current directory\n'
mkdir -p -- "$work/telos/demo/spincyc/alpha/deep/deeper"
pwd_out=$(
  cd "$work/telos/demo/spincyc/alpha/deep/deeper"
  WT_ROOT="$work" XDG_STATE_HOME="$state" PATH="$fake_bin:$PATH" "$wt" pwd
) || fail "pwd failed inside a clone"
[ "$pwd_out" = "$work/telos/demo" ] ||
  fail "pwd returned the wrong directory: $pwd_out"
rm -rf -- "$work/telos/demo/spincyc/alpha/deep"
if outside_out=$(cd "$test_root" && wt_run pwd 2>&1); then
  fail "pwd answered outside the workspace root"
fi
assert_contains "$outside_out" 'not inside a workspace under'
if project_out=$(cd "$work/telos" && wt_run pwd 2>&1); then
  fail "pwd answered in a project directory"
fi
assert_contains "$project_out" 'not inside a workspace under'
wt_run pwd telos/demo >/dev/null 2>&1 && fail "pwd accepted an argument"

printf '# path resolves a workspace\n'
[ "$(wt_run path telos/demo)" = "$work/telos/demo" ] ||
  fail "path returned the wrong directory"
wt_run path telos/absent >/dev/null 2>&1 &&
  fail "path accepted a missing workspace"

printf '# git verbs fan out over every repo\n'
git_out=$(wt_run git telos/demo -- rev-parse --abbrev-ref HEAD)
assert_contains "$git_out" '== spincyc/alpha'
assert_contains "$git_out" '== spincyc/beta'
assert_contains "$git_out" 'feature/demo'
fetch_out=$(wt_run fetch telos/demo 2>&1)
assert_contains "$fetch_out" '== spincyc/beta'
status_out=$(wt_run status telos/demo)
assert_contains "$status_out" 'ahead 0 behind 0'
assert_contains "$status_out" 'M README.md'

printf '# a failing git command is reported, not fatal\n'
if git_fail=$(wt_run git telos/demo -- no-such-subcommand 2>&1); then
  fail "a failing git command reported success"
fi
assert_contains "$git_fail" '== spincyc/beta'

printf '# check passes on a healthy layout\n'
check_out=$(wt_run check) || fail "check failed on a healthy layout: $check_out"
assert_contains "$check_out" 'wt check passed.'
assert_contains "$check_out" 'WT_MAX_AGENTS=2'

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

printf '# the launched agent keeps no work ledger\n'
assert_contains "$launch_out" 'aiq_disable=1'

printf '# slots are released when the agent exits\n'
agents_out=$(wt_run agents)
assert_contains "$agents_out" '0 of 2 slots in use'

printf '# max agents is enforced\n'
wt_agent=slow-agent wt_run telos/demo >/dev/null 2>&1 &
first_agent=$!
wt_agent=slow-agent wt_run telos/bare >/dev/null 2>&1 &
second_agent=$!
waited=0
while [ ! -e "$test_root/slow-started" ] && [ "$waited" -lt 100 ]; do
  sleep 0.05
  waited=$((waited + 1))
done
sleep 0.5
busy_out=$(wt_run agents)
assert_contains "$busy_out" '2 of 2 slots in use'
assert_contains "$busy_out" 'workspace=telos/demo'
if third_out=$(wt_agent=slow-agent wt_run telos/demo 2>&1); then
  fail "a third agent started past the limit"
fi
assert_contains "$third_out" 'all 2 agent slots are busy'
: >"$test_root/slow-release"
wait "$first_agent" || fail "the first held agent failed"
wait "$second_agent" || fail "the second held agent failed"
assert_contains "$(wt_run agents)" '0 of 2 slots in use'

printf '# rm refuses unsaved work\n'
if rm_out=$(wt_run rm telos/demo 2>&1); then
  fail "rm discarded a dirty worktree"
fi
assert_contains "$rm_out" 'unsaved  spincyc/alpha'
[ -d "$work/telos/demo" ] || fail "rm removed the workspace anyway"

printf '# rm refuses an unpushed commit in any repository\n'
git -C "$work/telos/demo/spincyc/alpha" checkout --quiet -- README.md
git -C "$work/telos/demo/spincyc/beta" config user.email \
  wt-test@example.invalid
git -C "$work/telos/demo/spincyc/beta" config user.name 'wt test'
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

printf 'ok - wt\n'

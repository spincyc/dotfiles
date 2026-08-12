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
  XDG_STATE_HOME="$state" \
  PATH="$fake_bin:$PATH" \
    "$wt" "$@"
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
printf 'agent cwd=%s slot=%s workspace=%s aiq_disable=%s args=%s\n' \
  "$(pwd -P)" "${WT_AGENT_SLOT:-}" "${WT_WORKSPACE:-}" \
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
assert_contains "$usage_out" 'wt claude feature/telos-sync'
if bad_option=$(wt_run --nope 2>&1); then
  fail "unknown option was accepted"
fi
assert_contains "$bad_option" 'unknown option: --nope'

printf '# workspace creation seeds guidance\n'
created=$(wt_run new feature/demo 2>/dev/null)
[ "$created" = "$work/feature/demo" ] ||
  fail "unexpected workspace path: $created"
[ -f "$work/feature/demo/AGENTS.md" ] || fail "AGENTS.md was not written"
[ -f "$work/feature/demo/CLAUDE.md" ] || fail "CLAUDE.md was not written"
[ -f "$work/feature/demo/GEMINI.md" ] || fail "GEMINI.md was not written"
assert_contains "$(cat "$work/feature/demo/AGENTS.md")" \
  'wt clone feature/demo spincyc/telos'
assert_contains "$(cat "$work/feature/demo/AGENTS.md")" \
  'Every repository lives at `<owner>/<repo>`'
assert_contains "$(cat "$work/feature/demo/AGENTS.md")" 'Do not use `aiq`'
assert_contains "$(cat "$work/feature/demo/AGENTS.md")" 'AIQ_DISABLE'

printf '# bare names take the namespace prefix\n'
wt_run new bare >/dev/null 2>&1
[ -d "$work/feature/bare" ] || fail "bare name did not take the prefix"

printf '# guidance is preserved unless --force\n'
printf 'local note\n' >>"$work/feature/demo/AGENTS.md"
wt_run new feature/demo >/dev/null 2>&1
assert_contains "$(cat "$work/feature/demo/AGENTS.md")" 'local note'
wt_run new --force feature/demo >/dev/null 2>&1
assert_missing "$(cat "$work/feature/demo/AGENTS.md")" 'local note'

printf '# unsafe names are refused\n'
wt_run new ../escape >/dev/null 2>&1 && fail "traversal name was accepted"
wt_run new a/b/c >/dev/null 2>&1 && fail "two-slash name was accepted"
[ ! -e "$work/../escape" ] || fail "traversal created a directory"

printf '# clone lands at owner/repo\n'
wt_run clone feature/demo "file://$origins/spincyc/alpha" >/dev/null 2>&1 ||
  fail "clone from a URL failed"
[ -d "$work/feature/demo/spincyc/alpha/.git" ] ||
  fail "clone did not land at spincyc/alpha"
clone_again=$(wt_run clone feature/demo "file://$origins/spincyc/alpha" 2>&1)
assert_contains "$clone_again" 'ok       spincyc/alpha'

printf '# workspace is inferred from the current directory\n'
(
  cd "$work/feature/demo/spincyc/alpha"
  WT_ROOT="$work" XDG_STATE_HOME="$state" PATH="$fake_bin:$PATH" \
    "$wt" clone "file://$origins/spincyc/beta" >/dev/null 2>&1
) || fail "clone from inside the workspace failed"
[ -d "$work/feature/demo/spincyc/beta/.git" ] ||
  fail "inferred clone did not land at spincyc/beta"

printf '# ls reports workspaces and repos\n'
ls_out=$(wt_run ls)
assert_contains "$ls_out" 'feature/demo'
assert_contains "$ls_out" 'feature/bare'
assert_contains "$ls_out" 'spincyc/alpha'
assert_contains "$ls_out" 'spincyc/beta'
assert_contains "$ls_out" 'clean'
assert_contains "$ls_out" '(no repositories)'

printf '# ls reports a dirty worktree\n'
printf 'change\n' >>"$work/feature/demo/spincyc/alpha/README.md"
assert_contains "$(wt_run ls)" 'dirty'

printf '# path resolves a workspace\n'
[ "$(wt_run path feature/demo)" = "$work/feature/demo" ] ||
  fail "path returned the wrong directory"
wt_run path feature/absent >/dev/null 2>&1 &&
  fail "path accepted a missing workspace"

printf '# git verbs fan out over every repo\n'
git_out=$(wt_run git feature/demo -- rev-parse --abbrev-ref HEAD)
assert_contains "$git_out" '== spincyc/alpha'
assert_contains "$git_out" '== spincyc/beta'
assert_contains "$git_out" 'main'
fetch_out=$(wt_run fetch feature/demo 2>&1)
assert_contains "$fetch_out" '== spincyc/beta'
status_out=$(wt_run status feature/demo)
assert_contains "$status_out" 'ahead 0 behind 0'
assert_contains "$status_out" 'M README.md'

printf '# a failing git command is reported, not fatal\n'
if git_fail=$(wt_run git feature/demo -- no-such-subcommand 2>&1); then
  fail "a failing git command reported success"
fi
assert_contains "$git_fail" '== spincyc/beta'

printf '# check passes on a healthy layout\n'
check_out=$(wt_run check) || fail "check failed on a healthy layout: $check_out"
assert_contains "$check_out" 'wt check passed.'
assert_contains "$check_out" 'WT_MAX_AGENTS=2'

printf '# check fails on a misplaced repository\n'
mkdir -p -- "$work/feature/bad"
git init --quiet -- "$work/feature/bad/spincyc"
if bad_out=$(wt_run check 2>&1); then
  fail "check passed with a repository in an owner directory"
fi
assert_contains "$bad_out" 'is a repository, not an owner directory'
rm -rf -- "$work/feature/bad"

printf '# check fails when the default agent is missing\n'
if missing_out=$(wt_agent=absent-agent wt_run check 2>&1); then
  fail "check passed with a missing default agent"
fi
assert_contains "$missing_out" 'default agent is not installed: absent-agent'

printf '# launching runs the agent in the workspace\n'
launch_out=$(wt_run feature/demo --flag value 2>/dev/null)
assert_contains "$launch_out" "cwd=$work/feature/demo"
assert_contains "$launch_out" 'workspace=feature/demo'
assert_contains "$launch_out" 'args=--flag value'
assert_contains "$launch_out" 'slot=1'

printf '# the launched agent keeps no work ledger\n'
assert_contains "$launch_out" 'aiq_disable=1'

printf '# slots are released when the agent exits\n'
agents_out=$(wt_run agents)
assert_contains "$agents_out" '0 of 2 slots in use'

printf '# max agents is enforced\n'
wt_agent=slow-agent wt_run feature/demo >/dev/null 2>&1 &
first_agent=$!
wt_agent=slow-agent wt_run feature/bare >/dev/null 2>&1 &
second_agent=$!
waited=0
while [ ! -e "$test_root/slow-started" ] && [ "$waited" -lt 100 ]; do
  sleep 0.05
  waited=$((waited + 1))
done
sleep 0.5
busy_out=$(wt_run agents)
assert_contains "$busy_out" '2 of 2 slots in use'
assert_contains "$busy_out" 'workspace=feature/demo'
if third_out=$(wt_agent=slow-agent wt_run feature/demo 2>&1); then
  fail "a third agent started past the limit"
fi
assert_contains "$third_out" 'all 2 agent slots are busy'
: >"$test_root/slow-release"
wait "$first_agent" || fail "the first held agent failed"
wait "$second_agent" || fail "the second held agent failed"
assert_contains "$(wt_run agents)" '0 of 2 slots in use'

printf '# rm refuses unsaved work\n'
if rm_out=$(wt_run rm feature/demo 2>&1); then
  fail "rm discarded a dirty worktree"
fi
assert_contains "$rm_out" 'unsaved  spincyc/alpha'
[ -d "$work/feature/demo" ] || fail "rm removed the workspace anyway"

printf '# rm refuses an unpushed commit in any repository\n'
git -C "$work/feature/demo/spincyc/alpha" checkout --quiet -- README.md
git -C "$work/feature/demo/spincyc/beta" config user.email \
  wt-test@example.invalid
git -C "$work/feature/demo/spincyc/beta" config user.name 'wt test'
printf 'local\n' >"$work/feature/demo/spincyc/beta/local.md"
git -C "$work/feature/demo/spincyc/beta" add local.md
git -C "$work/feature/demo/spincyc/beta" commit --quiet -m 'local'
if rm_out=$(wt_run rm feature/demo 2>&1); then
  fail "rm discarded an unpushed commit"
fi
assert_contains "$rm_out" 'unsaved  spincyc/beta'

printf '# rm removes a clean workspace and honours --force\n'
wt_run rm feature/bare >/dev/null || fail "rm refused a clean workspace"
[ ! -e "$work/feature/bare" ] || fail "rm left the workspace in place"
wt_run rm --force feature/demo >/dev/null || fail "rm --force failed"
[ ! -e "$work/feature/demo" ] || fail "rm --force left the workspace in place"

printf '# rm stays inside the workspace root\n'
mkdir -p -- "$test_root/outside"
ln -s -- "$test_root/outside" "$work/feature/linked"
if link_out=$(wt_run rm feature/linked 2>&1); then
  fail "rm followed a symlinked workspace"
fi
assert_contains "$link_out" 'must not be a symlink'
[ -d "$test_root/outside" ] || fail "rm removed the symlink target"

printf 'ok - wt\n'

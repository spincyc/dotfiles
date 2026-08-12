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
  WT_MAX_AGENTS="${wt_max_agents:-2}" \
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
# machine that happens to have a real claude or codex, and `wt check` fails on
# a clean CI box for a reason that has nothing to do with wt.
for agent_name in claude codex; do
  # A plain copy is enough now that the script reports its own $0: identical
  # copies that said nothing made `wt claude X` and `wt X` indistinguishable,
  # so the dispatch test could not fail.
  cp -- "$fake_bin/fake-agent" "$fake_bin/$agent_name"
  chmod 755 -- "$fake_bin/$agent_name"
done

# A stand-in gh that can only refuse: bare owner/repo clones are the one path
# that would otherwise reach the network, and this makes that impossible
# rather than merely unused.
cat >"$fake_bin/gh" <<'EOF'
#!/bin/sh
printf 'gh: the wt suite is offline: %s\n' "$*" >&2
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
if deep_out=$(wt_run new a/b/c 2>&1); then
  fail "two-slash name was accepted"
fi
assert_contains "$deep_out" 'not a usable workspace name: a/b/c'
[ ! -e "$work/../escape" ] || fail "traversal created a directory"

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
assert_contains "$(wt_run telos/demo 2>/dev/null)" 'agent=fake-agent'

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
# Each agent has its own sentinel, and the verdict comes from wt rather than
# from a fixed sleep: under load the second slot is not taken the moment the
# first one is, and a shared sentinel cannot tell the two apart.
wait_for '[ -e "$test_root/slow-started-1" ] &&
  [ -e "$test_root/slow-started-2" ]'
wait_for 'wt_run agents | grep -Fq "2 of 2 slots in use"'
busy_out=$(wt_run agents)
assert_contains "$busy_out" '2 of 2 slots in use'
assert_contains "$busy_out" 'workspace=telos/demo'
assert_contains "$busy_out" 'workspace=telos/bare'
# Slot exhaustion is EX_TEMPFAIL: the request was fine, the resource was not,
# which is what makes `until wt claude telos/foo; do sleep 30; done` writable.
third_status=0
third_out=$(wt_agent=slow-agent wt_run telos/demo 2>&1) || third_status=$?
[ "$third_status" -eq 75 ] ||
  fail "a third agent did not exit EX_TEMPFAIL: $third_status"
assert_contains "$third_out" 'all 2 agent slots are busy'
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
rm -f -- "$state/wt/agents/slot-1.info"
assert_contains "$(wt_run sweep telos/idle)" 'an agent is running here'
[ -d "$work/telos/idle" ] || fail "sweep trusted an unnamed busy slot"
: >"$test_root/slow-release"
wait "$first_agent" || fail "the first held agent failed"
wait "$second_agent" || fail "the second held agent failed"
assert_contains "$(wt_run agents)" '0 of 2 slots in use'
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

printf '# a sweep refuses a slot limit it cannot read\n'
wt_root="$test_root/limits"
wt_run new limits/keep >/dev/null 2>&1
# An unusable limit made the slot survey cover nothing, which read as "no
# agent is running anywhere" and swept workspaces out from under live agents.
if limit_sweep=$(wt_max_agents=lots wt_run sweep 2>&1); then
  fail "a sweep proceeded without knowing which workspaces hold an agent"
fi
assert_contains "$limit_sweep" 'WT_MAX_AGENTS is not a positive integer: lots'
assert_contains "$limit_sweep" 'refusing to sweep'
[ -d "$wt_root/limits/keep" ] || fail "the sweep deleted a workspace blind"
if limit_tidy=$(wt_max_agents=lots wt_run tidy 2>&1); then
  fail "a tidy proceeded on an unreadable slot limit"
fi
assert_contains "$limit_tidy" 'WT_MAX_AGENTS is not a positive integer: lots'
if limit_agents=$(wt_max_agents=0 wt_run agents 2>&1); then
  fail "agents accepted a zero limit"
fi
assert_contains "$limit_agents" 'WT_MAX_AGENTS is not a positive integer: 0'
if limit_check=$(wt_max_agents=-1 wt_run check 2>&1); then
  fail "check passed with an unusable slot limit"
fi
assert_contains "$limit_check" 'WT_MAX_AGENTS is not a positive integer: -1'

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

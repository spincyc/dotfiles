#!/bin/sh
set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
test_root=$(mktemp -d "${TMPDIR:-/tmp}/dotfiles-install-test.XXXXXX")
test_repo="$test_root/repo"
test_home="$test_root/home"
test_state="$test_root/state"
ml4w_root="$test_home/.mydotfiles/com.ml4w.dotfiles"
profile_relative=profiles/ml4w/legacy-2.9.9.5
profile_dir="$test_repo/$profile_relative"

cleanup() {
  case "$test_root" in
    "${TMPDIR:-/tmp}"/dotfiles-install-test.*)
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

assert_file_contains() {
  grep -Fq -- "$2" "$1" ||
    fail "$1 does not contain: $2"
}

run_profile() {
  env HOME="$test_home" XDG_STATE_HOME="$test_state" \
    "$test_repo/install.sh" --profile ml4w \
    --host-profile ultrawide-desktop
}

check_profile() {
  env HOME="$test_home" XDG_STATE_HOME="$test_state" \
    "$test_repo/install.sh" --check --profile ml4w \
    --host-profile ultrawide-desktop
}

write_live_metadata() {
  live_version=$1
  printf '{"active":"com.ml4w.dotfiles"}\n' \
    >"$test_home/.config/ml4w-dotfiles-installer/active.json"
  printf '%s\n' \
    '{"id":"com.ml4w.dotfiles","version":"'"$live_version"'","source":"https://github.com/mylinuxforwork/dotfiles.git","subfolder":"dotfiles"}' \
    >"$ml4w_root/config.dotinst"
}

mkdir -p -- "$test_repo"
cp -a -- "$repo_dir/." "$test_repo"

find "$profile_dir/common" \
  "$profile_dir/hosts/ultrawide-desktop" -type f -printf '%P\n' |
  sort >"$test_root/payload-paths"
awk -F '|' '!/^#/ && NF { print $3 }' "$profile_dir/manifest" |
  sort >"$test_root/manifest-paths"
diff -u "$test_root/payload-paths" "$test_root/manifest-paths" ||
  fail "manifest and payload file sets differ"

mkdir -p -- \
  "$test_state" \
  "$test_home/.config/ml4w-dotfiles-installer" \
  "$ml4w_root/.config/hypr/conf" \
  "$ml4w_root/.config/kitty" \
  "$ml4w_root/.config/ml4w/version" \
  "$ml4w_root/.config/swaync" \
  "$ml4w_root/.config/waybar"

write_live_metadata 2.9.9.5
printf '2.9.9.5\n' >"$ml4w_root/.config/ml4w/version/name"
printf 'source = ~/.config/hypr/conf/custom.conf\n' \
  >"$ml4w_root/.config/hypr/hyprland.conf"
printf 'include $HOME/.config/kitty/custom.conf\n' \
  >"$ml4w_root/.config/kitty/kitty.conf"
printf '%s\n' \
  'if [ -f ~/.config/waybar/themes${arrThemes[0]}/config-custom ]; then' \
  '    config_file="config-custom"' \
  'fi' \
  'if [ -f ~/.config/waybar/themes${arrThemes[1]}/style-custom.css ]; then' \
  '    style_file="style-custom.css"' \
  'fi' \
  >"$ml4w_root/.config/waybar/launch.sh"
printf 'legacy custom configuration\n' \
  >"$ml4w_root/.config/hypr/conf/custom.conf"
printf 'legacy shell configuration\n' >"$test_home/.zshrc"

for config_name in hypr kitty ml4w swaync waybar; do
  ln -s -- "$ml4w_root/.config/$config_name" \
    "$test_home/.config/$config_name"
done

if ! run_profile >"$test_root/install.out" 2>&1; then
  sed -n '1,200p' "$test_root/install.out" >&2
  fail "initial profile install failed"
fi

while IFS='|' read -r layer expected_mode relative_path; do
  case "$layer" in
    ""|\#*) continue ;;
    common)
      source_file="$profile_dir/common/$relative_path"
      ;;
    host:ultrawide-desktop)
      source_file="$profile_dir/hosts/ultrawide-desktop/$relative_path"
      ;;
    *)
      fail "unexpected manifest layer in fixture: $layer"
      ;;
  esac
  target_file="$ml4w_root/$relative_path"
  [ -f "$target_file" ] || fail "missing installed file: $target_file"
  [ ! -L "$target_file" ] || fail "installed a symlink: $target_file"
  cmp -s -- "$source_file" "$target_file" ||
    fail "installed content differs: $target_file"
  actual_mode=0$(stat -c %a -- "$target_file")
  [ "$actual_mode" = "$expected_mode" ] ||
    fail "unexpected mode $actual_mode: $target_file"
done <"$profile_dir/manifest"

for core_target in \
  .zshrc \
  .tmux.conf \
  .codex/AGENTS.md \
  .codex/ai-guidance \
  .claude/CLAUDE.md \
  .claude/ai-guidance \
  .gemini/GEMINI.md \
  .gemini/ai-guidance
do
  [ -L "$test_home/$core_target" ] ||
    fail "portable core link is missing: $core_target"
done

# Seeds are copied, never linked: Claude Code and the tool integrations own the
# live file once it exists.
for seed_target in .claude/settings.json; do
  [ ! -L "$test_home/$seed_target" ] ||
    fail "seed was linked instead of copied: $seed_target"
  [ -f "$test_home/$seed_target" ] ||
    fail "seed was not copied: $seed_target"
done

core_backup=$(find "$test_state/dotfiles/backups" -type f \
  -path '*/.zshrc' -print)
[ -n "$core_backup" ] || fail "legacy core file was not backed up"
[ "$(sed -n '1p' "$core_backup")" = \
  "legacy shell configuration" ] ||
  fail "core backup content differs"

initial_backup=$(find "$test_state/dotfiles/backups" -type f \
  -path '*/ml4w/.config/hypr/conf/custom.conf' -print)
[ -n "$initial_backup" ] || fail "legacy ML4W file was not backed up"
[ "$(sed -n '1p' "$initial_backup")" = \
  "legacy custom configuration" ] ||
  fail "ML4W backup content differs"
[ "$(stat -c %a -- "$initial_backup")" = 644 ] ||
  fail "ML4W backup did not preserve the original mode"
initial_backup_root=${initial_backup%%/ml4w/*}
[ "$(stat -c %a -- "$initial_backup_root")" = 700 ] ||
  fail "ML4W backup directory is not private"

check_profile >"$test_root/check.out"
backup_count_before=$(find "$test_state/dotfiles/backups" \
  -mindepth 1 -maxdepth 1 -type d -print | wc -l)
run_profile >"$test_root/reinstall.out"
backup_count_after=$(find "$test_state/dotfiles/backups" \
  -mindepth 1 -maxdepth 1 -type d -print | wc -l)
[ "$backup_count_before" -eq "$backup_count_after" ] ||
  fail "idempotent reinstall created another backup directory"

printf '\n# deliberate drift\n' \
  >>"$ml4w_root/.config/hypr/conf/custom.conf"
if check_profile >"$test_root/drift.out" 2>&1; then
  fail "--check accepted content drift"
fi
assert_file_contains "$test_root/drift.out" \
  "drift    $ml4w_root/.config/hypr/conf/custom.conf"
run_profile >"$test_root/repair.out"
check_profile >"$test_root/repaired-check.out"

printf '\n# gate sentinel\n' \
  >>"$ml4w_root/.config/hypr/conf/custom.conf"
write_live_metadata 0.0.0
if run_profile >"$test_root/version-gate.out" 2>&1; then
  fail "version gate accepted an incompatible profile"
fi
assert_file_contains "$test_root/version-gate.out" \
  "unexpected live ML4W version: 0.0.0"
assert_file_contains "$ml4w_root/.config/hypr/conf/custom.conf" \
  "# gate sentinel"
write_live_metadata 2.9.9.5
run_profile >"$test_root/post-gate-repair.out"

kitty_custom="$ml4w_root/.config/kitty/custom.conf"
external_target="$test_root/external-target"
printf 'external sentinel\n' >"$external_target"
rm -- "$kitty_custom"
ln -s -- "$external_target" "$kitty_custom"
if check_profile >"$test_root/symlink-target.out" 2>&1; then
  fail "target symlink was accepted"
fi
assert_file_contains "$test_root/symlink-target.out" \
  "target file is a symlink: $kitty_custom"
[ "$(sed -n '1p' "$external_target")" = "external sentinel" ] ||
  fail "target symlink escaped the ML4W sandbox"
rm -- "$kitty_custom"
cp -- "$profile_dir/common/.config/kitty/custom.conf" "$kitty_custom"
chmod 0644 -- "$kitty_custom"

hardlink_copy="$test_root/hardlink-copy"
ln -- "$kitty_custom" "$hardlink_copy"
if check_profile >"$test_root/hardlink-target.out" 2>&1; then
  fail "hard-linked target was accepted"
fi
assert_file_contains "$test_root/hardlink-target.out" \
  "hard-linked files are not supported: $kitty_custom"
rm -- "$hardlink_copy"

waybar_theme_parent="$ml4w_root/.config/waybar/themes/ml4w-glass-center"
saved_default="$test_root/saved-default"
external_directory="$test_root/external-directory"
mv -- "$waybar_theme_parent/default" "$saved_default"
mkdir -- "$external_directory"
ln -s -- "$external_directory" "$waybar_theme_parent/default"
if check_profile >"$test_root/symlink-parent.out" 2>&1; then
  fail "parent symlink was accepted"
fi
assert_file_contains "$test_root/symlink-parent.out" \
  "target parent is a symlink: $waybar_theme_parent/default"
[ -z "$(find "$external_directory" -mindepth 1 -print -quit)" ] ||
  fail "parent symlink escaped the ML4W sandbox"
rm -- "$waybar_theme_parent/default"
mv -- "$saved_default" "$waybar_theme_parent/default"

printf '%s\n' '2.9.9.5' 'unexpected trailing line' \
  >"$ml4w_root/.config/ml4w/version/name"
if check_profile >"$test_root/version-name.out" 2>&1; then
  fail "version-name gate accepted trailing content"
fi
assert_file_contains "$test_root/version-name.out" \
  "unexpected live ML4W version name"
printf '2.9.9.5\n' >"$ml4w_root/.config/ml4w/version/name"

waybar_launcher="$ml4w_root/.config/waybar/launch.sh"
waybar_launcher_saved="$test_root/waybar-launch.saved"
cp -p -- "$waybar_launcher" "$waybar_launcher_saved"
printf '%s\n' '# config-custom' '# style-custom.css' \
  >"$waybar_launcher"
if check_profile >"$test_root/loader-gate.out" 2>&1; then
  fail "Waybar loader gate accepted comment-only hooks"
fi
assert_file_contains "$test_root/loader-gate.out" \
  "live Waybar launcher does not support config-custom"
cp -p -- "$waybar_launcher_saved" "$waybar_launcher"

gemini_saved="$test_root/gemini-saved"
external_core_parent="$test_root/external-core-parent"
mv -- "$test_home/.gemini" "$gemini_saved"
mkdir -- "$external_core_parent"
printf 'external core sentinel\n' \
  >"$external_core_parent/GEMINI.md"
ln -s -- "$external_core_parent" "$test_home/.gemini"
if env HOME="$test_home" XDG_STATE_HOME="$test_state" \
  "$test_repo/install.sh" >"$test_root/core-parent.out" 2>&1; then
  fail "core installer accepted a symlinked parent"
fi
assert_file_contains "$test_root/core-parent.out" \
  "core target parent is a symlink: $test_home/.gemini"
[ "$(sed -n '1p' "$external_core_parent/GEMINI.md")" = \
  "external core sentinel" ] ||
  fail "core parent symlink escaped the test HOME"
rm -- "$test_home/.gemini"
mv -- "$gemini_saved" "$test_home/.gemini"

state_link="$test_root/state-link"
ln -s -- "$test_state" "$state_link"
rm -- "$test_home/.zshrc"
printf 'state-root sentinel\n' >"$test_home/.zshrc"
if env HOME="$test_home" XDG_STATE_HOME="$state_link" \
  "$test_repo/install.sh" >"$test_root/state-link.out" 2>&1; then
  fail "installer accepted a symlinked state root"
fi
assert_file_contains "$test_root/state-link.out" \
  "directory must not be a symlink: $state_link"
assert_file_contains "$test_home/.zshrc" "state-root sentinel"
run_profile >"$test_root/state-link-repair.out"

exec 8<>"$test_home/.local/state/dotfiles/install.lock"
flock -n 8 || fail "test could not acquire the installer lock"
if run_profile >"$test_root/concurrent-install.out" 2>&1; then
  fail "concurrent profile install was accepted"
fi
assert_file_contains "$test_root/concurrent-install.out" \
  "another dotfiles installer is running"
flock -u 8
exec 8>&-

rm -- "$test_home/.zshrc"
mkfifo -- "$test_home/.zshrc"
printf '\n# core preflight sentinel\n' \
  >>"$ml4w_root/.config/hypr/conf/custom.conf"
if run_profile >"$test_root/core-preflight.out" 2>&1; then
  fail "profile deploy accepted an unsupported core target"
fi
assert_file_contains "$test_root/core-preflight.out" \
  "unsupported core target type: $test_home/.zshrc"
assert_file_contains "$ml4w_root/.config/hypr/conf/custom.conf" \
  "# core preflight sentinel"
if env HOME="$test_home" XDG_STATE_HOME="$test_state" \
  "$test_repo/install.sh" --check \
  >"$test_root/core-check-parity.out" 2>&1; then
  fail "core check accepted an unsupported target"
fi
assert_file_contains "$test_root/core-check-parity.out" \
  "unsupported core target type: $test_home/.zshrc"
rm -- "$test_home/.zshrc"
run_profile >"$test_root/core-preflight-repair.out"

core_source_saved="$test_root/AI_GUIDANCE.saved"
mv -- "$test_repo/AI_GUIDANCE.md" "$core_source_saved"
if env HOME="$test_home" XDG_STATE_HOME="$test_state" \
  "$test_repo/install.sh" --check \
  >"$test_root/missing-core-source.out" 2>&1; then
  fail "core check accepted a missing source"
fi
assert_file_contains "$test_root/missing-core-source.out" \
  "managed core source is missing: $test_repo/AI_GUIDANCE.md"
mv -- "$core_source_saved" "$test_repo/AI_GUIDANCE.md"

printf '\n# prevalidation sentinel\n' \
  >>"$ml4w_root/.config/hypr/conf/custom.conf"
printf 'common|0644|../escape\n' >>"$profile_dir/manifest"
if run_profile >"$test_root/path-traversal.out" 2>&1; then
  fail "manifest path traversal was accepted"
fi
assert_file_contains "$test_root/path-traversal.out" \
  "dot path components are not allowed: ../escape"
assert_file_contains "$ml4w_root/.config/hypr/conf/custom.conf" \
  "# prevalidation sentinel"
[ ! -e "$ml4w_root/../escape" ] ||
  fail "manifest path escaped the ML4W sandbox"

if env HOME="$test_home" XDG_STATE_HOME="$test_state" \
  "$test_repo/install.sh" --profile ml4w \
  >"$test_root/missing-host.out" 2>&1; then
  fail "ML4W profile accepted a missing host profile"
fi

printf 'ok - installer profile, drift, backup, and safety checks passed\n'

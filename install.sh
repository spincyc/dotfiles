#!/bin/sh
set -eu
set -f

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
state_root="${XDG_STATE_HOME:-$HOME/.local/state}"
state_dir="$state_root/dotfiles"
lock_state_root="$HOME/.local/state"
lock_state_dir="$lock_state_root/dotfiles"
backup_dir="$state_dir/backups/$(date +%Y%m%d-%H%M%S)-$$"
mode=install
profile=core
host_profile=
mode_seen=0
profile_seen=0
host_seen=0
failed=0
manifest_work_dir=
manifest_entries_file=
manifest_seen_file=
pending_temp=
pending_core_stage=
pending_core_target=
pending_core_backup=
backup_dir_ready=0
install_lock_ready=0
user_id=

usage() {
  cat <<'EOF'
Usage: ./install.sh [--check | --update]
       ./install.sh [--check | --update] --profile ml4w \
         --host-profile ultrawide-desktop

  no option       Back up conflicts and link the portable core profile
  --check         Report drift without changing managed files
  --update        Fast-forward the repository, then install
  --profile       Also copy an explicit desktop profile into its ML4W sandbox
  --host-profile  Select the reviewed machine-specific desktop layer
EOF
}

usage_error() {
  usage >&2
  exit 2
}

die() {
  printf 'error: %s\n' "$*" >&2
  exit 2
}

cleanup() {
  if [ -n "$pending_core_backup" ] &&
     { [ -e "$pending_core_backup" ] ||
       [ -L "$pending_core_backup" ]; } &&
     [ -n "$pending_core_target" ] &&
     [ ! -e "$pending_core_target" ] &&
     [ ! -L "$pending_core_target" ]; then
    mv -- "$pending_core_backup" "$pending_core_target" 2>/dev/null || :
  fi
  if [ -n "$pending_core_stage" ] &&
     [ -d "$pending_core_stage" ] &&
     [ ! -L "$pending_core_stage" ]; then
    rm -f -- "$pending_core_stage/link"
    rmdir -- "$pending_core_stage" 2>/dev/null || :
  fi
  if [ -n "$pending_temp" ] && [ -f "$pending_temp" ] &&
     [ ! -L "$pending_temp" ]; then
    rm -f -- "$pending_temp"
  fi
  if [ -n "$manifest_entries_file" ]; then
    rm -f -- "$manifest_entries_file"
  fi
  if [ -n "$manifest_seen_file" ]; then
    rm -f -- "$manifest_seen_file"
  fi
  if [ -n "$manifest_work_dir" ] && [ -d "$manifest_work_dir" ] &&
     [ ! -L "$manifest_work_dir" ]; then
    rmdir -- "$manifest_work_dir" 2>/dev/null || :
  fi
}

trap cleanup 0
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

while [ "$#" -gt 0 ]; do
  case "$1" in
    --check)
      [ "$mode_seen" -eq 0 ] || usage_error
      mode=check
      mode_seen=1
      ;;
    --update)
      [ "$mode_seen" -eq 0 ] || usage_error
      mode=update
      mode_seen=1
      ;;
    --profile)
      [ "$profile_seen" -eq 0 ] || usage_error
      shift
      [ "$#" -gt 0 ] || usage_error
      profile=$1
      profile_seen=1
      ;;
    --host-profile)
      [ "$host_seen" -eq 0 ] || usage_error
      shift
      [ "$#" -gt 0 ] || usage_error
      host_profile=$1
      host_seen=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage_error
      ;;
  esac
  shift
done

case "$profile" in
  core|ml4w) ;;
  *) usage_error ;;
esac

if [ "$profile" = ml4w ]; then
  [ "$host_profile" = ultrawide-desktop ] || usage_error
elif [ -n "$host_profile" ]; then
  usage_error
fi

user_id=$(id -u)

if [ "$mode" = update ]; then
  [ "$(git -C "$repo_dir" symbolic-ref --quiet --short HEAD)" = main ] ||
    die "--update requires the main branch"
  [ "$(git -C "$repo_dir" config --get branch.main.remote)" = origin ] ||
    die "--update requires main to track origin"
  [ "$(git -C "$repo_dir" config --get branch.main.merge)" = \
    refs/heads/main ] ||
    die "--update requires main to track origin/main"
  origin_url=$(git -C "$repo_dir" remote get-url origin)
  case "$origin_url" in
    https://github.com/spincyc/dotfiles.git|\
git@github.com:spincyc/dotfiles.git)
      ;;
    *)
      die "--update refuses unexpected origin: $origin_url"
      ;;
  esac
  [ -z "$(git -C "$repo_dir" status --porcelain \
    --untracked-files=normal)" ] ||
    die "--update requires a clean worktree"
  git -C "$repo_dir" pull --ff-only --no-rebase --no-autostash \
    origin main
  if [ "$profile" = ml4w ]; then
    exec "$repo_dir/install.sh" --profile ml4w \
      --host-profile "$host_profile"
  fi
  exec "$repo_dir/install.sh"
fi

managed_links="
.zshrc:.zshrc
.tmux.conf:.tmux.conf
AI_GUIDANCE.md:.codex/AGENTS.md
ai-guidance:.codex/ai-guidance
AI_GUIDANCE.md:.claude/CLAUDE.md
ai-guidance:.claude/ai-guidance
.claude/settings.json:.claude/settings.json
AI_GUIDANCE.md:.gemini/GEMINI.md
ai-guidance:.gemini/ai-guidance
"

require_command() {
  command -v "$1" >/dev/null 2>&1 ||
    die "required command is unavailable: $1"
}

normalized_mode_for_file() {
  normalized_mode_path=$1
  normalized_mode_value=$(stat -c %a -- "$normalized_mode_path")
  case "$normalized_mode_value" in
    [0-7])
      printf '00%s\n' "$normalized_mode_value"
      ;;
    [0-7][0-7])
      printf '0%s\n' "$normalized_mode_value"
      ;;
    [0-7][0-7][0-7])
      printf '%s\n' "$normalized_mode_value"
      ;;
    *)
      die "special mode bits are not supported: $normalized_mode_path"
      ;;
  esac
}

assert_not_group_other_writable() {
  safe_mode_path=$1
  safe_mode_value=$(normalized_mode_for_file "$safe_mode_path")
  safe_group_other=${safe_mode_value#?}
  case "$safe_group_other" in
    [2367]?|?[2367])
      die "path is group- or world-writable: $safe_mode_path"
      ;;
  esac
}

assert_owned_directory() {
  owned_directory_path=$1
  [ -d "$owned_directory_path" ] ||
    die "required directory is missing: $owned_directory_path"
  [ ! -L "$owned_directory_path" ] ||
    die "directory must not be a symlink: $owned_directory_path"
  owned_directory_canonical=$(readlink -f -- "$owned_directory_path") ||
    die "cannot resolve directory: $owned_directory_path"
  [ "$owned_directory_canonical" = "$owned_directory_path" ] ||
    die "directory path traverses a symlink: $owned_directory_path"
  [ "$(stat -c %u -- "$owned_directory_path")" = "$user_id" ] ||
    die "directory is not owned by the current user: $owned_directory_path"
  assert_not_group_other_writable "$owned_directory_path"
}

assert_regular_owned_file() {
  regular_file_path=$1
  [ -f "$regular_file_path" ] ||
    die "required regular file is missing: $regular_file_path"
  [ ! -L "$regular_file_path" ] ||
    die "file must not be a symlink: $regular_file_path"
  regular_file_canonical=$(readlink -f -- "$regular_file_path") ||
    die "cannot resolve regular file: $regular_file_path"
  [ "$regular_file_canonical" = "$regular_file_path" ] ||
    die "file path traverses a symlink: $regular_file_path"
  [ "$(stat -c %u -- "$regular_file_path")" = "$user_id" ] ||
    die "file is not owned by the current user: $regular_file_path"
  [ "$(stat -c %h -- "$regular_file_path")" = 1 ] ||
    die "hard-linked files are not supported: $regular_file_path"
  assert_not_group_other_writable "$regular_file_path"
}

manifest_mode_for_file() {
  manifest_mode_path=$1
  printf '0%s\n' "$(normalized_mode_for_file "$manifest_mode_path")"
}

ensure_owned_relative_directory() {
  relative_directory_path=$1
  relative_creation_mode=$2
  relative_component_path=$HOME

  assert_owned_directory "$HOME"
  relative_old_ifs=$IFS
  IFS=/
  set -- $relative_directory_path
  IFS=$relative_old_ifs
  for relative_component in "$@"; do
    relative_component_path="$relative_component_path/$relative_component"
    if [ -L "$relative_component_path" ]; then
      die "directory must not be a symlink: $relative_component_path"
    fi
    if [ -e "$relative_component_path" ]; then
      assert_owned_directory "$relative_component_path"
    else
      mkdir -- "$relative_component_path"
      chmod "$relative_creation_mode" -- "$relative_component_path"
    fi
  done
}

ensure_private_child_directory() {
  private_parent_path=$1
  private_child_name=$2
  private_child_path="$private_parent_path/$private_child_name"

  assert_owned_directory "$private_parent_path"
  if [ -L "$private_child_path" ]; then
    die "directory must not be a symlink: $private_child_path"
  fi
  if [ -e "$private_child_path" ]; then
    assert_owned_directory "$private_child_path"
  else
    mkdir -- "$private_child_path"
  fi
  chmod 700 -- "$private_child_path"
}

ensure_state_directory_tree() {
  case "$state_root" in
    /*) ;;
    *) die "state directory must be absolute: $state_root" ;;
  esac
  case "$state_root" in
    "$HOME")
      assert_owned_directory "$HOME"
      ;;
    "$HOME"/*)
      state_relative_path=${state_root#"$HOME"/}
      ensure_owned_relative_directory "$state_relative_path" 700
      ;;
    *)
      assert_owned_directory "$state_root"
      ;;
  esac
  ensure_private_child_directory "$state_root" dotfiles
  ensure_private_child_directory "$state_dir" backups
}

acquire_install_lock() {
  if [ "$install_lock_ready" -eq 1 ]; then
    return 0
  fi
  require_command flock
  ensure_owned_relative_directory .local/state 700
  ensure_private_child_directory "$lock_state_root" dotfiles
  install_lock_path="$lock_state_dir/install.lock"
  [ ! -L "$install_lock_path" ] ||
    die "installer lock is a symlink: $install_lock_path"
  if [ -e "$install_lock_path" ]; then
    assert_regular_owned_file "$install_lock_path"
  else
    (umask 077 && : >"$install_lock_path")
  fi
  chmod 600 -- "$install_lock_path"
  exec 9<>"$install_lock_path"
  flock -n 9 ||
    die "another dotfiles installer is running"
  install_lock_ready=1
}

ensure_backup_dir() {
  if [ "$backup_dir_ready" -eq 1 ]; then
    return 0
  fi
  ensure_state_directory_tree
  [ ! -e "$backup_dir" ] && [ ! -L "$backup_dir" ] ||
    die "backup leaf already exists: $backup_dir"
  (umask 077 && mkdir -- "$backup_dir")
  chmod 700 -- "$backup_dir"
  backup_dir_ready=1
}

validate_core_source() {
  core_source_path=$1
  if [ -f "$core_source_path" ]; then
    assert_regular_owned_file "$core_source_path"
  elif [ -d "$core_source_path" ]; then
    assert_owned_directory "$core_source_path"
  else
    die "managed core source is missing: $core_source_path"
  fi
  core_source_canonical=$(readlink -f -- "$core_source_path") ||
    die "cannot resolve managed core source: $core_source_path"
  [ -n "$core_source_canonical" ] ||
    die "managed core source resolved empty: $core_source_path"
}

prepare_core_target_parent() {
  core_target_relative=$1
  core_target_create=$2
  core_parent_relative=${core_target_relative%/*}
  core_parent_path=$HOME

  assert_owned_directory "$HOME"
  if [ "$core_parent_relative" = "$core_target_relative" ]; then
    return 0
  fi

  core_parent_old_ifs=$IFS
  IFS=/
  set -- $core_parent_relative
  IFS=$core_parent_old_ifs
  for core_parent_component in "$@"; do
    core_parent_path="$core_parent_path/$core_parent_component"
    if [ -L "$core_parent_path" ]; then
      die "core target parent is a symlink: $core_parent_path"
    fi
    if [ -e "$core_parent_path" ]; then
      assert_owned_directory "$core_parent_path"
    elif [ "$core_target_create" -eq 1 ]; then
      mkdir -- "$core_parent_path"
      chmod 755 -- "$core_parent_path"
    else
      return 1
    fi
  done
}

core_link_matches_source() {
  core_link_target=$1
  core_link_source_canonical=$2
  [ -L "$core_link_target" ] &&
    [ -e "$core_link_target" ] ||
    return 1
  core_target_canonical=$(readlink -f -- "$core_link_target") ||
    return 1
  [ -n "$core_target_canonical" ] &&
    [ "$core_target_canonical" = "$core_link_source_canonical" ]
}

validate_core_conflict() {
  core_conflict_path=$1
  if [ -L "$core_conflict_path" ]; then
    [ "$(stat -c %u -- "$core_conflict_path")" = "$user_id" ] ||
      die "core target symlink ownership mismatch: $core_conflict_path"
  elif [ -f "$core_conflict_path" ]; then
    assert_regular_owned_file "$core_conflict_path"
  elif [ -d "$core_conflict_path" ]; then
    assert_owned_directory "$core_conflict_path"
  else
    die "unsupported core target type: $core_conflict_path"
  fi
}

preflight_core_profile() {
  for preflight_link in $managed_links; do
    preflight_source_name=${preflight_link%%:*}
    preflight_target_name=${preflight_link#*:}
    preflight_source_path="$repo_dir/$preflight_source_name"
    preflight_target_path="$HOME/$preflight_target_name"

    validate_core_source "$preflight_source_path"
    if ! prepare_core_target_parent "$preflight_target_name" 0; then
      continue
    fi
    if core_link_matches_source "$preflight_target_path" \
      "$core_source_canonical"; then
      continue
    fi
    if [ -e "$preflight_target_path" ] ||
       [ -L "$preflight_target_path" ]; then
      validate_core_conflict "$preflight_target_path"
    fi
  done
}

install_core_link() {
  core_install_source=$1
  core_install_target=$2
  core_install_name=$3

  prepare_core_target_parent "$core_install_name" 1
  core_install_parent=$(dirname -- "$core_install_target")
  pending_core_stage=$(mktemp -d \
    "$core_install_parent/.dotfiles-link.XXXXXX")
  ln -s -- "$core_install_source" "$pending_core_stage/link"

  if [ -e "$core_install_target" ] || [ -L "$core_install_target" ]; then
    validate_core_conflict "$core_install_target"
    ensure_backup_dir
    pending_core_backup="$backup_dir/$core_install_name"
    (umask 077 && mkdir -p -- \
      "$(dirname -- "$pending_core_backup")")
    pending_core_target=$core_install_target
    mv -- "$core_install_target" "$pending_core_backup"
    printf 'backup   %s -> %s\n' "$core_install_target" \
      "$pending_core_backup"
  fi

  mv -- "$pending_core_stage/link" "$core_install_target"
  rmdir -- "$pending_core_stage"
  pending_core_stage=
  pending_core_target=
  pending_core_backup=
  printf 'linked   %s -> %s\n' "$core_install_target" \
    "$core_install_source"
}

run_core_profile() {
  for managed_link in $managed_links; do
    source_name=${managed_link%%:*}
    target_name=${managed_link#*:}
    source_path="$repo_dir/$source_name"
    target_path="$HOME/$target_name"

    validate_core_source "$source_path"

    if [ "$mode" = check ]; then
      if ! prepare_core_target_parent "$target_name" 0; then
        printf 'unmanaged %s\n' "$target_path"
        failed=1
        continue
      fi
    elif ! prepare_core_target_parent "$target_name" 0; then
      :
    fi

    if core_link_matches_source "$target_path" \
      "$core_source_canonical"; then
      printf 'ok       %s\n' "$target_path"
      continue
    fi

    if [ "$mode" = check ]; then
      if [ -e "$target_path" ] || [ -L "$target_path" ]; then
        validate_core_conflict "$target_path"
      fi
      printf 'unmanaged %s\n' "$target_path"
      failed=1
      continue
    fi

    install_core_link "$source_path" "$target_path" "$target_name"
  done
}

validate_relative_path() {
  validate_path_value=$1
  case "$validate_path_value" in
    ""|/*|-*|*//*|*[!A-Za-z0-9._/-]*)
      die "unsafe manifest path: $validate_path_value"
      ;;
  esac
  case "/$validate_path_value/" in
    */./*|*/../*)
      die "dot path components are not allowed: $validate_path_value"
      ;;
  esac
}

assert_source_file() {
  source_root_path=$1
  source_relative_path=$2
  source_expected_mode=$3
  source_parent_relative=${source_relative_path%/*}
  source_component_path=$source_root_path

  assert_owned_directory "$source_root_path"
  if [ "$source_parent_relative" != "$source_relative_path" ]; then
    source_old_ifs=$IFS
    IFS=/
    set -- $source_parent_relative
    IFS=$source_old_ifs
    for source_component in "$@"; do
      source_component_path="$source_component_path/$source_component"
      assert_owned_directory "$source_component_path"
    done
  fi

  source_file_path="$source_root_path/$source_relative_path"
  assert_regular_owned_file "$source_file_path"
  [ "$(manifest_mode_for_file "$source_file_path")" = \
    "$source_expected_mode" ] ||
    die "source mode does not match manifest: $source_file_path"
}

validate_existing_target() {
  target_relative_path=$1
  target_parent_relative=${target_relative_path%/*}
  target_component_path=$ml4w_root
  target_missing_parent=0

  if [ "$target_parent_relative" != "$target_relative_path" ]; then
    target_old_ifs=$IFS
    IFS=/
    set -- $target_parent_relative
    IFS=$target_old_ifs
    for target_component in "$@"; do
      target_component_path="$target_component_path/$target_component"
      if [ "$target_missing_parent" -eq 1 ]; then
        continue
      fi
      if [ -L "$target_component_path" ]; then
        die "target parent is a symlink: $target_component_path"
      fi
      if [ -e "$target_component_path" ]; then
        assert_owned_directory "$target_component_path"
      else
        target_missing_parent=1
      fi
    done
  fi

  target_file_path="$ml4w_root/$target_relative_path"
  [ ! -L "$target_file_path" ] ||
    die "target file is a symlink: $target_file_path"
  if [ -e "$target_file_path" ]; then
    assert_regular_owned_file "$target_file_path"
    normalized_mode_for_file "$target_file_path" >/dev/null
  fi
}

profile_value() {
  awk -F '|' -v wanted_key="$1" '
    $1 == wanted_key {
      if (found) {
        exit 3
      }
      value = substr($0, length($1) + 2)
      if (value == "") {
        exit 4
      }
      print value
      found = 1
    }
    END {
      if (!found) {
        exit 2
      }
    }
  ' "$profile_metadata"
}

gate_ml4w_profile() {
  for required_command in awk cmp grep id jq mktemp readlink stat; do
    require_command "$required_command"
  done

  profile_dir="$repo_dir/profiles/ml4w/legacy-2.9.9.5"
  profile_metadata="$profile_dir/profile.conf"
  manifest_path="$profile_dir/manifest"
  ml4w_root="$HOME/.mydotfiles/com.ml4w.dotfiles"
  active_profile_path="$HOME/.config/ml4w-dotfiles-installer/active.json"
  live_dotinst="$ml4w_root/config.dotinst"
  live_version_name="$ml4w_root/.config/ml4w/version/name"

  assert_owned_directory "$HOME"
  assert_owned_directory "$HOME/.config"
  assert_owned_directory "$HOME/.config/ml4w-dotfiles-installer"
  assert_owned_directory "$HOME/.mydotfiles"
  assert_owned_directory "$ml4w_root"
  assert_owned_directory "$profile_dir"
  assert_owned_directory "$profile_dir/common"
  assert_owned_directory "$profile_dir/hosts"
  assert_owned_directory "$profile_dir/hosts/$host_profile"
  assert_regular_owned_file "$profile_metadata"
  assert_regular_owned_file "$manifest_path"

  awk -F '|' '
    NF != 2 {
      exit 2
    }
    $1 !~ /^(schema|profile_id|version|version_name|source|subfolder)$/ {
      exit 2
    }
    seen[$1]++ {
      exit 2
    }
    END {
      if (NR != 6) {
        exit 2
      }
    }
  ' "$profile_metadata" ||
    die "invalid ML4W profile metadata"

  expected_schema=$(profile_value schema) ||
    die "missing profile schema"
  expected_profile_id=$(profile_value profile_id) ||
    die "missing profile ID"
  expected_version=$(profile_value version) ||
    die "missing profile version"
  expected_version_name=$(profile_value version_name) ||
    die "missing profile version name"
  expected_source=$(profile_value source) ||
    die "missing profile source"
  expected_subfolder=$(profile_value subfolder) ||
    die "missing profile subfolder"

  [ "$expected_schema" = 1 ] ||
    die "unsupported ML4W profile schema: $expected_schema"
  [ "$expected_profile_id" = com.ml4w.dotfiles ] ||
    die "unsupported ML4W profile ID: $expected_profile_id"
  [ "$expected_version" = 2.9.9.5 ] ||
    die "unsupported ML4W version: $expected_version"
  [ "$expected_version_name" = 2.9.9.5 ] ||
    die "unsupported ML4W version name: $expected_version_name"
  [ "$expected_source" = \
    https://github.com/mylinuxforwork/dotfiles.git ] ||
    die "unsupported ML4W source: $expected_source"
  [ "$expected_subfolder" = dotfiles ] ||
    die "unsupported ML4W subfolder: $expected_subfolder"

  assert_regular_owned_file "$active_profile_path"
  active_profile_id=$(jq -er '.active | strings' "$active_profile_path") ||
    die "invalid active ML4W profile metadata"
  [ "$active_profile_id" = "$expected_profile_id" ] ||
    die "ML4W profile is not active: $active_profile_id"

  validate_existing_target config.dotinst
  assert_regular_owned_file "$live_dotinst"
  live_profile_id=$(jq -er '.id | strings' "$live_dotinst") ||
    die "invalid live ML4W profile ID"
  live_profile_version=$(jq -er '.version | strings' "$live_dotinst") ||
    die "invalid live ML4W profile version"
  live_profile_source=$(jq -er '.source | strings' "$live_dotinst") ||
    die "invalid live ML4W profile source"
  live_profile_subfolder=$(jq -er '.subfolder | strings' "$live_dotinst") ||
    die "invalid live ML4W profile subfolder"

  [ "$live_profile_id" = "$expected_profile_id" ] ||
    die "unexpected live ML4W profile ID: $live_profile_id"
  [ "$live_profile_version" = "$expected_version" ] ||
    die "unexpected live ML4W version: $live_profile_version"
  [ "$live_profile_source" = "$expected_source" ] ||
    die "unexpected live ML4W source: $live_profile_source"
  [ "$live_profile_subfolder" = "$expected_subfolder" ] ||
    die "unexpected live ML4W subfolder: $live_profile_subfolder"

  validate_existing_target .config/ml4w/version/name
  assert_regular_owned_file "$live_version_name"
  awk -v expected_name="$expected_version_name" '
    NR != 1 || $0 != expected_name {
      exit 2
    }
    END {
      if (NR != 1) {
        exit 2
      }
    }
  ' "$live_version_name" ||
    die "unexpected live ML4W version name"

  for active_config_dir in hypr kitty ml4w swaync waybar; do
    active_config_path="$HOME/.config/$active_config_dir"
    expected_config_path="$ml4w_root/.config/$active_config_dir"
    assert_owned_directory "$expected_config_path"
    [ -L "$active_config_path" ] ||
      die "ML4W config link is not active: $active_config_path"
    active_config_canonical=$(readlink -f -- "$active_config_path") ||
      die "cannot resolve ML4W config link: $active_config_path"
    expected_config_canonical=$(readlink -f -- \
      "$expected_config_path") ||
      die "cannot resolve expected ML4W config: $expected_config_path"
    [ "$active_config_canonical" = "$expected_config_canonical" ] ||
      die "ML4W config link has an unexpected target: $active_config_path"
  done

  hypr_loader_relative=.config/hypr/hyprland.conf
  kitty_loader_relative=.config/kitty/kitty.conf
  waybar_loader_relative=.config/waybar/launch.sh
  for loader_relative in \
    "$hypr_loader_relative" \
    "$kitty_loader_relative" \
    "$waybar_loader_relative"
  do
    validate_existing_target "$loader_relative"
  done

  grep -Eq \
    '^[[:space:]]*source[[:space:]]*=[[:space:]]*~/\.config/hypr/conf/custom\.conf[[:space:]]*$' \
    "$ml4w_root/$hypr_loader_relative" ||
    die "live Hyprland schema does not load custom.conf"
  grep -Fxq \
    'if [ -f ~/.config/waybar/themes${arrThemes[0]}/config-custom ]; then' \
    "$ml4w_root/$waybar_loader_relative" &&
    grep -Fxq '    config_file="config-custom"' \
      "$ml4w_root/$waybar_loader_relative" ||
    die "live Waybar launcher does not support config-custom"
  grep -Fxq \
    'if [ -f ~/.config/waybar/themes${arrThemes[1]}/style-custom.css ]; then' \
    "$ml4w_root/$waybar_loader_relative" &&
    grep -Fxq '    style_file="style-custom.css"' \
      "$ml4w_root/$waybar_loader_relative" ||
    die "live Waybar launcher does not support style-custom.css"
  grep -Eq \
    '^[[:space:]]*include[[:space:]]+\$HOME/\.config/kitty/custom\.conf[[:space:]]*$' \
    "$ml4w_root/$kitty_loader_relative" ||
    die "live Kitty schema does not load custom.conf"
}

validate_manifest() {
  manifest_work_dir=$(mktemp -d \
    "${TMPDIR:-/tmp}/dotfiles-ml4w-manifest.XXXXXX")
  manifest_entries_file="$manifest_work_dir/entries"
  manifest_seen_file="$manifest_work_dir/seen"
  : >"$manifest_entries_file"
  : >"$manifest_seen_file"
  manifest_common_found=0
  manifest_host_found=0

  while IFS= read -r manifest_line || [ -n "$manifest_line" ]; do
    case "$manifest_line" in
      ""|\#*) continue ;;
    esac
    case "$manifest_line" in
      *"|"*"|"*) ;;
      *) die "malformed manifest entry: $manifest_line" ;;
    esac

    manifest_layer=${manifest_line%%|*}
    manifest_remainder=${manifest_line#*|}
    manifest_mode=${manifest_remainder%%|*}
    manifest_relative_path=${manifest_remainder#*|}
    case "$manifest_relative_path" in
      *"|"*) die "malformed manifest entry: $manifest_line" ;;
    esac

    case "$manifest_layer" in
      common)
        manifest_source_root="$profile_dir/common"
        manifest_common_found=1
        ;;
      "host:$host_profile")
        manifest_source_root="$profile_dir/hosts/$host_profile"
        manifest_host_found=1
        ;;
      *)
        die "unsupported manifest layer: $manifest_layer"
        ;;
    esac
    case "$manifest_mode" in
      0644|0755) ;;
      *) die "unsupported manifest mode: $manifest_mode" ;;
    esac

    validate_relative_path "$manifest_relative_path"
    if grep -Fqx -- "$manifest_relative_path" "$manifest_seen_file"; then
      die "duplicate manifest target: $manifest_relative_path"
    fi
    printf '%s\n' "$manifest_relative_path" >>"$manifest_seen_file"

    assert_source_file "$manifest_source_root" \
      "$manifest_relative_path" "$manifest_mode"
    validate_existing_target "$manifest_relative_path"
    printf '%s|%s|%s\n' "$manifest_mode" "$manifest_relative_path" \
      "$manifest_source_root/$manifest_relative_path" \
      >>"$manifest_entries_file"
  done <"$manifest_path"

  [ "$manifest_common_found" -eq 1 ] ||
    die "manifest has no common layer"
  [ "$manifest_host_found" -eq 1 ] ||
    die "manifest has no selected host layer"
  [ -s "$manifest_entries_file" ] ||
    die "manifest selected no files"
}

ensure_target_parent() {
  parent_relative_path=$1
  parent_relative_path=${parent_relative_path%/*}
  parent_component_path=$ml4w_root

  if [ "$parent_relative_path" = "$1" ]; then
    return
  fi

  parent_old_ifs=$IFS
  IFS=/
  set -- $parent_relative_path
  IFS=$parent_old_ifs
  for parent_component in "$@"; do
    parent_component_path="$parent_component_path/$parent_component"
    if [ -L "$parent_component_path" ]; then
      die "target parent is a symlink: $parent_component_path"
    fi
    if [ -e "$parent_component_path" ]; then
      assert_owned_directory "$parent_component_path"
    else
      mkdir -- "$parent_component_path"
      chmod 755 -- "$parent_component_path"
    fi
  done
}

backup_ml4w_target() {
  backup_target_relative=$1
  backup_target_path="$ml4w_root/$backup_target_relative"
  ensure_backup_dir
  backup_copy_path="$backup_dir/ml4w/$backup_target_relative"
  (umask 077 && mkdir -p -- "$(dirname -- "$backup_copy_path")")
  cp -p -- "$backup_target_path" "$backup_copy_path"
  printf 'backup   %s -> %s\n' "$backup_target_path" "$backup_copy_path"
}

deploy_ml4w_manifest() {
  while IFS='|' read -r deploy_mode deploy_relative deploy_source; do
    deploy_target="$ml4w_root/$deploy_relative"
    validate_existing_target "$deploy_relative"

    if [ -f "$deploy_target" ] &&
       cmp -s -- "$deploy_source" "$deploy_target" &&
       [ "$(manifest_mode_for_file "$deploy_target")" = \
         "$deploy_mode" ]; then
      printf 'ok       %s\n' "$deploy_target"
      continue
    fi

    if [ -e "$deploy_target" ]; then
      backup_ml4w_target "$deploy_relative"
    fi

    ensure_target_parent "$deploy_relative"
    deploy_parent=$(dirname -- "$deploy_target")
    pending_temp=$(mktemp "$deploy_parent/.dotfiles-install.XXXXXX")
    cp -- "$deploy_source" "$pending_temp"
    chmod "$deploy_mode" -- "$pending_temp"
    mv -f -- "$pending_temp" "$deploy_target"
    pending_temp=
    printf 'installed %s\n' "$deploy_target"
  done <"$manifest_entries_file"
}

check_ml4w_manifest() {
  while IFS='|' read -r check_mode check_relative check_source; do
    check_target="$ml4w_root/$check_relative"
    if [ ! -e "$check_target" ]; then
      printf 'missing  %s\n' "$check_target"
      failed=1
      continue
    fi
    validate_existing_target "$check_relative"
    if cmp -s -- "$check_source" "$check_target" &&
       [ "$(manifest_mode_for_file "$check_target")" = \
         "$check_mode" ]; then
      printf 'ok       %s\n' "$check_target"
    else
      printf 'drift    %s\n' "$check_target"
      failed=1
    fi
  done <"$manifest_entries_file"
}

for core_command in id mktemp readlink stat; do
  require_command "$core_command"
done

if [ "$mode" != check ]; then
  acquire_install_lock
  preflight_core_profile
fi

if [ "$profile" = ml4w ]; then
  gate_ml4w_profile
  validate_manifest
  if [ "$mode" = check ]; then
    check_ml4w_manifest
  else
    deploy_ml4w_manifest
  fi
fi

# The portable core is always applied last so vendor installers cannot reclaim
# the clean repository-managed shell configuration.
run_core_profile

if [ "$mode" = check ]; then
  exit "$failed"
fi

printf '\nRun `exec zsh` for the new shell configuration.\n'

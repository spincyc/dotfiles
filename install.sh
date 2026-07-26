#!/bin/sh
set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/dotfiles"
backup_dir="$state_dir/backups/$(date +%Y%m%d-%H%M%S)"
mode=install

usage() {
  cat <<'EOF'
Usage: ./install.sh [--check | --update]

  no option  Back up conflicting files and link the managed dotfiles
  --check    Report whether every managed file is correctly linked
  --update   Fast-forward the repository, then install
EOF
}

if [ "$#" -gt 1 ]; then
  usage >&2
  exit 2
fi

case "${1:-}" in
  "") ;;
  --check) mode=check ;;
  --update) mode=update ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac

if [ "$mode" = update ]; then
  git -C "$repo_dir" pull --ff-only
fi

managed_files=".zshrc .tmux.conf"
failed=0

for name in $managed_files; do
  source_path="$repo_dir/$name"
  target_path="$HOME/$name"

  if [ "$mode" = check ]; then
    if [ -L "$target_path" ] &&
       [ "$(readlink -f -- "$target_path")" = "$(readlink -f -- "$source_path")" ]; then
      printf 'ok       %s\n' "$target_path"
    else
      printf 'unmanaged %s\n' "$target_path"
      failed=1
    fi
    continue
  fi

  if [ -L "$target_path" ] &&
     [ "$(readlink -f -- "$target_path")" = "$(readlink -f -- "$source_path")" ]; then
    printf 'ok       %s\n' "$target_path"
    continue
  fi

  if [ -e "$target_path" ] || [ -L "$target_path" ]; then
    mkdir -p -- "$backup_dir"
    mv -- "$target_path" "$backup_dir/$name"
    printf 'backup   %s -> %s\n' "$target_path" "$backup_dir/$name"
  fi

  ln -s -- "$source_path" "$target_path"
  printf 'linked   %s -> %s\n' "$target_path" "$source_path"
done

if [ "$mode" = check ]; then
  exit "$failed"
fi

printf '\nRun `exec zsh` for the new shell configuration.\n'

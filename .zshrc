# Portable interactive Zsh configuration.
# Put secrets and machine-specific settings in ~/.zshrc.local (not tracked).

export EDITOR="${EDITOR:-vim}"
export VISUAL="${VISUAL:-$EDITOR}"

HISTFILE="${ZDOTDIR:-$HOME}/.zsh_history"
HISTSIZE=50000
SAVEHIST=50000

setopt AUTO_CD
setopt EXTENDED_HISTORY
setopt HIST_EXPIRE_DUPS_FIRST
setopt HIST_IGNORE_ALL_DUPS
setopt HIST_IGNORE_SPACE
setopt HIST_REDUCE_BLANKS
setopt INC_APPEND_HISTORY
setopt INTERACTIVE_COMMENTS
setopt PROMPT_SUBST

bindkey -e

# Change directory into a wt workspace. wt cannot move the calling shell
# itself, so this is the shim its usage text points at: with a name it goes
# to that workspace, with none it climbs to the top of the one you are in.
# Deliberately named wtcd rather than shadowing wt with a function, which
# would break `command -v wt`, non-interactive callers, and the workspace
# guidance that tells agents to invoke wt directly.
wtcd() {
  local target
  if (( $# )); then
    target=$(command wt path "$@") || return
  else
    target=$(command wt pwd) || return
  fi
  cd -- "$target"
}

# Completions live beside the tool in this checkout, resolved through the
# symlink the same way .zshenv finds bin/, so they need no reinstall. They
# are Zsh-only by nature, which is why there is no managed_links entry.
dotfiles_root=${${(%):-%N}:A:h}
[[ -d $dotfiles_root/zsh ]] && fpath=($dotfiles_root/zsh $fpath)
unset dotfiles_root

# Use Oh My Zsh when installed, while remaining usable without it.
export ZSH="${ZSH:-$HOME/.oh-my-zsh}"
if [[ -r "$ZSH/oh-my-zsh.sh" ]]; then
  ZSH_THEME=""
  plugins=(git sudo colored-man-pages extract)
  source "$ZSH/oh-my-zsh.sh"

  ZSH_THEME_GIT_PROMPT_PREFIX="%F{yellow}git:(%f"
  ZSH_THEME_GIT_PROMPT_SUFFIX="%F{yellow})%f "
  ZSH_THEME_GIT_PROMPT_DIRTY="%F{red}*%f"
  ZSH_THEME_GIT_PROMPT_CLEAN=""
  PROMPT='%F{cyan}%m:%~%f $(git_prompt_info)%# '
else
  autoload -Uz compinit vcs_info
  zsh_cache_dir="${XDG_CACHE_HOME:-$HOME/.cache}/zsh"
  mkdir -p "$zsh_cache_dir"
  compinit -d "$zsh_cache_dir/zcompdump"
  zstyle ':vcs_info:git:*' formats ' %F{yellow}git:(%b)%f'
  precmd() { vcs_info }
  PROMPT='%F{cyan}%m:%~%f${vcs_info_msg_0_} %# '
fi

[[ -r "$HOME/.zshrc.local" ]] && source "$HOME/.zshrc.local"

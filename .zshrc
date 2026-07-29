# Portable interactive Zsh configuration.
# Put secrets and machine-specific settings in ~/.zshrc.local (not tracked).

export EDITOR="${EDITOR:-vim}"
export VISUAL="${VISUAL:-$EDITOR}"

typeset -U path PATH
path=("$HOME/.local/bin" $path)

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
  PROMPT='%F{cyan}%~%f $(git_prompt_info)%# '
else
  autoload -Uz compinit vcs_info
  zsh_cache_dir="${XDG_CACHE_HOME:-$HOME/.cache}/zsh"
  mkdir -p "$zsh_cache_dir"
  compinit -d "$zsh_cache_dir/zcompdump"
  zstyle ':vcs_info:git:*' formats ' %F{yellow}git:(%b)%f'
  precmd() { vcs_info }
  PROMPT='%F{cyan}%~%f${vcs_info_msg_0_} %# '
fi

[[ -r "$HOME/.zshrc.local" ]] && source "$HOME/.zshrc.local"

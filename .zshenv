# Environment for every Zsh invocation, interactive or not.
# Keep interactive-only configuration in .zshrc.

typeset -U path PATH
path=("$HOME/.local/bin" $path)

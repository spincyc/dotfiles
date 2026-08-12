# Environment for every Zsh invocation, interactive or not.
# Keep interactive-only configuration in .zshrc.

typeset -U path PATH
path=("$HOME/.local/bin" $path)

# Append this repository's own bin directory so a tool added under bin/ is on
# PATH in the next shell, with no reinstall and no managed_links entry. The
# path is resolved from this file through its symlink, so the checkout can
# live anywhere; installed links keep bin/ tools working outside Zsh too.
# Appended, not prepended: nothing here should shadow a system command.
dotfiles_root=${${(%):-%N}:A:h}
[[ -d $dotfiles_root/bin ]] && path=($path $dotfiles_root/bin)
unset dotfiles_root

# Keep repository-managed Python packages, such as wt, importable from any
# script. Empty entries are dropped so the current directory never joins
# sys.path by accident.
typeset -T PYTHONPATH pythonpath :
typeset -U pythonpath PYTHONPATH
pythonpath=("$HOME/.local/lib/python" ${pythonpath:#})
export PYTHONPATH

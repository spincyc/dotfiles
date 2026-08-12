# Environment for every Zsh invocation, interactive or not.
# Keep interactive-only configuration in .zshrc.

typeset -U path PATH
path=("$HOME/.local/bin" $path)

# Keep repository-managed Python packages, such as wt, importable from any
# script. Empty entries are dropped so the current directory never joins
# sys.path by accident.
typeset -T PYTHONPATH pythonpath :
typeset -U pythonpath PYTHONPATH
pythonpath=("$HOME/.local/lib/python" ${pythonpath:#})
export PYTHONPATH

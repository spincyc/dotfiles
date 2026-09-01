"""The agent relay protocol, made mechanical.

`relay/PROTOCOL.md` describes an exchange between a planning agent and an
executing agent that meet only through git. Its preflight, its final sync,
and its turn-file format are all precise, and all of them are prose an
executing agent would otherwise have to reimplement from memory, one git
incantation at a time, every turn. This package runs them instead, so a
failure arrives as an exit code and a token rather than as an improvisation.

``PROTOCOL_VERSION`` is the version this build implements, and the only
place it is written down. The document is immutable per version; this code
is not, so ``--protocol`` compares the two and refuses to run on a
mismatch rather than warning about it.

The modules are meant to be reused on their own:

``relay.errors``    the user-facing error types, including the blocked
                    channel and its tokens
``relay.gitcmd``    a thin ``git`` runner under a pinned environment
``relay.identity``  remote-URL normalisation and repository identity
``relay.turnfile``  turn-file front matter: parse, render, and the lint
                    rules
``relay.steps``     preflight, initialization, sync, claim, prepare, and
                    publish, as functions that return what happened
``relay.cli``       the ``relay`` command line
"""

PROTOCOL_VERSION = "relay-v5"

__all__ = [
    "PROTOCOL_VERSION",
    "cli",
    "errors",
    "gitcmd",
    "identity",
    "steps",
    "turnfile",
]

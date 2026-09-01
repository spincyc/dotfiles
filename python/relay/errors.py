"""User-facing failures.

Every module raises these instead of exiting, so the pieces stay usable
from scripts that want to handle the failure themselves. ``exit_code``
carries the protocol's meaning rather than a generic one: 2 for a usage
error, 3 for the blocked channel, 5 for lint findings.
"""

# The blocked-channel tokens, in the protocol's own order. A token is the
# only content the user is permitted to carry back from a failed run, so
# the set is closed and spelled once.
RELAYED_TOKENS = (
    "preflight-failed",
    "brief-unreadable",
    "brief-mutated",
    "claim-replay",
    "sync-conflict",
    "push-rejected",
    "no-credentials",
    "hooks-rejected",
)

# Stops this tool distinguishes that the protocol's blocked channel does
# not name. They are recoverable inside the session -- rewrite the shas and
# publish again, install the matching build -- so relaying one would hand
# the planner a token its table cannot explain.
INTERNAL_TOKENS = (
    "stale-shas",
    "protocol-mismatch",
)

BLOCKED_TOKENS = RELAYED_TOKENS + INTERNAL_TOKENS


class RelayError(Exception):
    """A failure worth reporting to the user verbatim."""

    exit_code = 1

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UsageError(RelayError):
    """The command line was wrong; the caller should also print usage."""

    exit_code = 2


class Blocked(RelayError):
    """A stop the protocol names, carrying the token to relay.

    The token is the payload, not decoration on the message: the user
    relays one line and nothing else, so a caller must be able to reach
    the token without parsing English out of the detail.
    """

    exit_code = 3

    def __init__(self, token: str, message: str) -> None:
        if token not in BLOCKED_TOKENS:
            raise ValueError(f"not a blocked-channel token: {token}")
        super().__init__(message)
        self.token = token

    @property
    def relayed(self) -> bool:
        """True when the user may carry this token back to the planner."""
        return self.token in RELAYED_TOKENS

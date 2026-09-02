"""User-facing failures.

Every module raises these instead of exiting, so the pieces stay usable from
scripts that want to handle the failure themselves.
"""


class WtError(Exception):
    """A failure worth reporting to the user verbatim."""

    exit_code = 1

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UsageError(WtError):
    """The command line was wrong; the caller should also print usage."""

    exit_code = 2


class RelayBlocked(WtError):
    """A relay turn stopped at a condition the protocol names.

    The token is the payload rather than decoration on the message: the
    user relays one line and nothing else, so the line has to be reachable
    without parsing English out of the detail. A token the protocol's
    blocked channel does not name is `relayed=False`, and is a stop to
    report here rather than to carry back.
    """

    exit_code = 3

    def __init__(
        self,
        run: str,
        turn: str,
        token: str,
        detail: str,
        relayed: bool = True,
    ) -> None:
        super().__init__(detail)
        self.run = run
        self.turn = turn
        self.token = token
        self.relayed = relayed

    @property
    def line(self) -> str:
        """The one line the user may carry back to the planner."""
        return f"relay blocked {self.run} {self.turn} {self.token}"


class PartlyRemoved(WtError):
    """Deletion began and could not finish, so the tree is now neither."""

    def __init__(self, workspace: str, remaining: list[str]) -> None:
        super().__init__(
            f"partly removed {workspace}: {len(remaining)} paths could not "
            f"be deleted, starting at {remaining[0]}; what remains is an "
            f"incomplete tree, not the workspace you had"
        )
        self.workspace = workspace
        self.remaining = remaining


class RemovalRefused(WtError):
    """The gate refused to delete a workspace, and said why.

    Distinct from a plain failure so a sweep can report "kept, because ..."
    rather than treating a deliberate refusal as something that went wrong.
    """

    def __init__(self, workspace: str, reasons: list[str]) -> None:
        super().__init__(f"refusing to remove {workspace}: {reasons[0]}")
        self.workspace = workspace
        self.reasons = reasons


class UnsavedWorkError(RemovalRefused):
    """A workspace was asked to go away while a clone still held work."""

    def __init__(
        self,
        workspace: str,
        repositories: list[str],
        reasons: list[str] | None = None,
    ) -> None:
        super().__init__(workspace, reasons or [f"unsaved: {repositories}"])
        # No remedy in the message: what to type to override this is the
        # command line's business, and a library that prescribes an
        # incantation cannot be reused by anything that spells it
        # differently.
        self.message = f"{workspace} holds unsaved work"
        self.repositories = repositories

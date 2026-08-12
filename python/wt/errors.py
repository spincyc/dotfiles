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

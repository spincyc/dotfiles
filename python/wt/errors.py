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


class UnsavedWorkError(WtError):
    """A workspace was asked to go away while a clone still held work."""

    def __init__(self, workspace: str, repositories: list[str]) -> None:
        super().__init__(
            f"{workspace} holds unsaved work; use wt rm --force to discard it"
        )
        self.workspace = workspace
        self.repositories = repositories

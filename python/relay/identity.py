"""Repository identity, independent of how a remote is spelled.

The handoff line names a repository; the checkout names a remote URL. The
same repository is written at least four ways -- `https://host/o/n`,
`ssh://git@host/o/n`, `git@host:o/n.git`, and the bare `o/n` shorthand --
so comparing the two literally would report a mismatch on repositories
that are in fact the same one. Both sides are reduced to `host/path`
first, and only then compared.
"""

import re

_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*://")
_SHORTHAND = re.compile(r"^[^/:@\s]+/[^/:@\s]+$")


def is_shorthand(spec: str) -> bool:
    """True for a bare `owner/name`, which names no host at all."""
    return bool(_SHORTHAND.match(spec.strip()))


def _trim(text: str) -> str:
    """Drop a trailing `.git` and any trailing slash, in either order."""
    text = text.rstrip("/")
    if text.endswith(".git"):
        text = text[: -len(".git")]
    return text.rstrip("/")


def normalize_remote(url: str) -> str:
    """Reduce a remote URL to a comparable `host/owner/name`.

    Lowercases the host and nothing else: hosts are case-insensitive and
    paths are not, so folding the path would make two different
    repositories on a case-sensitive host compare equal.
    """
    text = _SCHEME.sub("", url.strip())
    # Split the authority off first. A `@` or a `:` later in the path is
    # part of the path, and treating one as a delimiter would eat the
    # host along with it.
    authority, slash, path = text.partition("/")
    if "@" in authority:
        authority = authority.rsplit("@", 1)[1]
    host, colon, after = authority.partition(":")
    if colon:
        if after.isdigit():
            # An explicit port names no path; drop it rather than turning
            # `host:22/owner/name` into a segment called `22`.
            authority = host
        elif after:
            # scp-style `host:owner/name`.
            authority = f"{host}/{after}"
        else:
            authority = host
    segments = [part for part in (authority + slash + path).split("/") if part]
    if segments:
        segments[0] = segments[0].lower()
    return _trim("/".join(segments))


def normalize_spec(spec: str) -> str:
    """Reduce the repository a handoff line names.

    A bare `owner/name` names no host, so running it through
    `normalize_remote` would lowercase an owner in the belief that it was
    a host, and an owner spelled with capitals would then never match.
    """
    if is_shorthand(spec):
        return _trim(spec.strip())
    return normalize_remote(spec)


def same_repository(remote_url: str, spec: str) -> bool:
    """True when the checkout's origin is the repository spec names."""
    remote = normalize_remote(remote_url)
    wanted = normalize_spec(spec)
    if remote == wanted:
        return True
    if is_shorthand(spec):
        # The shorthand names the last two segments and says nothing
        # about the host, so it matches any host carrying that path.
        return remote.split("/")[-2:] == wanted.split("/")
    return False

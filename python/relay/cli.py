"""The `relay` command line.

Argument parsing, every line of output, and every exit code live here; the
other modules stay importable without printing anything.

The exit codes are uniform across subcommands, because a caller reading
them is usually a script or an agent rather than a person: 0 success, 2 a
usage error, 3 a blocked-channel stop, 5 lint findings, 1 anything else.
"""

import argparse
import os
import sys
from pathlib import Path

from . import PROTOCOL_VERSION, gitcmd, steps, turnfile
from .errors import Blocked, RelayError, UsageError

DESCRIPTION = """\
Run the mechanical steps of the agent relay protocol (relay/PROTOCOL.md),
so an executing agent gets exit codes instead of improvised git.

Exit codes: 0 success, 2 usage, 3 blocked (one `blocked: <token>` line on
stdout), 5 lint findings, 1 any other failure.
"""

EPILOG = """\
--protocol pins the run's protocol version. This build implements
%s, and refuses to run against any other: the document is
immutable per version, this command is not, and a version skew must stop
a run rather than warn it.
""" % PROTOCOL_VERSION


def _repository(directory: str) -> Path:
    start = Path(directory).expanduser()
    if not start.is_dir():
        raise UsageError(f"not a directory: {directory}")
    top = gitcmd.toplevel(start)
    if top is None:
        raise UsageError(f"not inside a git repository: {start}")
    return top


def _relative(repo: Path, given: str) -> str:
    """A repository-relative spelling of a path the user named."""
    path = Path(given).expanduser()
    if not path.is_absolute():
        path = Path(os.getcwd()) / path
    try:
        return str(path.resolve().relative_to(repo.resolve()))
    except ValueError:
        raise UsageError(
            f"{given} is outside {repo}; every path a turn file names is "
            f"repository-relative"
        ) from None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="relay",
        description=DESCRIPTION,
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=PROTOCOL_VERSION,
        help="print the protocol version this build implements",
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--protocol",
        metavar="VERSION",
        help=f"the run's protocol version; must be {PROTOCOL_VERSION}",
    )
    inside = argparse.ArgumentParser(add_help=False)
    inside.add_argument(
        "-C",
        "--directory",
        default=".",
        metavar="PATH",
        help="run inside this checkout instead of the current directory",
    )
    commands = parser.add_subparsers(dest="command", metavar="<subcommand>")
    commands.required = True

    preflight = commands.add_parser(
        "preflight",
        parents=[common, inside],
        help="run the per-turn preflight, stopping at the first failure",
    )
    preflight.add_argument("--repo", required=True)
    preflight.add_argument("--branch", required=True)
    preflight.add_argument("--brief", required=True, metavar="SHA")

    initialize = commands.add_parser(
        "init",
        parents=[common, inside],
        help="the one branch change the protocol permits, before a claim",
    )
    initialize.add_argument("--repo", required=True)
    initialize.add_argument("--branch", required=True)

    sync = commands.add_parser(
        "sync",
        parents=[common, inside],
        help="the final sync: reconcile with origin without a rewrite",
    )
    sync.add_argument("--branch", required=True)
    sync.add_argument(
        "--dry-run",
        action="store_true",
        help="report the path it would take and change nothing",
    )

    claim = commands.add_parser(
        "claim",
        parents=[common, inside],
        help="publish <nnn>-claim.md to take the turn number",
    )
    claim.add_argument("--run", required=True)
    claim.add_argument("--turn", required=True, metavar="NNN")
    claim.add_argument("--branch", required=True)
    claim.add_argument("--agent", required=True, metavar="NAME")

    prepare = commands.add_parser(
        "prepare",
        parents=[common, inside],
        help="sync, re-verify the brief, and print the shas to record",
    )
    prepare.add_argument("--branch", required=True)
    prepare.add_argument("--brief", required=True, metavar="SHA")
    prepare.add_argument("--brief-path", required=True, metavar="PATH")

    publish = commands.add_parser(
        "publish",
        parents=[common, inside],
        help="commit and push the result, refusing one whose shas lie",
    )
    publish.add_argument("--branch", required=True)
    publish.add_argument("--result", required=True, metavar="PATH")

    lint = commands.add_parser(
        "lint",
        parents=[common],
        help="statically validate turn files; no git, no network",
    )
    lint.add_argument("files", nargs="+", metavar="FILE")
    return parser


def _check_protocol(given: str | None) -> None:
    if given is None or given == PROTOCOL_VERSION:
        return
    raise Blocked(
        "protocol-mismatch",
        f"the run asks for {given} and this build implements "
        f"{PROTOCOL_VERSION}. Two parties on different rule sets must not "
        f"proceed: install the build that implements {given}, or restart "
        f"the run on {PROTOCOL_VERSION}",
    )


def cmd_preflight(arguments: argparse.Namespace) -> int:
    repo = _repository(arguments.directory)
    for done in steps.preflight(
        repo, arguments.repo, arguments.branch, arguments.brief
    ):
        print(f"ok: {done}")
    return 0


def cmd_init(arguments: argparse.Namespace) -> int:
    repo = _repository(arguments.directory)
    for done in steps.initialize(repo, arguments.repo, arguments.branch):
        print(f"ok: {done}")
    return 0


def cmd_sync(arguments: argparse.Namespace) -> int:
    repo = _repository(arguments.directory)
    result = steps.sync(repo, arguments.branch, arguments.dry_run)
    print(f"would: {result.message}" if result.dry_run else result.message)
    return 0


def cmd_claim(arguments: argparse.Namespace) -> int:
    repo = _repository(arguments.directory)
    result = steps.claim(
        repo,
        arguments.run,
        arguments.turn,
        arguments.branch,
        arguments.agent,
    )
    print(f"claimed: {result.path}")
    print(f"base={result.base}")
    if result.retried:
        print("note: origin had moved; the claim push was retried once")
    return 0


def cmd_prepare(arguments: argparse.Namespace) -> int:
    repo = _repository(arguments.directory)
    result = steps.prepare(
        repo, arguments.branch, arguments.brief, arguments.brief_path
    )
    print(result.sync.message)
    print(f"base={result.head}")
    print(f"work={result.branch}@{result.head}")
    return 0


def cmd_publish(arguments: argparse.Namespace) -> int:
    repo = _repository(arguments.directory)
    relative = _relative(repo, arguments.result)
    result = steps.publish(repo, arguments.branch, relative)
    print(f"published: {result.path}")
    print(f"work={arguments.branch}@{result.head}")
    if result.retried:
        print("note: origin had moved; the push was retried once")
    return 0


def cmd_lint(arguments: argparse.Namespace) -> int:
    findings = 0
    for name in arguments.files:
        reported = turnfile.lint_file(name)
        for finding in reported:
            print(finding)
        findings += len(reported)
        if not reported:
            print(f"ok: {name}")
    return 5 if findings else 0


COMMANDS = {
    "preflight": cmd_preflight,
    "init": cmd_init,
    "sync": cmd_sync,
    "claim": cmd_claim,
    "prepare": cmd_prepare,
    "publish": cmd_publish,
    "lint": cmd_lint,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(
        sys.argv[1:] if argv is None else list(argv)
    )
    try:
        if arguments.command != "lint" and not gitcmd.available():
            raise RelayError("git is not installed")
        _check_protocol(arguments.protocol)
        code = COMMANDS[arguments.command](arguments)
        # Flush inside the guard: a short answer stays in the buffer until
        # the interpreter exits, and a reader that has already gone away
        # would otherwise surface as an unhandled BrokenPipeError during
        # that final flush.
        sys.stdout.flush()
        return code
    except Blocked as error:
        # Exactly one line on stdout, because that line is the whole of
        # what the user is permitted to carry back. A stop the protocol
        # does not name is spelled differently on purpose, so it is never
        # relayed as a blocked-channel token.
        label = "blocked" if error.relayed else "stopped"
        print(f"{label}: {error.token}")
        sys.stdout.flush()
        print(f"relay: {error.message}", file=sys.stderr)
        return error.exit_code
    except UsageError as error:
        print(f"relay: {error.message}", file=sys.stderr)
        parser.print_usage(sys.stderr)
        return error.exit_code
    except RelayError as error:
        print(f"relay: {error.message}", file=sys.stderr)
        return error.exit_code
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 141
    except OSError as error:
        print(f"relay: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130

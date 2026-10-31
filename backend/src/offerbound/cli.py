"""`offerbound` command. Subcommands (start, update, doctor, run) arrive in later chunks."""

import argparse

from offerbound import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="offerbound", description="Offerbound AI job search copilot"
    )
    parser.add_argument("--version", action="version", version=f"offerbound {__version__}")
    parser.parse_args(argv)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Command-line interface for BrainSTEM API tools.

Usage examples
--------------
  brainstem login
  brainstem login --headless
  brainstem login --url http://127.0.0.1:8000/
  brainstem logout
  brainstem load session
  brainstem load session --portal public --filters name.icontains=rat --sort -name
  brainstem load session --id <uuid>
  brainstem load session --limit 20 --offset 40
  brainstem load session --per-page 20 --page 3
  brainstem load session --all
  brainstem save session --data '{"name":"New","projects":["<uuid>"]}'
  brainstem save session --id <uuid> --data '{"description":"updated"}'
  brainstem delete session --id <uuid>
"""

import argparse
import json
import os
import sys

import requests

from .brainstem_api_client import (
    AuthenticationError, BrainstemClient, _MODEL_TO_APP, _TOKEN_FILE,
)


def _common_flags(suppress_defaults: bool = False) -> argparse.ArgumentParser:
    """Shared flags available before and after the subcommand.

    The subcommand copies use ``argparse.SUPPRESS`` defaults so they do not
    overwrite a flag given before the subcommand (``brainstem --url X load``).
    """
    def default(value):
        return argparse.SUPPRESS if suppress_defaults else value

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--token",
        default=default(os.environ.get("BRAINSTEM_API_TOKEN")),
        help="API token. Defaults to $BRAINSTEM_API_TOKEN or the cached token.",
    )
    common.add_argument(
        "--headless",
        action="store_true",
        default=default(False),
        help="Print verification URL + code instead of opening a browser.",
    )
    common.add_argument(
        "--url",
        default=default(os.environ.get("BRAINSTEM_API_URL")),
        help="Base URL of the BrainSTEM server. Defaults to $BRAINSTEM_API_URL "
             "or https://www.brainstem.org/.",
    )
    return common


def _build_parser() -> argparse.ArgumentParser:
    common = _common_flags(suppress_defaults=True)

    parser = argparse.ArgumentParser(
        prog="brainstem",
        description="BrainSTEM command-line API client.",
        parents=[_common_flags()],
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # ---- login ------------------------------------------------------
    sub.add_parser(
        "login",
        parents=[common],
        help="Authenticate and cache your API token.",
    )

    # ---- logout -----------------------------------------------------
    sub.add_parser(
        "logout",
        parents=[common],
        help="Remove the cached API token.",
    )

    # ---- load -------------------------------------------------------
    p_load = sub.add_parser("load", parents=[common], help="Load records from BrainSTEM.")
    p_load.add_argument("model", choices=sorted(_MODEL_TO_APP), help="Model name.")
    p_load.add_argument("--portal", default="private", help="'private' or 'public'.")
    p_load.add_argument("--id", help="UUID of a specific record.")
    p_load.add_argument(
        "--filters",
        nargs="+",
        metavar="FIELD=VALUE",
        help="Filter expressions, e.g. name.icontains=rat",
    )
    p_load.add_argument(
        "--sort",
        nargs="+",
        metavar="FIELD",
        help="Sort fields. Prefix with '-' for descending.",
    )
    p_load.add_argument(
        "--include",
        nargs="+",
        metavar="RELATION",
        help="Related models to embed.",
    )
    p_load.add_argument("--limit", type=int,
                        help="Records per page (sent as per_page; default 100).")
    p_load.add_argument("--offset", type=int,
                        help="Records to skip; must be a multiple of the page size.")
    p_load.add_argument("--per-page", type=int, help="Records per page (default 100).")
    p_load.add_argument("--page", type=int, help="Page number, starting at 1.")
    p_load.add_argument(
        "--all",
        action="store_true",
        help="Follow pagination and print all records merged into one JSON object.",
    )

    # ---- save -------------------------------------------------------
    p_save = sub.add_parser("save", parents=[common], help="Create or update a record.")
    p_save.add_argument("model", choices=sorted(_MODEL_TO_APP), help="Model name.")
    p_save.add_argument("--portal", default="private")
    p_save.add_argument("--id", help="UUID of the record to update (omit to create).")
    p_save.add_argument(
        "--data",
        required=True,
        help="JSON string of fields to submit, e.g. '{\"name\":\"x\"}'.",
    )

    # ---- delete -----------------------------------------------------
    p_delete = sub.add_parser("delete", parents=[common], help="Delete a record by ID.")
    p_delete.add_argument("model", choices=sorted(_MODEL_TO_APP), help="Model name.")
    p_delete.add_argument("--portal", default="private")
    p_delete.add_argument("--id", required=True, help="UUID of the record to delete.")

    return parser


def main():
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "logout":
        if _TOKEN_FILE.exists():
            _TOKEN_FILE.unlink()
            print(f"Logged out. Token removed from {_TOKEN_FILE}")
        else:
            print("No cached token found.")
        return

    client = BrainstemClient(
        token=args.token,
        headless=getattr(args, "headless", False),
        url=getattr(args, "url", None),
    )

    if args.command == "login":
        if args.token:
            print("Logged in with the token from --token / $BRAINSTEM_API_TOKEN "
                  "(not cached).")
        else:
            print(f"Logged in. Token cached at {_TOKEN_FILE}")
        return

    if args.command == "load":
        filters = {}
        for expr in (args.filters or []):
            if "=" not in expr:
                parser.error(f"Invalid filter '{expr}': expected FIELD=VALUE")
            k, v = expr.split("=", 1)
            filters[k] = v

        limit, offset = args.limit, args.offset
        if args.per_page is not None or args.page is not None:
            if limit is not None or offset is not None:
                parser.error("Use either --per-page/--page or --limit/--offset, not both.")
            if (args.per_page is not None and args.per_page < 1) or \
                    (args.page is not None and args.page < 1):
                parser.error("--per-page and --page must be at least 1.")
            limit = args.per_page
            if args.page is not None:
                offset = (args.page - 1) * (args.per_page or 100)

        load_kwargs = dict(
            portal=args.portal,
            id=args.id,
            filters=filters or None,
            sort=args.sort,
            include=args.include,
            limit=limit,
            offset=offset,
        )
        if args.all:
            try:
                result = client.load(args.model, load_all=True, **load_kwargs)
            except (ValueError, AuthenticationError, requests.HTTPError) as exc:
                print(f"Error: {exc}", file=sys.stderr)
                sys.exit(1)
            print(json.dumps(result, indent=2))
            return

        try:
            resp = client.load(args.model, **load_kwargs)
        except ValueError as exc:
            parser.error(str(exc))

    elif args.command == "save":
        try:
            data = json.loads(args.data)
        except json.JSONDecodeError as exc:
            parser.error(f"Invalid JSON for --data: {exc}")

        resp = client.save(args.model, portal=args.portal, id=args.id, data=data)

    elif args.command == "delete":
        resp = client.delete(args.model, portal=args.portal, id=args.id)

    # Output
    if resp.status_code == 204:
        print("Deleted successfully.")
    else:
        try:
            print(json.dumps(resp.json(), indent=2))
        except Exception:
            print(resp.text)

    if not resp.ok:
        sys.exit(1)


if __name__ == "__main__":
    main()

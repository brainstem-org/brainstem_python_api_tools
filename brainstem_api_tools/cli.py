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
  brainstem save session --data '{"name":"New","projects":["<uuid>"]}'
  brainstem save session --id <uuid> --data '{"description":"updated"}'
  brainstem delete session --id <uuid>
"""

import argparse
import json
import os
import sys

from .brainstem_api_client import BrainstemClient, _MODEL_TO_APP, _TOKEN_FILE


def _build_parser() -> argparse.ArgumentParser:
    # Shared flags available on every subcommand
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--token",
        default=os.environ.get("BRAINSTEM_API_TOKEN"),
        help="API token. Defaults to $BRAINSTEM_API_TOKEN or the cached token.",
    )
    common.add_argument(
        "--headless",
        action="store_true",
        help="Print verification URL + code instead of opening a browser.",
    )
    common.add_argument(
        "--url",
        default=None,
        help="Base URL of the BrainSTEM server (default: https://www.brainstem.org/).",
    )

    parser = argparse.ArgumentParser(
        prog="brainstem",
        description="BrainSTEM command-line API client.",
        parents=[common],
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
    p_load.add_argument("--limit", type=int, help="Max records (API max: 100).")
    p_load.add_argument("--offset", type=int, help="Records to skip (pagination).")

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
        print(f"Token: {client._token}")
        print(f"Cached at: {_TOKEN_FILE}")
        return

    if args.command == "load":
        filters = {}
        for expr in (args.filters or []):
            if "=" not in expr:
                parser.error(f"Invalid filter '{expr}': expected FIELD=VALUE")
            k, v = expr.split("=", 1)
            filters[k] = v

        resp = client.load(
            args.model,
            portal=args.portal,
            id=args.id,
            filters=filters or None,
            sort=args.sort,
            include=args.include,
            limit=args.limit,
            offset=args.offset,
        )

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

from __future__ import annotations

import argparse
from pathlib import Path

from .paths import get_paths
from .core import run_once
from .gate import reset_gate
from .audit import summarize_interrupts
from .ingest_cli import ingest
from .notify import send_push
from .fetch import fetch_rss_to_inbox


def main() -> None:
    p = argparse.ArgumentParser(prog="signalgate", add_help=True)
    p.add_argument("--root", default=None, help="Project root path (or env SIGNALGATE_HOME).")

    sub = p.add_subparsers(dest="cmd", required=True)

    fx = sub.add_parser("fetch", help="Fetch RSS/Atom into data/inbox (silent by default).")
    fx.add_argument("--url", required=True, help="RSS/Atom feed URL.")
    fx.add_argument("--limit", type=int, default=20, help="Max items to write (default 20).")
    fx.add_argument("--print-count", action="store_true", help="Print fetched count (opt-in).")

    ig = sub.add_parser("ingest", help="Ingress layer: write events into cold store (silent by default).")
    ig.add_argument("--input", required=True, help="Path to an event.json file OR a directory of event jsons.")
    ig.add_argument("--glob", default="*.json", help="When --input is a directory, glob pattern to match files.")
    ig.add_argument("--print-count", action="store_true", help="Print ingested count (opt-in).")

    r = sub.add_parser("run", help="Decision core: run once with an input event JSON file.")
    r.add_argument("--input", required=True, help="Path to event.json")
    r.add_argument("--dry-run", action="store_true", help="Evaluate only; do NOT write cold/audit/state (opt-in).")

    n = sub.add_parser("notify", help="Send PushDeer notification (explicit only).")
    n.add_argument("--text", required=True, help="Title / short text.")
    n.add_argument("--desp", default="", help="Body / description.")
    n.add_argument("--pushkey", default=None, help="Override env PUSHDEER_KEY.")
    n.add_argument("--url", default=None, help="Override env PUSHDEER_URL (default api2.pushdeer.com).")

    a = sub.add_parser("audit", help="Show audit summary (only on explicit request).")

    g = sub.add_parser("reset-gate", help="Reset circuit breaker gate state (manual only).")

    args = p.parse_args()
    paths = get_paths(args.root)

    if args.cmd == "fetch":
        n_fx = fetch_rss_to_inbox(
            url=str(args.url),
            inbox_dir=paths.data_dir / "inbox",
            limit=int(args.limit),
        )
        if args.print_count:
            print(f"Fetched: {n_fx}")
        return

    if args.cmd == "ingest":
        n_ing = ingest(
            input_path=Path(args.input).expanduser().resolve(),
            cold_dir=paths.cold_dir,
            glob_pattern=str(args.glob),
        )
        if args.print_count:
            print(f"Ingested: {n_ing}")
        return

    if args.cmd == "run":
        msg = run_once(
            config_dir=paths.config_dir,
            cold_dir=paths.cold_dir,
            audit_dir=paths.audit_dir,
            state_dir=paths.state_dir,
            input_json=Path(args.input).expanduser().resolve(),
            dry_run=bool(args.dry_run),
        )
        if args.dry_run:
            print(msg)
        else:
            if msg:
                print(msg)
        return

    if args.cmd == "notify":
        ok = send_push(text=str(args.text), desp=str(args.desp), pushkey=args.pushkey, url=args.url)
        if ok:
            print("OK: pushed.")
        else:
            raise SystemExit("ERR: push failed.")
        return

    if args.cmd == "audit":
        print(summarize_interrupts(paths.audit_dir))
        return

    if args.cmd == "reset-gate":
        reset_gate(paths.state_dir)
        print("OK: gate reset.")
        return


if __name__ == "__main__":
    main()

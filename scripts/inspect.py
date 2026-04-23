#!/usr/bin/env python3
"""SwitchBoard decision log inspector.

Usage:
    python scripts/inspect.py recent [N]          # last N decisions (default 20)
    python scripts/inspect.py summary [N]         # aggregated stats over last N (default 100)
    python scripts/inspect.py show <request_id>   # single decision lookup

Reads from the admin API at http://localhost:20401 by default.
Override with SWITCHBOARD_URL env var.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

BASE_URL = os.environ.get("SWITCHBOARD_URL", "http://localhost:20401").rstrip("/")


def _get(path: str) -> Any:
    url = f"{BASE_URL}{path}"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        print(f"HTTP {exc.code}: {body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"Cannot reach SwitchBoard at {BASE_URL}: {exc.reason}", file=sys.stderr)
        sys.exit(1)


def _fmt_record(r: dict) -> str:
    lines = [
        f"  timestamp:   {r.get('timestamp', '')}",
        f"  request_id:  {r.get('request_id') or '(none)'}",
        f"  status:      {r.get('status', '')}",
        f"  lane:        {r.get('selected_lane', '')}",
        f"  backend:     {r.get('selected_backend', '')}",
        f"  rule:        {r.get('rule_name', '')}",
        f"  reason:      {r.get('reason', '')}",
        f"  latency_ms:  {r.get('latency_ms')}",
    ]
    if r.get("task_type"):
        lines.append(f"  task_type:   {r['task_type']}")
    if r.get("error_category"):
        lines.append(f"  error_cat:   {r['error_category']}")
    if r.get("error"):
        lines.append(f"  error:       {r['error']}")
    if r.get("context_summary"):
        cs = r["context_summary"]
        lines.append(
            f"  context:     task={cs.get('task_type')} complexity={cs.get('complexity')}"
            f" tokens={cs.get('estimated_tokens')}"
            f" tools={cs.get('requires_tools')} long_ctx={cs.get('requires_long_context')}"
        )
    return "\n".join(lines)


def cmd_recent(args: list[str]) -> None:
    n = int(args[0]) if args else 20
    records = _get(f"/admin/decisions/recent?n={n}")
    if not records:
        print("(no decisions recorded yet)")
        return
    for i, r in enumerate(records, 1):
        print(f"[{i}]")
        print(_fmt_record(r))
        print()


def cmd_summary(args: list[str]) -> None:
    n = int(args[0]) if args else 100
    s = _get(f"/admin/summary?n={n}")
    print(f"Window: last {s['window']} decisions ({s['total']} recorded)")
    print(f"  success:  {s['success_count']}   error: {s['error_count']}")
    print()
    print("Lanes:")
    for lane, count in sorted(s["lane_counts"].items(), key=lambda x: -x[1]):
        print(f"  {lane:<20} {count}")
    print()
    print("Backends:")
    for backend, count in sorted(s["backend_counts"].items(), key=lambda x: -x[1]):
        print(f"  {backend:<20} {count}")
    print()
    print("Rules:")
    for rule, c in sorted(s["rule_counts"].items(), key=lambda x: -x[1]):
        print(f"  {rule:<30} {c}")
    if s["error_category_counts"]:
        print()
        print("Error categories:")
        for cat, c in sorted(s["error_category_counts"].items(), key=lambda x: -x[1]):
            print(f"  {cat:<25} {c}")
    print()
    print("Latency (successful requests):")
    print(f"  p50={s.get('latency_p50_ms')} ms  p95={s.get('latency_p95_ms')} ms  mean={s.get('latency_mean_ms')} ms")


def cmd_show(args: list[str]) -> None:
    if not args:
        print("Usage: inspect.py show <request_id>", file=sys.stderr)
        sys.exit(1)
    request_id = args[0]
    r = _get(f"/admin/decisions/{request_id}")
    print(_fmt_record(r))


_COMMANDS = {
    "recent": cmd_recent,
    "summary": cmd_summary,
    "show": cmd_show,
}


def main() -> None:
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    cmd = argv[0]
    if cmd not in _COMMANDS:
        print(f"Unknown command: {cmd!r}. Choose from: {', '.join(_COMMANDS)}", file=sys.stderr)
        sys.exit(1)

    _COMMANDS[cmd](argv[1:])


if __name__ == "__main__":
    main()

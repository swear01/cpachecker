#!/usr/bin/env python3
"""Run a supervisor and notify its coordinator after terminal summary generation."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--session", required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command or args.summary.exists():
        parser.error("a real supervisor command and a fresh summary path are required")
    # Reserve the receipt before launching; a killed wrapper leaves visible pending evidence.
    with args.receipt.open("x", encoding="utf-8") as receipt:
        receipt.write(json.dumps({"notification": "pending", "command": command}) + "\n")
    result = {"command": command, "summary": str(args.summary.resolve())}
    try:
        result["supervisor_exit"] = subprocess.run(command, check=False).returncode
    except OSError as error:
        result["supervisor_exit"] = 1
        result["launch_error"] = str(error)
    try:
        raw = args.summary.read_bytes()
        summary = json.loads(raw)
        if not isinstance(summary, dict) or not isinstance(summary.get("arms"), dict):
            raise TypeError("final summary must contain an arms object")
        if set(summary["arms"]) != {"stock", "augmented"}:
            raise ValueError("final summary must include both arms")
        result["summary_sha256"] = hashlib.sha256(raw).hexdigest()
        result["arms"] = {
            arm: {"records": data["records"], "missing": len(data["missing_tasks"])}
            for arm, data in summary["arms"].items()
        }
        stop = args.summary.parent / "STOP.json"
        result["stop"] = json.loads(stop.read_bytes()) if stop.exists() else None
    except (OSError, ValueError, KeyError, TypeError) as error:
        result["summary_error"] = str(error)
    message = "Core-only supervisor TERMINAL; final-summary harvest: " + json.dumps(result)
    try:
        sent = subprocess.run(
            ["hapi", "ping-peer", args.session, message],
            capture_output=True, text=True, timeout=60, check=False,
        )
        result["notification"] = "accepted" if sent.returncode == 0 else "failed"
        result["notification_exit"] = sent.returncode
        result["notification_output"] = sent.stdout + sent.stderr
    except (OSError, subprocess.TimeoutExpired) as error:
        result["notification"] = "failed"
        result["notification_output"] = str(error)
    temporary = args.receipt.with_name(args.receipt.name + ".tmp")
    temporary.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    temporary.replace(args.receipt)
    print(json.dumps(result), flush=True)
    # Accepted means the messaging command succeeded, not that a human read the message.
    return int(bool(result["supervisor_exit"] or "summary_error" in result
                    or result["notification"] != "accepted"))


if __name__ == "__main__":
    sys.exit(main())

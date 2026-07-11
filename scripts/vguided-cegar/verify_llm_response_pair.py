#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PairVerification:
    tasks: int
    recorded_calls: int
    replayed_calls: int


def load_calls(root: Path) -> dict[str, list[tuple[str, str, str]]]:
    calls: dict[str, list[tuple[str, str, str]]] = {}
    for path in sorted(root.rglob("llm_rounds.jsonl")):
        task = path.parent.name
        rows = []
        for line_number, line in enumerate(path.read_text().splitlines(), start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            try:
                rows.append(
                    (
                        row["request_hash"],
                        row["response_hash"],
                        row["response_source"],
                    )
                )
            except KeyError as error:
                raise ValueError(f"{path}:{line_number}: missing {error.args[0]}") from error
        if task in calls:
            raise ValueError(f"duplicate task dump: {task}")
        calls[task] = rows
    return calls


def verify_pair(record_root: Path, replay_root: Path) -> PairVerification:
    recorded = load_calls(record_root)
    replayed = load_calls(replay_root)
    if not recorded:
        raise ValueError(f"no recorded llm_rounds.jsonl under {record_root}")
    if set(recorded) != set(replayed):
        missing = sorted(set(recorded) - set(replayed))
        extra = sorted(set(replayed) - set(recorded))
        raise ValueError(f"task-set mismatch: missing_replay={missing}, extra_replay={extra}")

    for task in sorted(recorded):
        record_rows = recorded[task]
        replay_rows = replayed[task]
        if any(source != "live_recorded" for _, _, source in record_rows):
            raise ValueError(f"{task}: record arm contains non-live_recorded source")
        if any(source != "replay" for _, _, source in replay_rows):
            raise ValueError(f"{task}: replay arm contains non-replay source")
        record_hashes = [(request, response) for request, response, _ in record_rows]
        replay_hashes = [(request, response) for request, response, _ in replay_rows]
        if record_hashes[: len(replay_hashes)] != replay_hashes:
            raise ValueError(f"{task}: replay is not an exact prefix of the recorded responses")

    return PairVerification(
        tasks=len(recorded),
        recorded_calls=sum(map(len, recorded.values())),
        replayed_calls=sum(map(len, replayed.values())),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record-dump", required=True, type=Path)
    parser.add_argument("--replay-dump", required=True, type=Path)
    args = parser.parse_args()
    result = verify_pair(args.record_dump, args.replay_dump)
    print(
        f"paired responses verified: tasks={result.tasks} "
        f"recorded_calls={result.recorded_calls} replayed_calls={result.replayed_calls}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Locked read/modify/write access to logs/execution_queue.json.

This is the ONLY code path that should touch the queue file. scan-and-debate.sh
(via reconcile_queue.py) and execute-pending.sh both shell out to this module's
CLI instead of having a live Claude session read/edit the JSON directly — GAP-71/72
found that leaving queue mutation to an LLM following prose instructions inside a
long prompt was unreliable (the reconciliation step was silently skipped on its
first day in production) and unsynchronized (two automated sessions could race on
the same file with no lock).

Usage:
  python queue_io.py --mark-executed <prediction_id> <executed_at_iso>
"""
import argparse
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import PROJECT_ROOT

QUEUE_FILE = PROJECT_ROOT / "logs" / "execution_queue.json"
LOCK_FILE = PROJECT_ROOT / "logs" / "execution_queue.lock"


@contextmanager
def _locked():
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(LOCK_FILE, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def load_queue() -> list[dict]:
    if not QUEUE_FILE.exists():
        return []
    return json.loads(QUEUE_FILE.read_text())


def save_queue(entries: list[dict]) -> None:
    tmp = QUEUE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(entries, indent=2))
    os.replace(tmp, QUEUE_FILE)


@contextmanager
def locked_queue():
    """Yields the current queue list; saves whatever mutations were made to it on exit."""
    with _locked():
        entries = load_queue()
        yield entries
        save_queue(entries)


def mark_executed(prediction_id: str, executed_at: str) -> bool:
    with locked_queue() as entries:
        for e in entries:
            if e["id"] == prediction_id:
                e["executed"] = True
                e["executed_at"] = executed_at
                print(f"[queue_io] marked executed: {prediction_id}")
                return True
    print(f"[queue_io] no queue entry found for id: {prediction_id}")
    return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mark-executed", nargs=2, metavar=("PRED_ID", "EXECUTED_AT_ISO"))
    args = parser.parse_args()

    if args.mark_executed:
        pred_id, executed_at = args.mark_executed
        ok = mark_executed(pred_id, executed_at)
        sys.exit(0 if ok else 1)
    else:
        parser.print_help()

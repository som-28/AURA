"""Logger tool: collects messages and returns them as structured logs."""
from typing import Tuple, List


def run(args: dict, context: dict) -> Tuple[List[str], dict]:
    message = args.get("message") or args.get("msg") or ""
    logs = [f"LOG: {message}"]
    return logs, {"logged": message}

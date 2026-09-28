"""Local stdin control channel. Model text cannot manufacture user approval."""

import json
import queue
import sys
import threading
import time
from collections.abc import Callable
from uuid import uuid4


class ControlChannel:
    def __init__(self, stop: threading.Event, describe: Callable[[str], str]) -> None:
        self.stop = stop
        self.describe = describe
        self.responses: queue.Queue[tuple[str, bool]] = queue.Queue(maxsize=16)

    def start(self) -> None:
        threading.Thread(target=self._read, name="alicia-control", daemon=True).start()

    def _read(self) -> None:
        for line in sys.stdin:
            if line.strip() == "quit":
                self.stop.set()
                return
            try:
                value = json.loads(line)
                if (
                    isinstance(value, dict)
                    and isinstance(value.get("approval_id"), str)
                    and isinstance(value.get("approved"), bool)
                ):
                    self.responses.put_nowait((value["approval_id"], value["approved"]))
            except (ValueError, queue.Full):
                continue

    def confirm(self, tool: str, value: str) -> bool:
        identifier = uuid4().hex
        print(
            "ALICIA_CONFIRM:"
            + json.dumps(
                {"approval_id": identifier, "tool": tool, "value": value, "command": self.describe(value)},
                ensure_ascii=False,
            ),
            flush=True,
        )
        print(
            "Para autorizar, escriba: " + json.dumps({"approval_id": identifier, "approved": True}),
            flush=True,
        )
        deadline = time.monotonic() + 60
        while not self.stop.is_set() and time.monotonic() < deadline:
            try:
                approval_id, approved = self.responses.get(timeout=0.2)
                if approval_id == identifier:
                    return approved
            except queue.Empty:
                continue
        return False

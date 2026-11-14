"""Export local, allowlisted framework events from a running or stopped project."""

import argparse
from collections import deque
import json
from pathlib import Path
import re
import zipfile


EVENT = re.compile(
    r"^\S+ event=(?:choice\.commit|rewind|voice\.request) "
    r"(?:(?:status|rid|http_code|error_code|server_request_id|latency_ms|"
    r"bytes|turn|path|index|from|to)=(?:[\w.-]*|\[[0-9, ]*\]) ?)+$",
    re.ASCII,
)


def export(project, output):
    events = deque(maxlen=200)
    log = project / "ai_debug.log"
    if log.is_file():
        with log.open("rb") as stream:
            stream.seek(max(0, log.stat().st_size - 512 * 1024))
            for line in stream.read(512 * 1024).decode("utf-8", "replace").splitlines():
                if len(line) <= 400 and EVENT.fullmatch(line):
                    events.append(line)
    engine = project / "log.txt"
    engine_version = None
    if engine.is_file():
        with engine.open("rb") as stream:
            header = stream.read(4096).decode("utf-8", "replace")
        match = re.search(r"Ren'Py ([0-9.]+)", header)
        engine_version = match.group(1) if match else None
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("manifest.json", json.dumps({
            "format": 1, "renpy_version": engine_version, "events": len(events),
        }))
        bundle.writestr("events.txt", "\n".join(events))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    export(args.project, args.output)

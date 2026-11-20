from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from question2.agent import SupportPipeline  # noqa: E402

PUBLIC = ["T-1001", "T-1002", "T-1003", "T-1004"]


def main() -> None:
    pipe = SupportPipeline()
    rows = []
    for tid in PUBLIC:
        res = pipe.handle_ticket(tid)
        rows.append({"ticket_id": tid, "action": res.action, "kb_article": res.kb_article})
    print(f"{'ticket':8} {'call':10} {'input':>6} {'cached':>6} {'output':>6} {'points':>7}")
    for tid, call in zip(PUBLIC, pipe.session.calls):
        cached = min(call.cached_prefix_tokens, call.input_tokens)
        print(f"{tid:8} {call.label:10} {call.input_tokens:>6} {cached:>6} {call.output_tokens:>6} {call.points():>7}")
    print(json.dumps({"resolutions": rows, "total_points": pipe.session.total_points()}, indent=2))


if __name__ == "__main__":
    main()

"""Per-agent wall-clock for one job, from the event log the app already writes.

    python scripts/stage_times.py <job_id>          # or a path to the .jsonl

"starts" is the offset of the agent's first event from the job's first event;
"spans" runs to its last event. TOTAL includes the time the plan waited for
your approval. Pair it with the job's reports/token_usage.txt, which has the
per-model call time and hidden reasoning tokens.
"""
import json
import sys
from pathlib import Path

arg = sys.argv[1]
path = Path(arg) if arg.endswith(".jsonl") else (
    Path(__file__).resolve().parent.parent / "Agents_backend" / "data" / "events" / f"{arg}.jsonl")
events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
t0 = events[0]["timestamp"]
spans: dict[str, list[float]] = {}
for e in events:
    s = spans.setdefault(e["agent_name"], [e["timestamp"], e["timestamp"]])
    s[1] = e["timestamp"]
for agent, (a, b) in sorted(spans.items(), key=lambda kv: kv[1][0]):
    print(f"{agent:<22} starts +{a - t0:7.1f}s   spans {b - a:7.1f}s")
print(f"TOTAL {events[-1]['timestamp'] - t0:.1f}s  (includes plan-approval time)")

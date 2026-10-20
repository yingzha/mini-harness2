"""Demo for Lesson 2 (steps/s02_executor.py). Makes live Haiku calls (a few cents).

    python -m demos.d02_executor

Runs the executor on a small hand-written task twice: once with the stock
harness H0, once with an example harness whose guardrail, skill, script and
plugin all take part. Workspaces and full trajectories are kept under runs/.
"""

import time

import config
from steps.s00_llm import LLM
from steps.s01_harness import Harness, load_harness
from steps.s02_executor import Sandbox, execute, render_record

TASK = (
    "Compute total revenue per region from source/sales.csv. Each order counts once. "
    "Write output/summary.csv with exactly the columns region,revenue (revenue with "
    "2 decimals), one row per region, sorted by region."
)
SALES = (
    "order_id,region,amount\n"
    '1001,North,"$1,200.50"\n'
    "1002,South,$300.00\n"
    "1003,North,$99.50\n"
    "1002,South,$300.00\n"
    "1004,East,(45.00)\n"
)
EXPECTED = "region,revenue\nEast,-45.00\nNorth,1300.00\nSouth,300.00\n"

EXAMPLE_FILES = {
    "guardrails.md": (
        'When amounts look like money strings ("$1,200.50", "(45.00)"), load the `money` skill.\n'
        "Before finishing, open every file you wrote in output/ and check it against the task.\n"
    ),
    "skills/money/SKILL.md": (
        "---\n"
        "description: Turn exported money strings into numbers before any arithmetic.\n"
        "---\n"
        "1. `$` and `,` are formatting. `(45.00)` is an accounting negative: -45.00.\n"
        "2. Run skills/money/scripts/clean_money.py with args: <input.csv> <output.csv> <column>.\n"
        "   It writes a copy with that column as plain numbers.\n"
        "3. Remove duplicate records (same ID) before summing.\n"
    ),
    "skills/money/scripts/clean_money.py": (
        "import csv, sys\n"
        "src, dst, column = sys.argv[1:4]\n"
        "def number(s):\n"
        "    s = s.strip().replace('$', '').replace(',', '')\n"
        "    return -float(s[1:-1]) if s.startswith('(') and s.endswith(')') else float(s)\n"
        "with open(src, newline='') as f:\n"
        "    rows = list(csv.DictReader(f))\n"
        "for row in rows:\n"
        "    row[column] = number(row[column])\n"
        "with open(dst, 'w', newline='') as f:\n"
        "    w = csv.DictWriter(f, fieldnames=list(rows[0]))\n"
        "    w.writeheader(); w.writerows(rows)\n"
        "print(f'wrote {len(rows)} rows to {dst}')\n"
    ),
    "plugin/require_output.py": (
        "def before_finish(event):\n"
        "    if not event['output_files']:\n"
        "        return 'output/ is empty. Write the deliverable before finishing.'\n"
    ),
}

run_dir = config.RUNS_DIR / time.strftime("demo_l2_%Y%m%d-%H%M%S")
source = run_dir / "task_source"
source.mkdir(parents=True)
(source / "sales.csv").write_text(SALES)

h0, _ = load_harness(config.BASE_HARNESS_DIR)
harnesses = {"base": h0, "example": Harness({**h0.files, **EXAMPLE_FILES})}

llm = LLM.from_env(config.LLM_SETTINGS)
sandbox = Sandbox.from_docker(config.SANDBOX)
print(f"Task: {TASK}\n\nExpected (worked out by hand):\n{EXPECTED}")
for label, harness in harnesses.items():
    record = execute(llm, sandbox, harness, TASK, source, run_dir / label, config.ROLLOUT_LIMITS, label=label)
    (run_dir / f"{label}.md").write_text(render_record(record))
    used = sorted({c.name for s in record.steps for c in s.calls})
    print(f"=== {label} harness: {record.stop_reason}, {record.turns} turns, "
          f"{record.tool_calls} tool calls ({record.tool_errors} errors)")
    print(f"tools used: {', '.join(used) or 'none'}")
    nudges = [s.nudge for s in record.steps if s.nudge]
    if nudges:
        print(f"plugin nudges: {nudges}")
    for path, content in record.deliverable.items():
        verdict = "matches" if content.replace("\r\n", "\n") == EXPECTED else "differs from"
        print(f"output/{path} ({verdict} the expected answer):\n{content}")
    if not record.deliverable:
        print("(no deliverable)")
    print(f"full trajectory: {(run_dir / f'{label}.md').relative_to(config.ROOT)}\n")

print("Usage meter:\n" + llm.meter.report())

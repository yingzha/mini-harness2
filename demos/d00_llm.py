"""Demo for Lesson 0 (steps/s00_llm.py).

    python -m demos.d00_llm          # offline: the request each role would send
    python -m demos.d00_llm --live   # one real call per model, then the usage table
"""

import argparse

import config
from steps.s00_llm import LLM, build_request, text_of

parser = argparse.ArgumentParser(description="Lesson 0: talking to the frozen model M")
parser.add_argument("--live", action="store_true", help="make one real call per model")
args = parser.parse_args()

settings = config.LLM_SETTINGS

print("Roles → model / effort")
for role, spec in settings.roles.items():
    print(f"  {role:<9} {spec.model:<18} effort={spec.effort}")

print("\nRequest the executor would send:")
for key, value in build_request(settings, "executor", "You are a careful analyst.",
                                [{"role": "user", "content": "Say hi."}]).items():
    print(f"  {key}: {value}")

editor_request = build_request(settings, "editor", "You edit harnesses.",
                               [{"role": "user", "content": "Say hi."}])
print(f"\nThe editor's request adds: betas={editor_request['betas']} "
      f"fallbacks={editor_request['fallbacks']!r}")

if not args.live:
    print("\n(offline) Add --live to make one real call per model.")
else:
    llm = LLM.from_env(settings)
    question = [{"role": "user", "content": "In one short sentence: what is an agent harness?"}]
    for role in ("executor", "editor"):
        response = llm.call(role, "Answer in one sentence.", question)
        print(f"\n[{role} / {response.model}] stop_reason={response.stop_reason}")
        print("  " + text_of(response).strip())
    print("\nUsage meter:\n" + llm.meter.report())

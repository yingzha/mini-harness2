"""Scripted answers for whole pipelines, by who is asking: sessions run side
by side, so the order of requests is not fixed. Each session is recognised by
its system prompt."""

import config
from tests.scripted_api import reply, text, tool_use

EDITOR = config.LLM_SETTINGS.roles["editor"].model
EXECUTOR = config.LLM_SETTINGS.roles["executor"].model
REFLECTION = ("<edits>\ncomponent: guardrails.md\ncandidates: composed1\nchange: reopen the report\n"
              "observed: one run reread its report\nverdict: confounded\n</edits>\n\n"
              "<experience>\ncue: a report whose totals are typed into prose\nlesson: guardrails.md: recompute "
              "each total before finishing\nevidence: the guardrails.md row\nconfidence: low\n</experience>")


def chooses(id_: str | None) -> dict:
    """A selector's reply naming id_."""
    return reply(text(f"<why>{id_} matches the request.</why>\n```choice\n{id_}\n```"), model=EDITOR)


def routed(selector_picks: str | None = None):
    """Editors keep the base; composer j writes "Rule j." into guardrails.md;
    the selector picks `selector_picks`; the reflector writes one row and a
    lesson; every run of the agent just says done."""
    def answer(body: dict) -> dict:
        system, turn = body["system"], len(body["messages"])
        if "candidate answers should be delivered" in system:
            return chooses(selector_picks)
        if "complete record of one improvement round" in system:
            return reply(text(REFLECTION), model=EDITOR)
        for j in (1, 2):
            if f"You are composer {j} of" in system:
                if turn == 1:
                    write = tool_use("w", "write_file", {"path": "context/harness/guardrails.md", "content": f"Rule {j}.\n"})
                    return reply(write, model=EDITOR, stop_reason="tool_use")
                return reply(text(f"<notes>kept -> rule {j} -> h0 never reopened its report</notes>"), model=EDITOR)
        if body["model"] == EDITOR:
            return reply(text("<notes>KEEP_BASE</notes>"), model=EDITOR)   # the editors
        return reply(text("done"), model=EXECUTOR)                           # every run
    return answer

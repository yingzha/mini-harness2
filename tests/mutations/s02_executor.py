"""Bugs to plant in steps/s02_executor.py, each with the test that must catch it.

Run with: python tools/mutate.py tests/mutations/s02_executor.py
A control (expect=None) changes nothing observable, so no test may fail for it.
"""

MUTATIONS = [
    {
        "label": "child inherits full env (API key)",
        "file": "steps/s02_executor.py",
        "replace": [
            ("env = {**_CHILD_ENV, \"HOME\": str(cwd)}",
             "env = None"),
        ],
        "expect": "test_model_code_does_not_inherit_the_api_key",
    },
    {
        "label": "timeout 15x too long",
        "file": "steps/s02_executor.py",
        "replace": [
            ("text=True, timeout=timeout_s)",
             "text=True, timeout=timeout_s * 15)"),
        ],
        "expect": "test_runaway_code_is_stopped_at_the_timeout",
    },
    {
        "label": "clip keeps only the head",
        "file": "steps/s02_executor.py",
        "replace": [
            ("return f\"{text[:half]}\\n[... {len(text) - 2 * half} characters cut ...]\\n{text[-half:]}\"",
             "return text[:limit] + \"\\n[... characters cut ...]\""),
        ],
        "expect": "test_long_output_is_clipped_keeping_head_and_tail",
    },
    {
        "label": "clip disabled",
        "file": "steps/s02_executor.py",
        "replace": [
            ("    if len(text) <= limit:\n        return text",
             "    if True:\n        return text"),
        ],
        "expect": "test_long_output_is_clipped_keeping_head_and_tail",
    },
    {
        "label": "path confinement check removed",
        "file": "steps/s02_executor.py",
        "replace": [
            ("if not path.is_relative_to(base):",
             "if False:"),
        ],
        "expect": "test_file_tools_cannot_reach_outside_their_root",
    },
    {
        "label": "paths not resolved (.. and symlinks)",
        "file": "steps/s02_executor.py",
        "replace": [
            ("path = (base / rel).resolve()",
             "path = base / rel"),
        ],
        "expect": "test_file_tools_cannot_reach_outside_their_root",
    },
    {
        "label": "write_root not enforced",
        "file": "steps/s02_executor.py",
        "replace": [
            ("if not path.is_relative_to(write_root.resolve()):",
             "if False:"),
        ],
        "expect": "test_file_tools_cannot_reach_outside_their_root",
    },
    {
        "label": "only first tool result sent",
        "file": "steps/s02_executor.py",
        "replace": [
            ("messages.append({\"role\": \"user\", \"content\": results})",
             "messages.append({\"role\": \"user\", \"content\": results[:1]})"),
        ],
        "expect": "test_loop_returns_responses_unchanged_and_all_results_in_one_message",
    },
    {
        "label": "thinking blocks dropped",
        "file": "steps/s02_executor.py",
        "replace": [
            ("messages.append({\"role\": \"assistant\", \"content\": response.content})",
             "messages.append({\"role\": \"assistant\", \"content\": [b for b in response.content if b.type != \"thinking\"]})"),
        ],
        "expect": "test_loop_returns_responses_unchanged_and_all_results_in_one_message",
    },
    {
        "label": "tool exceptions not caught",
        "file": "steps/s02_executor.py",
        "replace": [
            ("except Exception as e:  # a failing tool",
             "except ZeroDivisionError as e:  # a failing tool"),
        ],
        "expect": "test_tool_failures_become_error_results_and_the_loop_goes_on",
    },
    {
        "label": "turn cap off by one",
        "file": "steps/s02_executor.py",
        "replace": [
            ("for turn in range(1, max_turns + 1):",
             "for turn in range(1, max_turns):"),
        ],
        "expect": "test_loop_stops_at_the_turn_cap",
    },
    {
        "label": "cut-off tool call executed",
        "file": "steps/s02_executor.py",
        "replace": [
            ("if response.stop_reason == \"max_tokens\":\n                    result = ToolResult(_CUT_OFF_CALL",
             "if False:\n                    result = ToolResult(_CUT_OFF_CALL"),
        ],
        "expect": "test_a_cut_off_tool_call_is_answered_but_not_run",
    },
    {
        "label": "plugin notes not sent to model",
        "file": "steps/s02_executor.py",
        "replace": [
            ("\"content\": \"\\n\\n\".join([result.output, *notes])})",
             "\"content\": result.output})"),
        ],
        "expect": "test_plugin_notes_reach_the_model_and_nudges_are_bounded",
    },
    {
        "label": "nudges unbounded",
        "file": "steps/s02_executor.py",
        "replace": [
            ("if hooks and nudges < MAX_NUDGES:",
             "if hooks:"),
        ],
        "expect": "test_plugin_notes_reach_the_model_and_nudges_are_bounded",
    },
    {
        "label": "hooks told no output files",
        "file": "steps/s02_executor.py",
        "replace": [
            ("for p in output_dir.rglob(\"*\") if p.is_file())}",
             "for p in output_dir.rglob(\"*\") if False)}"),
        ],
        "expect": "test_plugin_notes_reach_the_model_and_nudges_are_bounded",
    },
    {
        "label": "crashing hook is fatal",
        "file": "steps/s02_executor.py",
        "replace": [
            ("            if done.returncode != 0:\n                why",
             "            if False:\n                why"),
        ],
        "expect": "test_a_broken_plugin_is_recorded_and_the_rollout_continues",
    },
    {
        "label": "non-string hook result accepted",
        "file": "steps/s02_executor.py",
        "replace": [
            ("if isinstance(value, str):",
             "if True:"),
        ],
        "expect": "test_a_broken_plugin_is_recorded_and_the_rollout_continues",
    },
    {
        "label": "subagent returns its whole trace",
        "file": "steps/s02_executor.py",
        "replace": [
            ("return ToolResult(clip(sub.final_text), subtrace=sub.steps)",
             "return ToolResult(render_trajectory(sub.steps), subtrace=sub.steps)"),
        ],
        "expect": "test_skill_and_subagent_tools_follow_the_harness",
    },
    {
        "label": "subagent ignores its AGENT.md",
        "file": "steps/s02_executor.py",
        "replace": [
            ("sub = run_agent_loop(llm, \"executor\", agent.body,",
             "sub = run_agent_loop(llm, \"executor\", \"\","),
        ],
        "expect": "test_skill_and_subagent_tools_follow_the_harness",
    },
    {
        "label": "load_skill offered with no skills",
        "file": "steps/s02_executor.py",
        "replace": [
            ("    if not skills:\n        return None",
             "    if False:\n        return None"),
        ],
        "expect": "test_skill_and_subagent_tools_follow_the_harness",
    },
    {
        "label": "workspace gets skill text and plugins",
        "file": "steps/s02_executor.py",
        "replace": [
            ("if SCRIPT_FILE.fullmatch(path) or SKILL_SCRIPT.fullmatch(path):",
             "if True:"),
        ],
        "expect": "test_workspace_has_inputs_and_scripts_but_not_skill_text_or_plugins",
    },
    {
        "label": "workspace reused with leftovers",
        "file": "steps/s02_executor.py",
        "replace": [
            ("if workspace.exists() and any(workspace.iterdir()):",
             "if False:"),
        ],
        "expect": "test_workspace_has_inputs_and_scripts_but_not_skill_text_or_plugins",
    },
    {
        "label": "harness text not sent as system",
        "file": "steps/s02_executor.py",
        "replace": [
            ("harness.always_on_text(), task, tools,",
             "\"\", task, tools,"),
        ],
        "expect": "test_execute_records_the_deliverable_and_stats",
    },
    {
        "label": "deliverable not captured",
        "file": "steps/s02_executor.py",
        "replace": [
            ("for p in sorted(output.rglob(\"*\")) if p.is_file()}",
             "for p in sorted(output.rglob(\"*\")) if False}"),
        ],
        "expect": "test_execute_records_the_deliverable_and_stats",
    },
    {
        "label": "invalid harness not refused",
        "file": "steps/s02_executor.py",
        "replace": [
            ("if errors := validate(harness):",
             "if False:"),
        ],
        "expect": "test_execute_refuses_an_invalid_harness",
    },
    {
        "label": "tool errors not counted",
        "file": "steps/s02_executor.py",
        "replace": [
            ("return sum(c.is_error for s in self.steps for c in s.calls)",
             "return 0"),
        ],
        "expect": "test_execute_records_the_deliverable_and_stats",
    },
    {
        "label": "unknown tool not reported clearly",
        "file": "steps/s02_executor.py",
        "replace": [
            ("    if tool is None:\n        return ToolResult(f\"Unknown tool",
             "    if False:\n        return ToolResult(f\"Unknown tool"),
        ],
        "expect": "test_tool_failures_become_error_results_and_the_loop_goes_on",
    },
    {
        "label": "string args not rejected",
        "file": "steps/s02_executor.py",
        "replace": [
            ("if not isinstance(args, list):",
             "if False:"),
        ],
        "expect": "test_run_python_rejects_args_that_are_not_a_list",
    },
    {
        "label": "descriptions never reach the model",
        "file": "steps/s02_executor.py",
        "replace": [
            ("    return \"\\n\".join(f\"- {name}: {d.meta.get('description', '')}\" for name, d in sorted(documents.items()))",
             "    return \"\""),
        ],
        "expect": "test_skill_and_subagent_tools_follow_the_harness",
    },
    {
        "label": "equivalent: half = int(limit / 2)",
        "file": "steps/s02_executor.py",
        "replace": [
            ("half = limit // 2",
             "half = int(limit / 2)"),
        ],
        "expect": None,
    },
]

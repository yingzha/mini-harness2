"""Bugs to plant in steps/s02_executor.py, each with the test that must catch it.

Run with: python -m tools.mutate tests/mutations/s02_executor.py
A control (expect=None) changes nothing observable, so no test may fail for it.
"""

MUTATIONS = [
    {
        "label": "timeout 15x too long",
        "file": "steps/s02_executor.py",
        "replace": [
            ("p.wait(timeout=timeout_s)",
             "p.wait(timeout=timeout_s * 15)"),
        ],
        "expect": "test_runaway_code_is_stopped_at_the_timeout_and_leaves_nothing_running",
    },
    {
        "label": "clip keeps only the head",
        "file": "steps/s02_executor.py",
        "replace": [
            ("return f\"{text[:half]}\\n[... {len(text) - 2 * half} characters cut ...]\\n{text[-half:]}\"",
             "return text[:limit] + \"\\n[... characters cut ...]\""),
        ],
        "expect": "test_clip_keeps_head_and_tail",
    },
    {
        "label": "clip disabled",
        "file": "steps/s02_executor.py",
        "replace": [
            ("    if len(text) <= limit:\n        return text",
             "    if True:\n        return text"),
        ],
        "expect": "test_clip_keeps_head_and_tail",
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
        "label": "sandbox gets the API key passed through",
        "file": "steps/s02_executor.py",
        "replace": [
            ("\"--network\", \"none\",",
             "\"--network\", \"none\", \"--env\", \"ANTHROPIC_API_KEY\","),
        ],
        "expect": "test_model_code_sees_only_its_workspace_and_holds_no_power",
    },
    {
        "label": "sandbox sees every process on the VM",
        "file": "steps/s02_executor.py",
        "replace": [
            ("\"--network\", \"none\",",
             "\"--network\", \"none\", \"--pid\", \"host\","),
        ],
        "expect": "test_model_code_sees_only_its_workspace_and_holds_no_power",
    },
    {
        "label": "sandbox given the folder around the workspace",
        "file": "steps/s02_executor.py",
        "replace": [
            ("*map(str, args)], workspace, writable=True",
             "*map(str, args)], workspace.parent, writable=True"),
        ],
        "expect": "test_model_code_sees_only_its_workspace_and_holds_no_power",
    },
    {
        "label": "network left on",
        "file": "steps/s02_executor.py",
        "replace": [
            ("            \"--network\", \"none\",\n",
             ""),
        ],
        "expect": "test_model_code_sees_only_its_workspace_and_holds_no_power",
    },
    {
        "label": "sandbox runs as root",
        "file": "steps/s02_executor.py",
        "replace": [
            ("\"--user\", self.settings.user,",
             "\"--user\", \"root\","),
        ],
        "expect": "test_model_code_sees_only_its_workspace_and_holds_no_power",
    },
    {
        "label": "capabilities kept",
        "file": "steps/s02_executor.py",
        "replace": [
            ("\"--cap-drop\", \"ALL\", \"--security-opt\"",
             "\"--security-opt\""),
        ],
        "expect": "test_model_code_sees_only_its_workspace_and_holds_no_power",
    },
    {
        "label": "privileges can be gained (setuid)",
        "file": "steps/s02_executor.py",
        "replace": [
            (" \"--security-opt\", \"no-new-privileges\",",
             ""),
        ],
        "expect": "test_model_code_sees_only_its_workspace_and_holds_no_power",
    },
    {
        "label": "run_python gets a read-only workspace",
        "file": "steps/s02_executor.py",
        "replace": [
            ("workspace, writable=True, timeout_s=timeout_s)",
             "workspace, writable=False, timeout_s=timeout_s)"),
        ],
        "expect": "test_model_code_sees_only_its_workspace_and_holds_no_power",
    },
    {
        "label": "container never removed",
        "file": "steps/s02_executor.py",
        "replace": [
            ("        finally:\n            subprocess.run([\"docker\", \"rm\", \"--force\", container], capture_output=True)",
             "        finally:\n            pass"),
        ],
        "expect": "test_runaway_code_is_stopped_at_the_timeout_and_leaves_nothing_running",
    },
    {
        "label": "containers not labelled, so leftovers are invisible",
        "file": "steps/s02_executor.py",
        "replace": [
            ("            \"--label\", f\"{SANDBOX_LABEL}={source}\",\n",
             ""),
        ],
        "expect": "test_runaway_code_is_stopped_at_the_timeout_and_leaves_nothing_running",
    },
    {
        "label": "output buffered, so it is lost at a timeout",
        "file": "steps/s02_executor.py",
        "replace": [
            ("_PYTHON = (\"python\", \"-I\", \"-u\")",
             "_PYTHON = (\"python\", \"-I\")"),
        ],
        "expect": "test_runaway_code_is_stopped_at_the_timeout_and_leaves_nothing_running",
    },
    {
        "label": "no process limit",
        "file": "steps/s02_executor.py",
        "replace": [
            ("            \"--pids-limit\", str(self.settings.pids_limit),\n",
             ""),
        ],
        "expect": "test_fork_bombs_and_memory_blowups_stay_inside_the_sandbox",
    },
    {
        "label": "no memory limit",
        "file": "steps/s02_executor.py",
        "replace": [
            ("            \"--memory\", self.settings.memory,\n",
             ""),
        ],
        "expect": "test_fork_bombs_and_memory_blowups_stay_inside_the_sandbox",
    },
    {
        "label": "images may be downloaded",
        "file": "steps/s02_executor.py",
        "replace": [
            ("            \"--pull\", \"never\",                     # only the image we built, never a download\n",
             ""),
        ],
        "expect": "test_a_broken_sandbox_ends_the_rollout_instead_of_blaming_the_model",
    },
    {
        "label": "a failed create goes unnoticed",
        "file": "steps/s02_executor.py",
        "replace": [
            ("if made.returncode != 0:",
             "if False:"),
        ],
        "expect": "test_a_broken_sandbox_ends_the_rollout_instead_of_blaming_the_model",
    },
    {
        "label": "sandbox failures reported to the model",
        "file": "steps/s02_executor.py",
        "replace": [
            ("    except SandboxError:\n        raise",
             "    except ZeroDivisionError:\n        raise"),
        ],
        "expect": "test_a_broken_sandbox_ends_the_rollout_instead_of_blaming_the_model",
    },
    {
        "label": "nested mount translated through its parent",
        "file": "steps/s02_executor.py",
        "replace": [
            ("point = max(points, key=len)",
             "point = min(points, key=len)"),
        ],
        "expect": "test_host_paths_follow_the_most_specific_mount_and_keep_it_read_only",
    },
    {
        "label": "write granted through a read-only mount",
        "file": "steps/s02_executor.py",
        "replace": [
            ("if writable and not folder.writable:",
             "if False:"),
        ],
        "expect": "test_host_paths_follow_the_most_specific_mount_and_keep_it_read_only",
    },
    {
        "label": "path on no mount accepted",
        "file": "steps/s02_executor.py",
        "replace": [
            ("    if not points:\n        raise SandboxError",
             "    if False:\n        raise SandboxError"),
        ],
        "expect": "test_host_paths_follow_the_most_specific_mount_and_keep_it_read_only",
    },
    {
        "label": "plugin prints corrupt its result",
        "file": "steps/s02_executor.py",
        "replace": [
            ("    os.dup2(2, 1)   # what",
             "    pass   # what"),
        ],
        "expect": "test_plugin_notes_reach_the_model_and_nudges_are_bounded",
    },
    {
        "label": "plugins may rewrite the deliverable",
        "file": "steps/s02_executor.py",
        "replace": [
            ("self._workspace, writable=False,",
             "self._workspace, writable=True,"),
        ],
        "expect": "test_a_broken_plugin_is_recorded_and_the_rollout_continues",
    },
    {
        "label": "a plugin's sys.exit crashes the rollout",
        "file": "steps/s02_executor.py",
        "replace": [
            ("except ValueError:   # it called",
             "except ZeroDivisionError:   # it called"),
        ],
        "expect": "test_a_broken_plugin_is_recorded_and_the_rollout_continues",
    },
    {
        "label": "sandbox output held in full while it streams",
        "file": "steps/s02_executor.py",
        "replace": [
            ("            del self._tail[:-self._half]\n",
             ""),
        ],
        "expect": "test_huge_output_is_cut_on_our_side_keeping_head_and_tail",
    },
    {
        "label": "a timed-out call waits for its code to finish",
        "file": "steps/s02_executor.py",
        "replace": [
            ("p.kill()   # its streams close",
             "pass   # its streams close"),
        ],
        "expect": "test_runaway_code_is_stopped_at_the_timeout_and_leaves_nothing_running",
    },
    {
        "label": "output that isn't UTF-8 crashes the tool",
        "file": "steps/s02_executor.py",
        "replace": [
            ("errors=\"replace\")   # model code",
             "errors=\"strict\")   # model code"),
        ],
        "expect": "test_output_in_any_encoding_reaches_the_model",
    },
    {
        "label": "start and end decoded apart",
        "file": "steps/s02_executor.py",
        "replace": [
            ("return decode(self._head + self._tail)",
             "return decode(self._head) + decode(self._tail)"),
        ],
        "expect": "test_output_in_any_encoding_reaches_the_model",
    },
    {
        "label": "stdin never reaches the sandbox",
        "file": "steps/s02_executor.py",
        "replace": [
            ("            stream.write(data)\n",
             "            pass\n"),
        ],
        "expect": "test_plugin_notes_reach_the_model_and_nudges_are_bounded",
    },
    {
        "label": "deliverable includes untouched files",
        "file": "steps/s02_executor.py",
        "replace": [
            ("if baseline.get(path) != digest]",
             "if True]"),
        ],
        "expect": "test_execute_records_the_deliverable_and_stats",
    },
    {
        "label": "deliverable not captured",
        "file": "steps/s02_executor.py",
        "replace": [
            ("                   for path in changed_files(workspace, baseline)}",
             "                   for path in []}"),
        ],
        "expect": "test_execute_records_the_deliverable_and_stats",
    },
    {
        "label": "hooks told nothing changed",
        "file": "steps/s02_executor.py",
        "replace": [
            ("\"changed_files\": changed_files(self._workspace, self._baseline)}",
             "\"changed_files\": []}"),
        ],
        "expect": "test_plugin_notes_reach_the_model_and_nudges_are_bounded",
    },
    {
        "label": "extra mounts writable",
        "file": "steps/s02_executor.py",
        "replace": [
            ("dst={dst},readonly\")",
             "dst={dst}\")"),
        ],
        "expect": "test_an_agent_cannot_grade_itself",
    },
    {
        "label": "environment variables dropped",
        "file": "steps/s02_executor.py",
        "replace": [
            ("*more, *variables,",
             "*more,"),
        ],
        "expect": "test_its_own_checks_grade_the_workspace",
    },
    {
        "label": "equivalent: half = int(limit / 2)",
        "file": "steps/s02_executor.py",
        "replace": [
            ("    half = limit // 2\n",
             "    half = int(limit / 2)\n"),
        ],
        "expect": None,
    },
    {
        "label": "equivalent: sorted(...)[-1] instead of max",
        "file": "steps/s02_executor.py",
        "replace": [
            ("point = max(points, key=len)",
             "point = sorted(points, key=len)[-1]"),
        ],
        "expect": None,
    },
]

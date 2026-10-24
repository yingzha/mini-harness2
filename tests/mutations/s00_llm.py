"""Bugs to plant in steps/s00_llm.py, each with the test that must catch it.

Run with: python -m tools.mutate tests/mutations/s00_llm.py
A control (expect=None) changes nothing observable, so no test may fail for it.
"""

MUTATIONS = [
    {
        "label": "typo: output_configs",
        "file": "steps/s00_llm.py",
        "replace": [
            ("\"output_config\": {\"effort\": spec.effort},",
             "\"output_configs\": {\"effort\": spec.effort},"),
        ],
        "expect": "test_requests_are_valid_for_the_real_sdk",
    },
    {
        "label": "fallbacks sent to every model",
        "file": "steps/s00_llm.py",
        "replace": [
            ("if spec.model in settings.server_fallback_models:",
             "if True:"),
        ],
        "expect": "test_requests_are_valid_for_the_real_sdk",
    },
    {
        "label": "role ignored (always executor spec)",
        "file": "steps/s00_llm.py",
        "replace": [
            ("spec = settings.roles[role]",
             "spec = settings.roles[\"executor\"]"),
        ],
        "expect": "test_requests_are_valid_for_the_real_sdk",
    },
    {
        "label": "caching dropped",
        "file": "steps/s00_llm.py",
        "replace": [
            ("\"cache_control\": {\"type\": \"ephemeral\"},",
             ""),
        ],
        "expect": "test_requests_are_valid_for_the_real_sdk",
    },
    {
        "label": "None cache field not coalesced",
        "file": "steps/s00_llm.py",
        "replace": [
            ("cache_read = usage.cache_read_input_tokens or 0",
             "cache_read = usage.cache_read_input_tokens"),
        ],
        "expect": "test_meter_costs_follow_reported_usage",
    },
    {
        "label": "unpriced fallback model crashes",
        "file": "steps/s00_llm.py",
        "replace": [
            ("model = response.model if response.model in self.settings.prices else request[\"model\"]",
             "model = response.model"),
        ],
        "expect": "test_fallback_served_by_an_unpriced_model_does_not_crash_the_run",
    },
    {
        "label": "tier off by one (>=)",
        "file": "steps/s00_llm.py",
        "replace": [
            ("and inp + cache_read + cache_write > price.long_prompt_threshold",
             "and inp + cache_read + cache_write >= price.long_prompt_threshold"),
        ],
        "expect": "test_long_prompt_tier_starts_strictly_above_threshold_and_counts_cached_tokens",
    },
    {
        "label": "cached tokens ignored for tier",
        "file": "steps/s00_llm.py",
        "replace": [
            ("and inp + cache_read + cache_write > price.long_prompt_threshold",
             "and inp > price.long_prompt_threshold"),
        ],
        "expect": "test_long_prompt_tier_starts_strictly_above_threshold_and_counts_cached_tokens",
    },
    {
        "label": "blank workspace id sent",
        "file": "steps/s00_llm.py",
        "replace": [
            ("return {\"anthropic-workspace-id\": workspace} if workspace else {}",
             "return {\"anthropic-workspace-id\": workspace} if workspace is not None else {}"),
        ],
        "expect": "test_blank_workspace_id_sends_no_header",
    },
    {
        "label": "meter overwrites instead of adding",
        "file": "steps/s00_llm.py",
        "replace": [
            ("r.cost_usd += cost",
             "r.cost_usd = cost"),
        ],
        "expect": "test_meter_costs_follow_reported_usage",
    },
    {
        "label": "call count overwritten",
        "file": "steps/s00_llm.py",
        "replace": [
            ("r.calls += 1",
             "r.calls = 1"),
        ],
        "expect": "test_meter_costs_follow_reported_usage",
    },
    {
        "label": "input tokens overwritten",
        "file": "steps/s00_llm.py",
        "replace": [
            ('r.input_tokens += line["input"]',
             'r.input_tokens = line["input"]'),
        ],
        "expect": "test_meter_costs_follow_reported_usage",
    },
    {
        "label": "equivalent: * 1e-6",
        "file": "steps/s00_llm.py",
        "replace": [
            ("    ) / 1_000_000",
             "    ) * 1e-6"),
        ],
        "expect": None,
    },
    {
        "label": "the real client ignores the configured retries",
        "file": "steps/s00_llm.py",
        "replace": [(", max_retries=settings.max_retries)", ")")],
        "expect": "test_the_real_client_retries_as_configured",
    },
    {
        "label": "no line written per call",
        "file": "steps/s00_llm.py",
        "replace": [('                        log.write(json.dumps(line) + "\\n")\n', "                        pass\n")],
        "expect": "test_every_call_leaves_a_line_with_its_own_usage",
    },
    {
        "label": "the log's folder not created",
        "file": "steps/s00_llm.py",
        "replace": [("                self._log.parent.mkdir(parents=True, exist_ok=True)", "                pass")],
        "expect": "test_every_call_leaves_a_line_with_its_own_usage",
    },
    {
        "label": "the session not logged",
        "file": "steps/s00_llm.py",
        "replace": [('"session": session,', '"session": "",')],
        "expect": "test_every_call_leaves_a_line_with_its_own_usage",
    },
    {
        "label": "the request's depth not logged",
        "file": "steps/s00_llm.py",
        "replace": [("depth=len(messages))", "depth=1)")],
        "expect": "test_every_call_leaves_a_line_with_its_own_usage",
    },
    {
        "label": "thinking tokens not logged",
        "file": "steps/s00_llm.py",
        "replace": [('"thinking": usage.output_tokens_details.thinking_tokens if usage.output_tokens_details else None,',
                     '"thinking": None,')],
        "expect": "test_every_call_leaves_a_line_with_its_own_usage",
    },
    {
        "label": "cache writes logged as reads",
        "file": "steps/s00_llm.py",
        "replace": [('"cache_read": usage.cache_read_input_tokens or 0,', '"cache_read": usage.cache_creation_input_tokens or 0,')],
        "expect": "test_every_call_leaves_a_line_with_its_own_usage",
    },
    {
        "label": "from_env drops the usage log",
        "file": "steps/s00_llm.py",
        "replace": [("return cls(client, settings, UsageMeter(settings.prices, usage_log))", "return cls(client, settings)")],
        "expect": "test_every_call_leaves_a_line_with_its_own_usage",
    },
    {
        "label": "the time of a call not logged",
        "file": "steps/s00_llm.py",
        "replace": [('"time": self._clock(),', '"time": 0,')],
        "expect": "test_every_call_leaves_a_line_with_its_own_usage",
    },
    {
        "label": "a log that can't be written ends the run",
        "file": "steps/s00_llm.py",
        "replace": [("                except OSError as e:", "                except ValueError as e:")],
        "expect": "test_a_usage_log_that_cannot_be_written_does_not_end_the_run",
    },
    {
        "label": "the warning repeats on every call",
        "file": "steps/s00_llm.py",
        "replace": [("                    self._log = None\n", "                    pass\n")],
        "expect": "test_a_usage_log_that_cannot_be_written_does_not_end_the_run",
    },
]

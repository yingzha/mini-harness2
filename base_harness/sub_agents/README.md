# Subagents (C5): delegated workers with their own context

Add a subagent as `sub_agents/<name>/AGENT.md`:

    ---
    description: <one line: when to delegate to it>
    ---
    <its system prompt>

It sees only its own file and the request it is given, and returns only its
final text. Worth it when the input is large and the answer is small.

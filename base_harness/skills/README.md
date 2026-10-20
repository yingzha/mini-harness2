# Skills (C6): procedures loaded on demand

Add a skill as `skills/<name>/SKILL.md`:

    ---
    description: <one line: what situation it handles>
    ---
    <the procedure>

Helper scripts the skill runs go in `skills/<name>/scripts/<file>.py`.

A skill is only ever used if `systemprompt.md` or `guardrails.md` contains its
trigger line: When <situation>, load the `<name>` skill.

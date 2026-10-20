# Plugins (C8): code that runs inside the tool loop

Add a plugin as `plugin/<name>.py` defining one or both hooks:

    def after_tool(event): ...     # return text to append to the tool result, or None
    def before_finish(event): ...  # return a message to keep the agent working, or None

A plugin enforces a behaviour rather than asking for it: the model can skip
prose, but it cannot skip a hook.

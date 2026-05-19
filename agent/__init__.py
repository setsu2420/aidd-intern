"""aidd-intern agent package."""


def __getattr__(name: str):
    if name == "submission_loop":
        from agent.core.agent_loop import submission_loop

        return submission_loop
    raise AttributeError(f"module 'agent' has no attribute {name!r}")


__all__ = ["submission_loop"]

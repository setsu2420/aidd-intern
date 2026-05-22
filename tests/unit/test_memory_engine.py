import json
import pytest
from unittest.mock import MagicMock, patch

from agent.core.memory import MermaidTaskCanvas, LayeredMemoryPipeline
from agent.core.tools import create_builtin_tools


def test_mermaid_task_canvas_states():
    canvas = MermaidTaskCanvas()
    canvas.add_node("AlignStructures", "RUNNING", "running bold alignment")
    canvas.add_node("GenerateBinder", "PENDING")
    canvas.add_edge("AlignStructures", "GenerateBinder")

    # Render check
    mermaid_str = canvas.render_mermaid()
    assert "AlignStructures" in mermaid_str
    assert "GenerateBinder" in mermaid_str
    assert "🔵 AlignStructures (running bold alignment)" in mermaid_str
    assert "🟡 GenerateBinder" in mermaid_str
    assert "AlignStructures --> GenerateBinder" in mermaid_str

    # Update state
    canvas.update_node("AlignStructures", "SUCCESS", "0.54s")
    mermaid_str2 = canvas.render_mermaid()
    assert "🟢 AlignStructures (0.54s)" in mermaid_str2

    # Clear
    canvas.clear()
    assert (
        canvas.render_mermaid()
        == "```mermaid\ngraph TD\n    Empty[No task initialized]\n```"
    )


def test_layered_memory_pipeline_formatting():
    mock_retrieval_res = {
        "rewritten_query": "What are user's design constraints?",
        "categories": [
            {
                "name": "aidd_parameters",
                "description": "Preferred binder target hotspots and hyperparameters",
                "summary": "### AIDD Preferences\n- Target hotspot: GLU45\n- Epochs: 200",
            }
        ],
        "items": [
            {
                "memory_type": "preference",
                "content": "Prefers standard protein design pipelines",
            },
            {"memory_type": "constraint", "content": "Must fit within 12GB GPU VRAM"},
        ],
    }

    pipeline = LayeredMemoryPipeline(client=MagicMock())
    res = pipeline.format_layered_memories(mock_retrieval_res, user_name="Alice")

    # Check L1 (Atomic Memory)
    assert len(res["L1_atomic"]) == 2
    assert res["L1_atomic"][0]["type"] == "preference"
    assert res["L1_atomic"][0]["content"] == "Prefers standard protein design pipelines"

    # Check L2 (Scenario Blocks)
    assert "aidd_parameters" in res["L2_scenarios"]
    assert "GLU45" in res["L2_scenarios"]["aidd_parameters"]["summary"]

    # Check L3 (Profile & Persona)
    assert "# Alice Profile & Persona" in res["L3_profile"]
    assert "Must fit within 12GB GPU VRAM" in res["L3_profile"]

    # Check the whole structured block (formatted_prompt)
    prompt = res["formatted_prompt"]
    assert "🧠 LAYERED LONG-TERM MEMORY ENGINE" in prompt
    assert "[L3: USER PROFILE & PERSONA]" in prompt
    assert "[L2: ACTIVE SCENARIO BLOCKS]" in prompt
    assert "[L1: ATOMIC FACTS & PREFERENCES]" in prompt
    assert "1. [PREFERENCE] Prefers standard protein design pipelines" in prompt


@pytest.mark.asyncio
async def test_update_task_canvas_handler_works():
    tools = create_builtin_tools(local_mode=True)
    update_tool = [t for t in tools if t.name == "update_task_canvas"][0]

    class FakeSession:
        def __init__(self):
            self.task_canvas = MermaidTaskCanvas()

    session = FakeSession()
    args = {
        "node": "Docking",
        "status": "RUNNING",
        "details": "Autodock Vina calculation",
        "edge_to": "RankCandidates",
    }

    # Execute
    output, success = await update_tool.handler(args, session=session)
    assert success is True
    assert "Successfully updated task canvas node" in output
    assert "Docking (Autodock Vina calculation)" in output
    assert "Docking --> RankCandidates" in output


@pytest.mark.asyncio
@patch("agent.core.memu.MemUClient.retrieve")
async def test_layered_retrieve_handler_works(mock_retrieve, monkeypatch):
    monkeypatch.setenv("MEMU_API_KEY", "dummy_key")
    mock_retrieve.return_value = {
        "rewritten_query": "What are user's preferences?",
        "categories": [],
        "items": [{"memory_type": "preference", "content": "Loves standard models"}],
    }

    tools = create_builtin_tools(local_mode=True)
    retrieve_tool = [t for t in tools if t.name == "memu_retrieve_memories"][0]

    class FakeSession:
        def __init__(self):
            self.hf_username = "Bob"

    session = FakeSession()
    output, success = await retrieve_tool.handler(
        {"query": "preferences"}, session=session
    )
    assert success is True
    data = json.loads(output)
    assert "Bob Profile & Persona" in data["L3_profile"]
    assert "Loves standard models" in data["L3_profile"]
    assert "Loves standard models" in data["formatted_prompt"]


@pytest.mark.asyncio
async def test_event_listener_performance_metrics():
    from agent.main import event_listener
    import asyncio
    from agent.core.session import Event

    event_queue = asyncio.Queue()
    submission_queue = asyncio.Queue()
    turn_complete_event = asyncio.Event()
    ready_event = asyncio.Event()

    class MockConfig:
        model_name = "test-model"

    class MockSession:
        def __init__(self):
            self.config = MockConfig()
            self._cancelled = asyncio.Event()

        async def send_deferred_turn_complete_notification(self, event):
            pass

    session_holder = [MockSession()]

    # Run event listener in background task
    listener_task = asyncio.create_task(
        event_listener(
            event_queue,
            submission_queue,
            turn_complete_event,
            ready_event,
            prompt_session=None,
            config=session_holder[0].config,
            session_holder=session_holder,
        )
    )

    await asyncio.sleep(0.01)

    # Put a tool_call and output to accumulate tool times
    await event_queue.put(Event(event_type="tool_call", data={"tool": "PXDesign"}))
    await event_queue.put(
        Event(
            event_type="tool_output",
            data={"output": "success", "success": True, "duration_s": 1.25},
        )
    )

    # Put an llm call to accumulate thinking times
    await event_queue.put(Event(event_type="llm_call", data={"latency_ms": 3500}))

    # Trigger turn complete
    await event_queue.put(Event(event_type="turn_complete"))

    # Wait for turn completion
    await asyncio.wait_for(turn_complete_event.wait(), timeout=3.0)

    listener_task.cancel()
    try:
        await listener_task
    except asyncio.CancelledError:
        pass

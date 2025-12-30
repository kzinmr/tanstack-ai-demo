from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from tanstack_pydantic_ai import TanStackAIAdapter
from tanstack_pydantic_ai.adapter.request_types import (
    ToolCallFunction,
    ToolCallPart as UIToolCallPart,
    UIMessage,
)


def test_load_messages_reorders_tool_return_after_tool_call() -> None:
    tool_call_id = "call-123"
    messages = [
        UIMessage(role="user", content="show monthly calls"),
        UIMessage(
            role="assistant",
            toolCalls=[
                UIToolCallPart(
                    id=tool_call_id,
                    function=ToolCallFunction(
                        name="execute_query_readonly",
                        arguments="{}",
                    ),
                )
            ],
        ),
        UIMessage(role="assistant", content="Here are the results."),
        UIMessage(
            role="tool",
            content='{"type":"tool_result","message":"ok"}',
            toolCallId=tool_call_id,
            name="execute_query_readonly",
        ),
        UIMessage(role="user", content="thanks"),
    ]

    loaded = TanStackAIAdapter.load_messages(messages)

    assert isinstance(loaded[0], ModelRequest)
    assert isinstance(loaded[0].parts[0], UserPromptPart)

    assert isinstance(loaded[1], ModelResponse)
    assert any(isinstance(part, ToolCallPart) for part in loaded[1].parts)

    assert isinstance(loaded[2], ModelRequest)
    assert isinstance(loaded[2].parts[0], ToolReturnPart)
    assert loaded[2].parts[0].tool_call_id == tool_call_id

    assert isinstance(loaded[3], ModelResponse)
    assert any(
        isinstance(part, TextPart) and part.content == "Here are the results."
        for part in loaded[3].parts
    )

    assert isinstance(loaded[4], ModelRequest)
    assert isinstance(loaded[4].parts[0], UserPromptPart)

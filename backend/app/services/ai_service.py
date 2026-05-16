import json
import os
from typing import Any, AsyncGenerator, Dict, List, Optional

import litellm

from app.config import settings

# Tell litellm to silently drop params unsupported by a model
litellm.drop_params = True
litellm.set_verbose = False


def _apply_env_keys() -> None:
    """Push configured API keys into the environment so litellm can pick them up."""
    key_map = {
        "OPENAI_API_KEY": settings.OPENAI_API_KEY,
        "ANTHROPIC_API_KEY": settings.ANTHROPIC_API_KEY,
        "GEMINI_API_KEY": settings.GOOGLE_API_KEY,
        "MISTRAL_API_KEY": settings.MISTRAL_API_KEY,
        "COHERE_API_KEY": settings.COHERE_API_KEY,
        "GROQ_API_KEY": settings.GROQ_API_KEY,
        "TOGETHERAI_API_KEY": settings.TOGETHER_API_KEY,
        "HUGGINGFACE_API_KEY": settings.HUGGINGFACE_API_KEY,
        "AZURE_API_KEY": settings.AZURE_OPENAI_API_KEY,
        "AZURE_API_BASE": settings.AZURE_OPENAI_ENDPOINT,
    }
    for env_var, value in key_map.items():
        if value:
            os.environ[env_var] = value


def _build_kwargs(
    model: str,
    messages: List[Dict[str, str]],
    temperature: float,
    max_tokens: int,
    stream: bool = False,
    tools: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    return kwargs


async def chat_completion(
    model: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 4096,
    tools: Optional[List[Dict]] = None,
) -> Any:
    """Non-streaming chat completion — returns a litellm ModelResponse."""
    _apply_env_keys()
    kwargs = _build_kwargs(model, messages, temperature, max_tokens, tools=tools)
    return await litellm.acompletion(**kwargs)


async def stream_chat_completion(
    model: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> AsyncGenerator[str, None]:
    """Streaming chat completion — yields text chunks."""
    _apply_env_keys()
    kwargs = _build_kwargs(model, messages, temperature, max_tokens, stream=True)
    response = await litellm.acompletion(**kwargs)
    async for chunk in response:
        delta = chunk.choices[0].delta
        if delta and delta.content:
            yield delta.content


async def run_tool_loop(
    model: str,
    messages: List[Dict],
    temperature: float,
    max_tokens: int,
    tools: List[Dict],
    tool_registry: Dict,
    max_rounds: int = 5,
) -> Any:
    """
    Agentic tool-use loop.

    Calls the LLM; if it requests tool calls, invokes the corresponding MCP
    servers, appends results, and calls the LLM again — up to `max_rounds`.
    Returns the final litellm ModelResponse (no more tool calls, or limit hit).
    """
    # Import here to avoid circular dependency at module load time
    from app.services.mcp_service import invoke_tool

    _apply_env_keys()
    msgs = list(messages)  # work on a copy

    for _ in range(max_rounds):
        response = await litellm.acompletion(
            **_build_kwargs(model, msgs, temperature, max_tokens, tools=tools)
        )
        choice = response.choices[0]
        tool_calls = getattr(choice.message, "tool_calls", None)

        if not tool_calls:
            return response

        # Add the assistant turn with tool_calls
        assistant_msg: Dict = {"role": "assistant", "content": choice.message.content or ""}
        assistant_msg["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in tool_calls
        ]
        msgs.append(assistant_msg)

        # Execute each tool call
        for tc in tool_calls:
            tool_name = tc.function.name
            try:
                tool_args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                tool_args = {}

            server = tool_registry.get(tool_name)
            if server is None:
                result_text = f"[No MCP server registered for tool '{tool_name}']"
            else:
                result_text = await invoke_tool(server, tool_name, tool_args)

            msgs.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_text,
                }
            )

    # Limit reached — do one final call without tools
    return await litellm.acompletion(
        **_build_kwargs(model, msgs, temperature, max_tokens)
    )


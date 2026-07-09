"""
Streaming chat service — supports Anthropic, OpenAI, and Google Gemini providers.

Tool discovery is fully automatic via MCP (Streamable HTTP transport).
Adding a new @mcp.tool() in mcp_server.py is sufficient — no registry updates needed here.

Provider routing is by explicit catalog lookup (MODELS below), not name
prefix: every model id names its provider. Both /chat/providers and
_get_provider read that one list, so the catalog lives in exactly one place
(R1.5d).
"""
import asyncio
import json
import os
from abc import ABC, abstractmethod
from datetime import timedelta
from typing import AsyncGenerator, Callable

from mcp import types as mcp_types
from mcp.client.session_group import ClientSessionGroup, StreamableHttpParameters

SYSTEM_PROMPT = """You are a personal running assistant called Son of Anton, built into the Running Shoe Deal Finder. \
You help the user manage their shoe rotation, track mileage, find deals, and make smart decisions about their running gear. \
You have access to MCP tools to query owned shoes, run history, shoe notes, and current deals. \
Be concise and direct — the user is a competitive runner, running terminology is fine. \
Flag proactively when a shoe is approaching 700km or its mileage limit.

Shoes are categorized by type: short_distance_racer, long_distance_racer, long_run, tempo, intervals, daily_trainer, \
trail, recovery. Use shoe_type when recommending replacement deals, suggesting which shoe to wear for a \
specific workout type, or filtering deals by category. When the user asks for a shoe recommendation for a \
race, tempo run, or easy day — use shoe_type to match the right shoe from their rotation.

IMPORTANT RULES — follow every single time, no exceptions:

1. VERIFY BEFORE CLAIMING: Always call get_owned_shoes before making any statement about a specific shoe's \
mileage, status, or condition. Never rely on memory from earlier in the conversation — shoe state changes \
with every logged run.

2. CHECK BEFORE ADDING: Before calling add_shoe, always call get_shoes first to verify the shoe isn't \
already tracked. If it exists, tell the user instead of creating a duplicate.

3. VERIFY TOOL SUCCESS: After every write operation (log_run_to_shoe, add_shoe, retire_shoe, \
add_shoe_note, delete_shoe_run, etc.), check the response for "success": true. If success is false, \
report the exact error to the user — never claim an action succeeded without confirming it.

4. CORRECT SHOE IDENTITY: When the user refers to a shoe by nickname, color, or description, always \
call get_owned_shoes first and match it to the correct owned_shoe_id before calling any other tool. \
Never guess an id from memory.

5. RESOURCE CONTEXT: Your system prompt contains live shoe rotation and deals data loaded at conversation \
start. Use this for general rotation and deals questions without calling tools. Only call get_owned_shoes \
or get_deals tools if you need fresher data than what is in context, or if the user asks about something \
specific not covered by the pre-loaded context."""

MCP_SERVERS: list[dict] = [
    {
        "name": "anton",
        "url": os.getenv("MCP_SERVER_URL", "http://localhost:8000/mcp"),
        # This is the loopback self-connection: `url` points back at *this same*
        # process's /mcp (dependency_graph §8.1). Once R2.1 auth is active, /mcp
        # requires the bearer token, so this client must send it too — otherwise
        # Son of Anton silently degrades to "no tools available". The token is
        # attached per-connection by _server_headers() so it's read at connect
        # time (robust to import ordering) and scoped to this loopback entry.
        "auth_loopback": True,
    },
]


def _server_headers(server: dict) -> dict | None:
    """
    Build the request headers for one MCP server connection.

    Merges any static `headers` on the entry with the R2.1 bearer token for the
    loopback self-connection (`auth_loopback`). Read from the environment *here*
    (not at MCP_SERVERS definition time) because chat_service is imported before
    main.py's load_dotenv() runs — reading ANTON_SECRET at import could capture an
    empty value and silently 401 the loopback. Scoped to the flagged entry so the
    secret is never sent to any future external MCP server.
    """
    headers = dict(server.get("headers") or {})
    if server.get("auth_loopback"):
        from app.middleware.auth import get_named_token
        token = get_named_token("loopback")
        headers["Authorization"] = f"Bearer {token}"
    return headers or None

# Single source of truth for the chat model catalog (R1.5d). Each entry names
# its provider explicitly, so provider routing (_get_provider) and the
# /chat/providers listing both read this one list instead of two files agreeing
# by convention. `provider` is a key into PROVIDERS below.
MODELS: list[dict] = [
    {"id": "claude-sonnet-4-5",         "label": "Claude Sonnet", "description": "Best quality", "provider": "anthropic"},
    {"id": "claude-haiku-4-5-20251001", "label": "Claude Haiku",  "description": "Fastest",      "provider": "anthropic"},
    {"id": "gpt-4o",                    "label": "GPT-4o",        "description": "Best quality", "provider": "openai"},
    {"id": "gpt-4o-mini",               "label": "GPT-4o Mini",   "description": "Fastest",      "provider": "openai"},
    {"id": "gemini-2.0-flash",          "label": "Gemini Flash",  "description": "Fastest",      "provider": "google"},
    {"id": "gemini-2.0-pro",            "label": "Gemini Pro",    "description": "Best quality", "provider": "google"},
]

# Provider-level metadata: display name and the env var whose presence enables
# the provider. Keyed by MODELS[].provider. The provider *implementation* is
# mapped separately in _PROVIDER_CLASSES (below the class definitions).
PROVIDERS: dict[str, dict] = {
    "anthropic": {"name": "Claude",  "api_key_env": "ANTHROPIC_API_KEY"},
    "openai":    {"name": "ChatGPT", "api_key_env": "OPENAI_API_KEY"},
    "google":    {"name": "Gemini",  "api_key_env": "GOOGLE_API_KEY"},
}


def get_models() -> list[dict]:
    """The chat model catalog (id, label, description, provider) — the single
    source consumed by the /chat/providers endpoint and _get_provider."""
    return MODELS

# Defensive cap on the agentic loop in each provider's run() below. Without
# this, a model that keeps emitting tool calls indefinitely (a confusing
# tool result, or one that just won't accept "done") loops forever — there
# was no termination guarantee other than the model's own behavior.
MAX_AGENTIC_TURNS = 25


def _extract_result_text(call_result: mcp_types.CallToolResult) -> str:
    if call_result.isError:
        return json.dumps({"error": "Tool call failed"})
    return "\n".join(
        block.text for block in call_result.content if block.type == "text"
    ) or "{}"


class BaseLLMProvider(ABC):
    @abstractmethod
    async def run(
        self,
        initial_messages: list[dict],
        model: str,
        tools: list[mcp_types.Tool],
        queue: asyncio.Queue,
        call_mcp_tool: Callable,
        system_prompt: str = SYSTEM_PROMPT,
    ) -> None:
        """Agentic loop: stream LLM response, call tools, repeat until done.
        Push SSE event dicts to queue; end with {"type":"done"} or {"type":"error"}."""


class AnthropicProvider(BaseLLMProvider):
    def _tool_schema(self, tool: mcp_types.Tool) -> dict:
        return {
            "name": tool.name,
            "description": tool.description or "",
            "input_schema": tool.inputSchema,
        }

    async def run(self, initial_messages, model, tools, queue, call_mcp_tool, system_prompt=SYSTEM_PROMPT):
        from anthropic import AsyncAnthropic

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            await queue.put({"type": "error", "message": "ANTHROPIC_API_KEY is not configured."})
            return

        client = AsyncAnthropic(api_key=api_key)
        running = [{"role": m["role"], "content": m["content"]} for m in initial_messages]
        tool_schemas = [self._tool_schema(t) for t in tools]

        for _turn in range(MAX_AGENTIC_TURNS):
            streaming_tools: dict[int, dict] = {}

            async with client.messages.stream(
                model=model,
                max_tokens=4096,
                system=system_prompt,
                tools=tool_schemas,
                messages=running,
            ) as stream:
                async for event in stream:
                    if event.type == "content_block_start":
                        if event.content_block.type == "tool_use":
                            streaming_tools[event.index] = {
                                "id": event.content_block.id,
                                "name": event.content_block.name,
                                "input_str": "",
                            }
                            await queue.put({"type": "tool_call", "tool": event.content_block.name})

                    elif event.type == "content_block_delta":
                        if event.delta.type == "text_delta":
                            await queue.put({"type": "text", "content": event.delta.text})
                        elif event.delta.type == "input_json_delta" and event.index in streaming_tools:
                            streaming_tools[event.index]["input_str"] += event.delta.partial_json

                    elif event.type == "content_block_stop" and event.index in streaming_tools:
                        tu = streaming_tools[event.index]
                        try:
                            tu["input"] = json.loads(tu["input_str"]) if tu["input_str"] else {}
                        except json.JSONDecodeError:
                            tu["input"] = {}

                final_msg = await stream.get_final_message()

            tool_blocks = [b for b in (final_msg.content or []) if b.type == "tool_use"]
            if not tool_blocks:
                await queue.put({"type": "done"})
                return

            assistant_content = []
            for b in final_msg.content:
                if b.type == "text":
                    assistant_content.append({"type": "text", "text": b.text})
                elif b.type == "tool_use":
                    assistant_content.append(
                        {"type": "tool_use", "id": b.id, "name": b.name, "input": b.input}
                    )
            running.append({"role": "assistant", "content": assistant_content})

            tool_results = []
            for block in tool_blocks:
                result_text, success = await call_mcp_tool(block.name, block.input or {})
                await queue.put({"type": "tool_result", "tool": block.name, "success": success})
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": result_text}
                )
            running.append({"role": "user", "content": tool_results})
        else:
            # Loop exhausted MAX_AGENTIC_TURNS without the model ever
            # stopping on its own (every other exit path above returns
            # directly, which skips this for/else clause).
            await queue.put({
                "type": "error",
                "message": f"Stopped after {MAX_AGENTIC_TURNS} tool-call turns without finishing — this looks like a loop.",
            })


class OpenAIProvider(BaseLLMProvider):
    def _tool_schema(self, tool: mcp_types.Tool) -> dict:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.inputSchema,
            },
        }

    async def run(self, initial_messages, model, tools, queue, call_mcp_tool, system_prompt=SYSTEM_PROMPT):
        from openai import AsyncOpenAI

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            await queue.put({"type": "error", "message": "OPENAI_API_KEY is not configured."})
            return

        client = AsyncOpenAI(api_key=api_key)
        # OpenAI takes system as a message, not a separate parameter
        running = [{"role": "system", "content": system_prompt}]
        running += [{"role": m["role"], "content": m["content"]} for m in initial_messages]
        tool_schemas = [self._tool_schema(t) for t in tools]

        for _turn in range(MAX_AGENTIC_TURNS):
            tc_acc: dict[int, dict] = {}
            full_text = ""
            finish_reason = None

            stream = await client.chat.completions.create(
                model=model,
                messages=running,
                tools=tool_schemas,
                stream=True,
            )

            async for chunk in stream:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta

                if delta.content:
                    full_text += delta.content
                    await queue.put({"type": "text", "content": delta.content})

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tc_acc:
                            tc_acc[idx] = {"id": "", "name": "", "arguments": ""}
                        if tc.id:
                            tc_acc[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name and not tc_acc[idx]["name"]:
                                tc_acc[idx]["name"] = tc.function.name
                                await queue.put({"type": "tool_call", "tool": tc.function.name})
                            if tc.function.arguments:
                                tc_acc[idx]["arguments"] += tc.function.arguments

                if choice.finish_reason:
                    finish_reason = choice.finish_reason

            if not tc_acc or finish_reason == "stop":
                await queue.put({"type": "done"})
                return

            assistant_msg: dict = {"role": "assistant", "content": full_text or None}
            assistant_msg["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                }
                for tc in tc_acc.values()
            ]
            running.append(assistant_msg)

            for tc in tc_acc.values():
                try:
                    parsed = json.loads(tc["arguments"] or "{}")
                except json.JSONDecodeError:
                    parsed = {}
                result_text, success = await call_mcp_tool(tc["name"], parsed)
                await queue.put({"type": "tool_result", "tool": tc["name"], "success": success})
                running.append({"role": "tool", "tool_call_id": tc["id"], "content": result_text})
        else:
            await queue.put({
                "type": "error",
                "message": f"Stopped after {MAX_AGENTIC_TURNS} tool-call turns without finishing — this looks like a loop.",
            })


class GeminiProvider(BaseLLMProvider):
    def _convert_property(self, prop: dict):
        import google.generativeai as genai

        type_map = {
            "string": genai.protos.Type.STRING,
            "integer": genai.protos.Type.INTEGER,
            "number": genai.protos.Type.NUMBER,
            "boolean": genai.protos.Type.BOOLEAN,
            "array": genai.protos.Type.ARRAY,
            "object": genai.protos.Type.OBJECT,
        }
        return genai.protos.Schema(
            type_=type_map.get(prop.get("type", "string"), genai.protos.Type.STRING),
            description=prop.get("description", ""),
        )

    def _to_gemini_schema(self, schema: dict):
        import google.generativeai as genai

        props = {k: self._convert_property(v) for k, v in (schema.get("properties") or {}).items()}
        return genai.protos.Schema(
            type_=genai.protos.Type.OBJECT,
            properties=props,
            required=schema.get("required", []),
        )

    def _tool_schema(self, tool: mcp_types.Tool):
        import google.generativeai as genai

        schema = tool.inputSchema or {}
        return genai.protos.FunctionDeclaration(
            name=tool.name,
            description=tool.description or "",
            parameters=self._to_gemini_schema(schema) if schema.get("properties") else None,
        )

    async def run(self, initial_messages, model, tools, queue, call_mcp_tool, system_prompt=SYSTEM_PROMPT):
        import google.generativeai as genai

        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            await queue.put({"type": "error", "message": "GOOGLE_API_KEY is not configured."})
            return

        genai.configure(api_key=api_key)

        gemini_tools = [genai.protos.Tool(function_declarations=[self._tool_schema(t) for t in tools])]
        model_client = genai.GenerativeModel(
            model_name=model,
            tools=gemini_tools,
            system_instruction=system_prompt,
        )

        # Build history from prior turns (all but the last message)
        history = []
        for msg in initial_messages[:-1]:
            history.append({"role": "user" if msg["role"] == "user" else "model", "parts": [msg["content"]]})

        chat = model_client.start_chat(history=history)
        current_message = initial_messages[-1]["content"] if initial_messages else ""

        for _turn in range(MAX_AGENTIC_TURNS):
            function_calls: list[dict] = []

            try:
                response = await chat.send_message_async(current_message, stream=True)
                async for chunk in response:
                    try:
                        if chunk.text:
                            await queue.put({"type": "text", "content": chunk.text})
                    except (ValueError, AttributeError):
                        pass

                    try:
                        for candidate in chunk.candidates or []:
                            for part in candidate.content.parts or []:
                                if hasattr(part, "function_call") and part.function_call.name:
                                    fc = part.function_call
                                    function_calls.append({"name": fc.name, "args": dict(fc.args) if fc.args else {}})
                                    await queue.put({"type": "tool_call", "tool": fc.name})
                    except (AttributeError, ValueError):
                        pass

            except Exception as exc:
                await queue.put({"type": "error", "message": f"Gemini error: {exc}"})
                return

            if not function_calls:
                await queue.put({"type": "done"})
                return

            tool_response_parts = []
            for fc in function_calls:
                result_text, success = await call_mcp_tool(fc["name"], fc["args"])
                await queue.put({"type": "tool_result", "tool": fc["name"], "success": success})
                try:
                    result_json = json.loads(result_text)
                except json.JSONDecodeError:
                    result_json = {"result": result_text}
                tool_response_parts.append(
                    genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=fc["name"],
                            response=result_json,
                        )
                    )
                )

            current_message = tool_response_parts
        else:
            await queue.put({
                "type": "error",
                "message": f"Stopped after {MAX_AGENTIC_TURNS} tool-call turns without finishing — this looks like a loop.",
            })


# provider key (from MODELS/PROVIDERS) → implementation. Defined here, after
# the provider classes, so it can reference them.
_PROVIDER_CLASSES: dict[str, type[BaseLLMProvider]] = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "google": GeminiProvider,
}

_MODEL_PROVIDER: dict[str, str] = {m["id"]: m["provider"] for m in MODELS}


def _get_provider(model: str) -> BaseLLMProvider:
    """Resolve a model id to its provider implementation via the MODELS catalog
    (R1.5d) — no name-prefix guessing. Unknown ids fall back to Anthropic, the
    default provider (DEFAULT_MODEL is a Claude model)."""
    provider = _MODEL_PROVIDER.get(model, "anthropic")
    return _PROVIDER_CLASSES[provider]()


async def _load_context_resources(group) -> str:
    """Read rotation and deals resources from the MCP server and format them as a system-prompt addition."""
    try:
        if not group.sessions:
            return ""
        session = group.sessions[0]
        from pydantic import AnyUrl

        rotation_result = await session.read_resource(AnyUrl("shoes://rotation"))
        rotation_text = "\n".join(c.text for c in rotation_result.contents if hasattr(c, "text"))

        deals_result = await session.read_resource(AnyUrl("shoes://deals/active"))
        deals_text = "\n".join(c.text for c in deals_result.contents if hasattr(c, "text"))

        return (
            "\n\n## Live Context (loaded at conversation start)\n\n"
            f"### My Shoe Rotation\n{rotation_text}\n\n"
            f"### Active Deals\n{deals_text}\n"
        )
    except Exception:
        return ""  # fail silently — tools are still available as a fallback


async def read_mcp_resource(uri: str) -> str:
    """Open a brief MCP session, read one resource by URI, and return its text content."""
    from pydantic import AnyUrl

    async with ClientSessionGroup() as group:
        for server in MCP_SERVERS:
            url = server.get("url", "")
            if not url:
                continue
            try:
                await group.connect_to_server(
                    StreamableHttpParameters(
                        url=url,
                        headers=_server_headers(server),
                        timeout=timedelta(seconds=10),
                        sse_read_timeout=timedelta(seconds=30),
                    )
                )
            except Exception:
                continue

        if not group.sessions:
            raise RuntimeError("No MCP server available")

        result = await group.sessions[0].read_resource(AnyUrl(uri))
        return "\n".join(c.text for c in result.contents if hasattr(c, "text"))


async def _run_chat(messages: list, model: str, queue: asyncio.Queue) -> None:
    """
    Runs the provider agentic loop in an isolated asyncio Task.

    ClientSessionGroup's anyio cancel scopes are confined to this task,
    preventing cancel-scope ordering conflicts at the SSE generator boundary.
    """
    provider = _get_provider(model)

    try:
        async with ClientSessionGroup() as group:
            for server in MCP_SERVERS:
                url = server.get("url", "")
                if not url:
                    continue
                try:
                    await group.connect_to_server(
                        StreamableHttpParameters(
                            url=url,
                            headers=_server_headers(server),
                            timeout=timedelta(seconds=10),
                            sse_read_timeout=timedelta(seconds=300),
                        )
                    )
                except Exception as exc:
                    print(f"[chat] MCP server '{server['name']}' unavailable: {exc}")

            if not group.tools:
                await queue.put({"type": "error", "message": "No tools available from any MCP server."})
                return

            tools = list(group.tools.values())

            async def call_mcp_tool(name: str, tool_input: dict) -> tuple[str, bool]:
                try:
                    result = await group.call_tool(name, tool_input)
                    return _extract_result_text(result), not result.isError
                except Exception as exc:
                    return json.dumps({"error": str(exc)}), False

            context_addition = await _load_context_resources(group)
            augmented_system_prompt = SYSTEM_PROMPT + context_addition

            await provider.run(
                initial_messages=messages,
                model=model,
                tools=tools,
                queue=queue,
                call_mcp_tool=call_mcp_tool,
                system_prompt=augmented_system_prompt,
            )

    except Exception as exc:
        await queue.put({"type": "error", "message": str(exc)})
    finally:
        await queue.put(None)


async def stream_chat(messages: list, model: str) -> AsyncGenerator:
    """
    Async generator that streams an LLM response as SSE event dicts.

    Spawns _run_chat in a separate asyncio Task so that ClientSessionGroup's
    anyio cancel scopes are confined to that task and never cross the SSE
    generator boundary.

    Sequence of yielded events:
      {"type": "tool_call",   "tool": "get_owned_shoes"}
      {"type": "tool_result", "tool": "get_owned_shoes", "success": True}
      {"type": "text",        "content": "token…"}
      {"type": "done"}
      {"type": "error",       "message": "…"}
    """
    queue: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(_run_chat(messages, model, queue))
    try:
        while True:
            event = await queue.get()
            if event is None:
                break
            yield event
    finally:
        if not task.done():
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

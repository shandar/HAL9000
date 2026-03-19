"""
HAL9000 — Brain
Multi-provider AI backend with function calling (tool use).
Supports OpenAI, Anthropic, and Gemini.

The think() loop:
  1. Send user message + tool definitions to the LLM
  2. If LLM returns tool calls → execute them → feed results back
  3. Repeat until LLM gives a text response or max iterations hit
"""

import json
import threading
from typing import Optional

from config import cfg
from core import tools
from core.memory_store import get_store


# ── Base ─────────────────────────────────────────────────

class BaseBrain:
    """Common interface for all brain providers."""

    def __init__(self, knowledge_context: str = ""):
        self.history: list[dict] = []
        self._history_lock = threading.Lock()
        self._thinking_lock = threading.Lock()  # prevents concurrent think() calls
        self._knowledge_context = knowledge_context
        # Build static parts once; memory is refreshed on each _get_system_prompt()
        base_prompt = cfg.SYSTEM_PROMPT
        if cfg.DEMO_MODE:
            base_prompt += cfg.DEMO_PROMPT
        self._static_prompt_parts = [base_prompt]

        if knowledge_context:
            self._static_prompt_parts.append(
                "--- YOUR KNOWLEDGE BASE ---\n"
                "The following is information you have been given. "
                "Use it to answer questions accurately. "
                "If asked about something not in your knowledge, say so.\n\n"
                + knowledge_context
            )

        self._static_prompt_parts.append(
            "--- TOOLS ---\n"
            "You have access to tools that let you control the user's computer, "
            "run commands, manage files, search the web, and remember things. "
            "Use them when the user asks you to do something or when you need information. "
            "Keep responses concise — under 3 sentences for voice output unless the user asks for detail. "
            "For destructive or sensitive operations, always confirm with the user first."
        )

    @property
    def system_prompt(self) -> str:
        """Build system prompt with fresh memory on every access."""
        parts = list(self._static_prompt_parts)

        # Load current persistent memory (refreshed, not stale)
        store = get_store()
        all_memories = store.list_all()
        if all_memories:
            by_type: dict[str, list[str]] = {}
            for m in all_memories:
                if m.type == "session_summary":
                    continue
                by_type.setdefault(m.type, []).append(m.content)

            memory_lines = []
            for mtype, items in by_type.items():
                memory_lines.append(f"[{mtype}s]")
                for item in items:
                    memory_lines.append(f"  - {item}")

            if memory_lines:
                parts.append(
                    "--- YOUR PERSISTENT MEMORY ---\n"
                    "These are facts, decisions, and preferences you've stored:\n\n"
                    + "\n".join(memory_lines)
                )

        # Recent session summaries (limit 3)
        summaries = store.get_session_summaries(limit=3)
        if summaries:
            summary_lines = [f"- {s.content}" for s in summaries]
            parts.append(
                "--- RECENT SESSIONS ---\n"
                "Context from your recent sessions:\n\n"
                + "\n".join(summary_lines)
            )

        # Always-loaded knowledge uploads
        try:
            from core.knowledge import load_always_files
            always_knowledge = load_always_files()
            if always_knowledge:
                parts.append(
                    "--- UPLOADED KNOWLEDGE (always loaded) ---\n"
                    + always_knowledge
                )
        except Exception:
            pass

        return "\n\n".join(parts)

    def _error_msg(self, detail: str) -> str:
        """Generate a HAL-style error message."""
        return f"I seem to be having a small problem. {detail}"

    def think(self, user_text: str, frame_b64: Optional[str] = None) -> str:
        raise NotImplementedError

    def think_stream(self, user_text: str, frame_b64: Optional[str] = None):
        """Generator that yields tokens as they arrive. Override in subclass.
        Yields dicts: {"type": "token", "text": "..."} or {"type": "tool", "name": "...", "result": "..."}
        Final yield: {"type": "done", "text": "full reply"}
        Falls back to non-streaming think() if not overridden."""
        reply = self.think(user_text, frame_b64)
        yield {"type": "done", "text": reply}

    def reset(self):
        with self._history_lock:
            self.history = []
        print("[HAL Brain] Memory cleared.")

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimate: ~4 chars per token for English."""
        if not text:
            return 0
        return max(1, len(text) // 4)

    def _message_tokens(self, msg: dict) -> int:
        """Estimate tokens in a single history message."""
        content = msg.get("content", "")
        if isinstance(content, str):
            return self._estimate_tokens(content)
        elif isinstance(content, list):
            # Anthropic-style content blocks or tool results
            total = 0
            for block in content:
                if isinstance(block, dict):
                    total += self._estimate_tokens(
                        block.get("text", "")
                        or block.get("content", "")
                        or json.dumps(block)
                    )
                else:
                    # Anthropic SDK objects (TextBlock, ToolUseBlock, etc.)
                    total += self._estimate_tokens(str(block))
            return total
        return self._estimate_tokens(str(content))

    def _compress_tool_results(self):
        """Truncate verbose tool results in older history entries."""
        max_chars = cfg.TOOL_RESULT_MAX_CHARS
        with self._history_lock:
            # Only compress older messages (keep last 4 intact for context)
            cutoff = max(0, len(self.history) - 4)
            for i in range(cutoff):
                msg = self.history[i]
                role = msg.get("role", "")
                content = msg.get("content", "")

                # OpenAI tool results
                if role == "tool" and isinstance(content, str) and len(content) > max_chars:
                    try:
                        parsed = json.loads(content)
                        if "result" in parsed:
                            parsed["result"] = parsed["result"][:max_chars] + "...(truncated)"
                            self.history[i]["content"] = json.dumps(parsed)
                    except (json.JSONDecodeError, TypeError):
                        pass

                # Anthropic tool_result blocks
                if role == "user" and isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_result":
                            c = block.get("content", "")
                            if isinstance(c, str) and len(c) > max_chars:
                                try:
                                    parsed = json.loads(c)
                                    if "result" in parsed:
                                        parsed["result"] = parsed["result"][:max_chars] + "...(truncated)"
                                        block["content"] = json.dumps(parsed)
                                except (json.JSONDecodeError, TypeError):
                                    block["content"] = c[:max_chars] + "...(truncated)"

    def _trim_history(self):
        """Token-aware history trimming with tool output compression."""
        # First compress verbose tool outputs
        self._compress_tool_results()

        max_tokens = cfg.CONTEXT_MAX_TOKENS
        with self._history_lock:
            # Calculate total tokens
            total = sum(self._message_tokens(m) for m in self.history)

            if total <= max_tokens:
                return

            # Drop oldest messages until under budget
            # Always keep at least the last 2 messages (current exchange)
            while len(self.history) > 2 and total > max_tokens:
                dropped = self.history.pop(0)
                total -= self._message_tokens(dropped)

            print(f"[HAL Brain] Trimmed history to {len(self.history)} messages (~{total} tokens)")

    def _repair_history(self):
        """Remove orphaned tool_calls that don't have matching tool responses.
        This prevents the '400: tool_calls must be followed by tool messages' error."""
        with self._history_lock:
            if not self.history:
                return

            # Walk backwards — find the last assistant message with tool_calls
            # and check if all tool_call_ids have matching tool responses
            repaired = False
            i = len(self.history) - 1
            while i >= 0:
                msg = self.history[i]
                if msg.get("role") == "assistant" and msg.get("tool_calls"):
                    # Check if every tool_call_id has a matching tool response after it
                    tc_ids = {tc["id"] for tc in msg["tool_calls"]}
                    responded = set()
                    for j in range(i + 1, len(self.history)):
                        if self.history[j].get("role") == "tool":
                            responded.add(self.history[j].get("tool_call_id", ""))
                    orphaned = tc_ids - responded
                    if orphaned:
                        # Remove this assistant msg and any partial tool responses
                        self.history = self.history[:i]
                        repaired = True
                        print(f"[HAL Brain] Repaired history: removed orphaned tool_calls at index {i}")
                        break
                i -= 1

            if not repaired:
                # Fallback: if last message is assistant with tool_calls, just remove it
                if self.history and self.history[-1].get("role") == "assistant" and self.history[-1].get("tool_calls"):
                    self.history.pop()
                    print("[HAL Brain] Repaired history: removed trailing tool_calls message")

    def _log_tool_call(self, name: str, args: dict, result: dict):
        status = "OK" if "result" in result else "ERROR"
        print(f"[HAL Tool] {name}({json.dumps(args, ensure_ascii=False)[:100]}) → {status}")


# ── OpenAI (GPT-4o) ─────────────────────────────────────

class OpenAIBrain(BaseBrain):

    def __init__(self, knowledge_context: str = ""):
        super().__init__(knowledge_context)
        from openai import OpenAI
        self.client = OpenAI(api_key=cfg.OPENAI_API_KEY)
        self._tools = tools.to_openai_tools()
        print(f"[HAL Brain] OpenAI provider ready ({cfg.OPENAI_MODEL}, {len(self._tools)} tools)")

    def think(self, user_text: str, frame_b64: Optional[str] = None) -> str:
        # Prevent concurrent think() calls — a second message while a tool
        # call is running would corrupt the history sequence
        if not self._thinking_lock.acquire(timeout=0.1):
            return "I'm still processing your previous request. One moment."

        try:
            return self._think_impl(user_text, frame_b64)
        finally:
            self._thinking_lock.release()

    def _think_impl(self, user_text: str, frame_b64: Optional[str] = None) -> str:
        content = self._build_content(user_text, frame_b64)
        self.history.append({"role": "user", "content": content})
        self._trim_history()

        max_iters = cfg.TOOL_MAX_ITERATIONS

        try:
            for _ in range(max_iters):
                messages = [{"role": "system", "content": self.system_prompt}]
                messages.extend(self.history)

                response = self.client.chat.completions.create(
                    model=cfg.OPENAI_MODEL,
                    max_tokens=cfg.MAX_TOKENS,
                    messages=messages,
                    tools=self._tools if self._tools else None,
                )

                choice = response.choices[0]

                # If no tool calls, we have the final answer
                if choice.finish_reason != "tool_calls" or not choice.message.tool_calls:
                    reply = choice.message.content or ""
                    self.history.append({"role": "assistant", "content": reply})
                    print(f"[HAL] {reply}")
                    return reply

                # Process tool calls
                assistant_msg = {
                    "role": "assistant",
                    "content": choice.message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in choice.message.tool_calls
                    ],
                }
                self.history.append(assistant_msg)

                # Execute tool calls in parallel when multiple are requested
                from concurrent.futures import ThreadPoolExecutor

                def _run_tool(tc):
                    name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {}
                    result = tools.execute(name, args)
                    self._log_tool_call(name, args, result)
                    return tc.id, result

                with ThreadPoolExecutor(max_workers=4) as pool:
                    results = list(pool.map(_run_tool, choice.message.tool_calls))

                for tc_id, result in results:
                    self.history.append({
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": json.dumps(result),
                    })

            # Max iterations reached
            reply = "I've reached my tool call limit for this turn. Let me summarize what I found."
            self.history.append({"role": "assistant", "content": reply})
            return reply

        except Exception as e:
            err = f"I seem to be having a small problem. Error: {e}"
            print(f"[HAL Brain] OpenAI error: {e}")
            # Clean up corrupted history — remove orphaned tool_calls + tool responses
            self._repair_history()
            return err

    def think_stream(self, user_text: str, frame_b64: Optional[str] = None):
        """Streaming version — yields tokens as they arrive from OpenAI."""
        if not self._thinking_lock.acquire(timeout=0.1):
            yield {"type": "done", "text": "I'm still processing your previous request. One moment."}
            return

        try:
            yield from self._think_stream_impl(user_text, frame_b64)
        finally:
            self._thinking_lock.release()

    def _think_stream_impl(self, user_text: str, frame_b64: Optional[str] = None):
        content = self._build_content(user_text, frame_b64)
        self.history.append({"role": "user", "content": content})
        self._trim_history()

        max_iters = cfg.TOOL_MAX_ITERATIONS

        try:
            for _ in range(max_iters):
                messages = [{"role": "system", "content": self.system_prompt}]
                messages.extend(self.history)

                # Streaming API call
                stream = self.client.chat.completions.create(
                    model=cfg.OPENAI_MODEL,
                    max_tokens=cfg.MAX_TOKENS,
                    messages=messages,
                    tools=self._tools if self._tools else None,
                    stream=True,
                )

                # Collect streamed response
                full_text = ""
                tool_calls_data = {}  # id -> {name, arguments}
                finish_reason = None

                for chunk in stream:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if not delta:
                        continue

                    finish_reason = chunk.choices[0].finish_reason

                    # Text content token
                    if delta.content:
                        full_text += delta.content
                        yield {"type": "token", "text": delta.content}

                    # Tool call chunks (streamed incrementally)
                    if delta.tool_calls:
                        for tc_chunk in delta.tool_calls:
                            idx = tc_chunk.index
                            if idx not in tool_calls_data:
                                tool_calls_data[idx] = {
                                    "id": tc_chunk.id or "",
                                    "name": "",
                                    "arguments": "",
                                }
                            if tc_chunk.id:
                                tool_calls_data[idx]["id"] = tc_chunk.id
                            if tc_chunk.function:
                                if tc_chunk.function.name:
                                    tool_calls_data[idx]["name"] = tc_chunk.function.name
                                if tc_chunk.function.arguments:
                                    tool_calls_data[idx]["arguments"] += tc_chunk.function.arguments

                # If no tool calls, we're done
                if finish_reason != "tool_calls" or not tool_calls_data:
                    self.history.append({"role": "assistant", "content": full_text})
                    print(f"[HAL] {full_text}")
                    yield {"type": "done", "text": full_text}
                    return

                # Process tool calls
                tc_list = sorted(tool_calls_data.values(), key=lambda x: x.get("id", ""))
                assistant_msg = {
                    "role": "assistant",
                    "content": full_text or None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": tc["arguments"],
                            },
                        }
                        for tc in tc_list
                    ],
                }
                self.history.append(assistant_msg)

                for tc in tc_list:
                    name = tc["name"]
                    try:
                        args = json.loads(tc["arguments"])
                    except json.JSONDecodeError:
                        args = {}
                    result = tools.execute(name, args)
                    self._log_tool_call(name, args, result)

                    yield {"type": "tool", "name": name, "result": result}

                    self.history.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(result),
                    })

            # Max iterations
            reply = "I've reached my tool call limit for this turn."
            self.history.append({"role": "assistant", "content": reply})
            yield {"type": "done", "text": reply}

        except Exception as e:
            err = f"I seem to be having a small problem. Error: {e}"
            print(f"[HAL Brain] OpenAI streaming error: {e}")
            self._repair_history()
            yield {"type": "done", "text": err}

    def _build_content(self, text: str, frame_b64: Optional[str]):
        if frame_b64:
            return [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{frame_b64}",
                        "detail": "low",
                    },
                },
                {"type": "text", "text": text},
            ]
        return text


# ── Anthropic (Claude) ───────────────────────────────────

class AnthropicBrain(BaseBrain):

    def __init__(self, knowledge_context: str = ""):
        super().__init__(knowledge_context)
        import anthropic
        self.client = anthropic.Anthropic(api_key=cfg.ANTHROPIC_API_KEY)
        self._anthropic = anthropic
        self._tools = tools.to_anthropic_tools()
        print(f"[HAL Brain] Anthropic provider ready ({cfg.ANTHROPIC_MODEL}, {len(self._tools)} tools)")

    def think(self, user_text: str, frame_b64: Optional[str] = None) -> str:
        if not self._thinking_lock.acquire(timeout=0.1):
            return "I'm still processing your previous request. One moment."
        try:
            return self._think_impl(user_text, frame_b64)
        finally:
            self._thinking_lock.release()

    def _think_impl(self, user_text: str, frame_b64: Optional[str] = None) -> str:
        content = self._build_content(user_text, frame_b64)
        self.history.append({"role": "user", "content": content})
        self._trim_history()

        max_iters = cfg.TOOL_MAX_ITERATIONS

        try:
            for _ in range(max_iters):
                response = self.client.messages.create(
                    model=cfg.ANTHROPIC_MODEL,
                    max_tokens=cfg.MAX_TOKENS,
                    system=self.system_prompt,
                    messages=self.history,
                    tools=self._tools if self._tools else None,
                )

                # Check if response contains tool use
                tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
                text_blocks = [b for b in response.content if b.type == "text"]

                if not tool_use_blocks:
                    # Pure text response
                    reply = text_blocks[0].text if text_blocks else ""
                    self.history.append({"role": "assistant", "content": response.content})
                    print(f"[HAL] {reply}")
                    return reply

                # Has tool calls — add assistant message then tool results
                self.history.append({"role": "assistant", "content": response.content})

                tool_results = []
                for block in tool_use_blocks:
                    name = block.name
                    args = block.input
                    result = tools.execute(name, args)
                    self._log_tool_call(name, args, result)

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    })

                self.history.append({"role": "user", "content": tool_results})

            reply = "I've reached my tool call limit for this turn."
            self.history.append({"role": "assistant", "content": [{"type": "text", "text": reply}]})
            return reply

        except Exception as e:
            err = f"I seem to be having a small problem. Error: {e}"
            print(f"[HAL Brain] Anthropic error: {e}")
            self._repair_history()
            return err

    def _build_content(self, text: str, frame_b64: Optional[str]) -> list[dict]:
        if frame_b64:
            return [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": frame_b64,
                    },
                },
                {"type": "text", "text": text},
            ]
        return [{"type": "text", "text": text}]


# ── Gemini ───────────────────────────────────────────────

class GeminiBrain(BaseBrain):

    def __init__(self, knowledge_context: str = ""):
        super().__init__(knowledge_context)
        from google import genai
        self.client = genai.Client(api_key=cfg.GEMINI_API_KEY)
        self._genai = genai
        self._tools_config = tools.to_gemini_tools()
        print(f"[HAL Brain] Gemini provider ready ({cfg.GEMINI_MODEL}, tools enabled)")

    def think(self, user_text: str, frame_b64: Optional[str] = None) -> str:
        if not self._thinking_lock.acquire(timeout=0.1):
            return "I'm still processing your previous request. One moment."
        try:
            return self._think_impl_gemini(user_text, frame_b64)
        finally:
            self._thinking_lock.release()

    def _think_impl_gemini(self, user_text: str, frame_b64: Optional[str] = None) -> str:
        contents = self._build_contents(user_text, frame_b64)

        max_iters = cfg.TOOL_MAX_ITERATIONS

        try:
            for _ in range(max_iters):
                response = self.client.models.generate_content(
                    model=cfg.GEMINI_MODEL,
                    contents=contents,
                    config=self._genai.types.GenerateContentConfig(
                        system_instruction=self.system_prompt,
                        max_output_tokens=cfg.MAX_TOKENS,
                        tools=self._tools_config,
                    ),
                )

                # Check for function calls
                has_function_call = False
                if response.candidates and response.candidates[0].content:
                    for part in response.candidates[0].content.parts:
                        if hasattr(part, "function_call") and part.function_call:
                            has_function_call = True
                            break

                if not has_function_call:
                    reply = response.text or ""
                    self.history.append({"role": "user", "text": user_text})
                    self.history.append({"role": "assistant", "text": reply})
                    print(f"[HAL] {reply}")
                    return reply

                # Process function calls
                from google.genai import types

                # Add model response to contents
                contents.append(response.candidates[0].content)

                # Execute each function call and build response parts
                function_response_parts = []
                for part in response.candidates[0].content.parts:
                    if hasattr(part, "function_call") and part.function_call:
                        fc = part.function_call
                        name = fc.name
                        args = dict(fc.args) if fc.args else {}
                        result = tools.execute(name, args)
                        self._log_tool_call(name, args, result)

                        function_response_parts.append(
                            types.Part.from_function_response(
                                name=name,
                                response=result,
                            )
                        )

                contents.append(
                    types.Content(role="user", parts=function_response_parts)
                )

            reply = "I've reached my tool call limit for this turn."
            self.history.append({"role": "user", "text": user_text})
            self.history.append({"role": "assistant", "text": reply})
            return reply

        except Exception as e:
            err = f"I seem to be having a small problem. Error: {e}"
            print(f"[HAL Brain] Gemini error: {e}")
            self._repair_history()
            return err

    def _build_contents(self, text: str, frame_b64: Optional[str]):
        """Build Gemini contents array including conversation history."""
        import base64
        from google.genai import types

        contents = []

        # Add conversation history
        for entry in self.history:
            role = "user" if entry["role"] == "user" else "model"
            contents.append(types.Content(
                role=role,
                parts=[types.Part.from_text(text=entry["text"])],
            ))

        # Build current message parts
        parts = []
        if frame_b64:
            image_bytes = base64.standard_b64decode(frame_b64)
            parts.append(types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"))
        parts.append(types.Part.from_text(text=text))

        contents.append(types.Content(role="user", parts=parts))
        return contents


# ── Ollama (local, free) ────────────────────────────────

class OllamaBrain(BaseBrain):
    """Local LLM via Ollama — no API key required."""

    def __init__(self, knowledge_context: str = ""):
        super().__init__(knowledge_context)
        import ollama as _ollama
        self._ollama = _ollama
        self._client = _ollama.Client(host=cfg.OLLAMA_BASE_URL)
        self._tools = tools.to_openai_tools()  # Ollama uses OpenAI tool format
        self._model = cfg.OLLAMA_MODEL

        # Verify model is available
        try:
            models = self._client.list()
            available = [m.model.split(":")[0] for m in models.models]
            base_name = self._model.split(":")[0]
            if base_name not in available:
                print(f"[HAL Brain] WARNING: Model '{self._model}' not found locally.")
                print(f"[HAL Brain] Available: {', '.join(available)}")
                print(f"[HAL Brain] Run: ollama pull {self._model}")
        except Exception as e:
            print(f"[HAL Brain] WARNING: Could not connect to Ollama at {cfg.OLLAMA_BASE_URL}: {e}")
            print(f"[HAL Brain] Make sure Ollama is running: ollama serve")

        print(f"[HAL Brain] Ollama provider ready ({self._model}, {len(self._tools)} tools, FREE)")

    def think(self, user_text: str, frame_b64: Optional[str] = None) -> str:
        # Ollama vision support depends on model — skip frame for non-vision models
        content = user_text
        if frame_b64 and self._model_supports_vision():
            content = self._build_content(user_text, frame_b64)

        self.history.append({"role": "user", "content": content})
        self._trim_history()

        max_iters = cfg.TOOL_MAX_ITERATIONS

        try:
            for _ in range(max_iters):
                messages = [{"role": "system", "content": self.system_prompt}]
                messages.extend(self.history)

                response = self._client.chat(
                    model=self._model,
                    messages=messages,
                    tools=self._tools if self._tools else None,
                )

                msg = response.message

                # If no tool calls, return text
                if not msg.tool_calls:
                    reply = msg.content or ""
                    self.history.append({"role": "assistant", "content": reply})
                    print(f"[HAL] {reply}")
                    return reply

                # Process tool calls
                assistant_msg = {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": f"call_{i}",
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": json.dumps(tc.function.arguments)
                                    if isinstance(tc.function.arguments, dict)
                                    else tc.function.arguments,
                            },
                        }
                        for i, tc in enumerate(msg.tool_calls)
                    ],
                }
                self.history.append(assistant_msg)

                for i, tc in enumerate(msg.tool_calls):
                    name = tc.function.name
                    args = tc.function.arguments if isinstance(tc.function.arguments, dict) else {}
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}

                    result = tools.execute(name, args)
                    self._log_tool_call(name, args, result)

                    self.history.append({
                        "role": "tool",
                        "content": json.dumps(result),
                    })

            reply = "I've reached my tool call limit for this turn."
            self.history.append({"role": "assistant", "content": reply})
            return reply

        except Exception as e:
            err_msg = str(e)
            if "connection" in err_msg.lower() or "refused" in err_msg.lower():
                return "I cannot reach Ollama. Please ensure it is running: ollama serve"
            err = f"I seem to be having a small problem. Error: {e}"
            print(f"[HAL Brain] Ollama error: {e}")
            self._repair_history()
            return err

    def _model_supports_vision(self) -> bool:
        """Check if the current model supports vision/images."""
        vision_models = {"llava", "bakllava", "moondream", "llava-llama3"}
        base = self._model.split(":")[0].lower()
        return base in vision_models

    def _build_content(self, text: str, frame_b64: Optional[str]):
        """Build content with image for vision-capable models."""
        if frame_b64:
            return [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{frame_b64}"}},
                {"type": "text", "text": text},
            ]
        return text


# ── Factory ──────────────────────────────────────────────

def create_brain(knowledge_context: str = "") -> BaseBrain:
    """Create the brain for the configured AI_PROVIDER."""
    provider = cfg.AI_PROVIDER.lower()

    if provider == "openai":
        return OpenAIBrain(knowledge_context)
    elif provider == "anthropic":
        return AnthropicBrain(knowledge_context)
    elif provider == "gemini":
        return GeminiBrain(knowledge_context)
    elif provider == "ollama":
        return OllamaBrain(knowledge_context)
    else:
        raise ValueError(
            f"Unknown AI_PROVIDER: '{provider}'. "
            f"Use 'openai', 'anthropic', 'gemini', or 'ollama'."
        )

"""DeepSeek calls for the pipeline stages (roadmap steps 11-17).

One place for the model and the client, and the three call shapes the stages need: `complete`
for text, `extract` for a typed (pydantic) result, and `extract_streaming` for a typed result
whose list items are handed over one by one while the model is still writing (the live
progression of design-doc D7). Every request streams, so a whole document in the prompt never
hits an HTTP timeout, and every result comes back with its token usage so a stage can report
what it cost.

The client is the Anthropic SDK pointed at **DeepSeek's Anthropic-compatible endpoint**
(`https://api.deepseek.com/anthropic`), so the message shapes, streaming and tool protocol are
the ones the SDK already speaks. The compatibility layer does not carry all of it, and what it
drops is not documented, so it was measured. What holds and what does not:

* streaming, `system`, `thinking`, and **client-side tools** (`tool_use` -> `tool_result`) all
  work, including across several turns.
* `web_search_20250305` works and stays a **server** tool: the search runs at DeepSeek's end
  and the results arrive as `web_search_tool_result` blocks.
* `web_fetch_20250910` is **rejected** ("unknown variant"), so fetching a page is a *local*
  tool: the model asks for a URL, `auditor.ingest` fetches it here, and the readable text goes
  back as a `tool_result`. `_run_tool` is the only place in this file that touches the network
  on its own account.
* **Structured outputs are not carried.** `output_format=<model>` comes back with no
  `parsed_output` and no text at all, which would break every typed stage. So a typed call
  sends the model's JSON Schema in the prompt and validates the reply here; `extract_streaming`
  scans the text as it arrives exactly as before, because it always parsed raw text.
* `output_config.effort` and `cache_control` are accepted and ignored. The `effort` argument is
  kept because ten stages pass it and it is meaningful again the moment this points back at
  Anthropic; DeepSeek caches context automatically, so `cache=True` costs nothing either way.

Defaults, and the environment variables that change them (read from the environment and from
`backend/.env`):

    DEEPSEEK_API_KEY    the key (ANTHROPIC_API_KEY is still read, so an existing .env works)
    DEEPSEEK_BASE_URL   https://api.deepseek.com/anthropic (or ANTHROPIC_BASE_URL)
    AUDITOR_MODEL       deepseek-flash
    AUDITOR_EFFORT      high (low | medium | high | xhigh | max) - carried, ignored by DeepSeek
    AUDITOR_OUTPUT_HEADROOM  3 - how much room the reasoning gets on top of a stage's budget

Check the setup with `python -m auditor.llm check`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

import anthropic
import httpx2 as httpx  # the SDK's HTTP library; its transport errors escape from inside a stream
from pydantic import BaseModel, ValidationError

DEFAULT_MODEL = "deepseek-flash"
DEFAULT_BASE_URL = "https://api.deepseek.com/anthropic"
DEFAULT_EFFORT = "high"
EFFORTS = ("low", "medium", "high", "xhigh", "max")
DEFAULT_MAX_TOKENS = 8000
ENV_FILE = Path(__file__).resolve().parents[1] / ".env"

# DeepSeek reasons on every request whether or not `thinking` is sent, and the reasoning is
# charged to `max_tokens` alongside the answer. Measured on the substantiation match call for a
# three-claim page: 1,408 tokens of answer and 12,819 of reasoning, against a 12,000 cap tuned
# when the reasoning was not billed to the same budget. So a stage's cap is what its *answer*
# may need and this is the room the thinking gets on top. Set AUDITOR_OUTPUT_HEADROOM=1 when
# pointing back at a provider that does not charge reasoning to the output budget.
OUTPUT_HEADROOM = float(os.environ.get("AUDITOR_OUTPUT_HEADROOM", "3"))
OUTPUT_CEILING = int(os.environ.get("AUDITOR_OUTPUT_CEILING", "64000"))

# A turn that runs the server search can pause; this is how often we send it back to continue.
MAX_PAUSES = 4
# And how many rounds of local tool calls one turn may take before we stop feeding it.
MAX_TOOL_ROUNDS = 12

WEB_SEARCH_TOOL = "web_search_20250305"

# A fetched page comes back into the turn whole, so it is capped. An SEC filing is millions of
# tokens and six of them would bury the request. Enough for the part of a filing a quote comes
# from, not the filing. Counted in characters here because we do the truncating ourselves.
FETCH_CONTENT_TOKENS = int(os.environ.get("AUDITOR_FETCH_CONTENT_TOKENS", "40000"))
FETCH_CONTENT_CHARS = FETCH_CONTENT_TOKENS * 4


def web_tools(*, searches: int = 6, fetches: int = 6) -> list[dict[str, Any]]:
    """The pair external verification (step 14) and self-consistency (step 15) look for evidence
    with. Search is DeepSeek's own server tool and runs at their end; fetch is ours and runs
    here, because the compatibility layer rejects Anthropic's `web_fetch`. `fetches` is the
    budget `_stream` enforces, since a client-side tool has no `max_uses`."""
    return [
        {"type": WEB_SEARCH_TOOL, "name": "web_search", "max_uses": searches},
        {
            "name": "web_fetch",
            "description": (
                "Fetch a web page or PDF by URL and return its readable text, truncated. Use it "
                "to read a page a search returned, so you can quote it exactly."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "The absolute URL to fetch."}},
                "required": ["url"],
            },
            "_max_uses": fetches,
        },
    ]


def output_budget(answer_tokens: int) -> int:
    """What to ask the API for so an answer of `answer_tokens` has room to be reasoned out."""
    return min(int(answer_tokens * OUTPUT_HEADROOM), OUTPUT_CEILING)


T = TypeVar("T", bound=BaseModel)


class LlmError(Exception):
    """A call did not produce a usable result. The message says why in the person's terms."""


def load_env(path: Path = ENV_FILE) -> bool:
    """Read `backend/.env` into the environment without overriding what is already set."""
    if not path.is_file():
        return False
    from dotenv import load_dotenv

    return load_dotenv(path, override=False)


def credentials() -> tuple[str | None, str]:
    """(key, base URL). `DEEPSEEK_*` wins; `ANTHROPIC_*` is still read so an .env written for
    Claude keeps working, and because the SDK's own variable is the one it falls back to."""
    load_env()
    key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    base = os.environ.get("DEEPSEEK_BASE_URL") or os.environ.get("ANTHROPIC_BASE_URL") or DEFAULT_BASE_URL
    return key, base


@dataclass(frozen=True)
class LlmSettings:
    model: str = DEFAULT_MODEL
    effort: str = DEFAULT_EFFORT
    max_tokens: int = DEFAULT_MAX_TOKENS
    timeout: float = 600.0
    max_retries: int = 2
    base_url: str = DEFAULT_BASE_URL

    def __post_init__(self) -> None:
        if self.effort not in EFFORTS:
            raise ValueError(f"effort must be one of {', '.join(EFFORTS)}, not {self.effort!r}")

    @classmethod
    def from_env(cls) -> "LlmSettings":
        _, base_url = credentials()
        values: dict[str, Any] = {"base_url": base_url}
        if model := os.environ.get("AUDITOR_MODEL"):
            values["model"] = model
        if effort := os.environ.get("AUDITOR_EFFORT"):
            values["effort"] = effort.lower()
        if max_tokens := os.environ.get("AUDITOR_MAX_TOKENS"):
            values["max_tokens"] = int(max_tokens)
        return cls(**values)


@dataclass(frozen=True)
class Usage:
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    stop_reason: str | None
    request_id: str | None
    seconds: float

    def describe(self) -> str:
        cached = f" + {self.cache_read_tokens} read from cache" if self.cache_read_tokens else ""
        written = f" + {self.cache_write_tokens} written to cache" if self.cache_write_tokens else ""
        return f"{self.model}: {self.input_tokens} in{cached}{written}, {self.output_tokens} out, {self.seconds:.1f} s"


class JsonArrayElements:
    """Reads a JSON object as it streams and hands over each object that closes inside one of
    the root object's arrays, with the array's key: feed `{"signals": [{...}, {...}], "clarity":
    [{...}]}` in any chunking and get ("signals", "{...}") twice, then ("clarity", "{...}").
    Strings, escapes and nesting inside an element are respected; nothing is parsed until an
    element is complete, so a chunk boundary can fall anywhere. Text before the first `{`, such
    as a code fence, is ignored, because it never opens a brace."""

    def __init__(self) -> None:
        self._depth = 0
        self._in_string = False
        self._escape = False
        self._key: list[str] | None = None  # the string being read at depth 1
        self._last_key: str | None = None
        self._array_key: str | None = None  # the root array we are inside, if any
        self._element: list[str] | None = None  # the element being collected

    def feed(self, chunk: str) -> list[tuple[str, str]]:
        """Feed more text; the elements that closed in it, as (array key, element JSON)."""
        done: list[tuple[str, str]] = []
        for ch in chunk:
            collecting = self._element is not None
            if collecting:
                self._element.append(ch)  # type: ignore[union-attr]
            if self._in_string:
                if self._escape:
                    self._escape = False
                elif ch == "\\":
                    self._escape = True
                elif ch == '"':
                    self._in_string = False
                    if self._key is not None:
                        self._last_key = "".join(self._key)
                        self._key = None
                elif self._key is not None:
                    self._key.append(ch)
                continue
            if ch == '"':
                self._in_string = True
                if self._depth == 1:
                    self._key = []
            elif ch in "{[":
                if ch == "[" and self._depth == 1:
                    self._array_key = self._last_key
                if ch == "{" and self._depth == 2 and self._array_key is not None and not collecting:
                    self._element = ["{"]
                self._depth += 1
            elif ch in "}]":
                self._depth -= 1
                if ch == "}" and self._depth == 2 and self._element is not None and self._array_key is not None:
                    done.append((self._array_key, "".join(self._element)))
                    self._element = None
                elif ch == "]" and self._depth == 1:
                    self._array_key = None
        return done


def json_instruction(output: type[BaseModel]) -> str:
    """What is appended to a typed call's prompt in place of structured outputs. The schema is
    sent whole: naming the fields in prose instead was tried on the extract stage and the model
    invented plausible neighbours for them."""
    schema = json.dumps(output.model_json_schema(), separators=(",", ":"))
    return (
        "\n\nReply with one JSON object and nothing else: no explanation before or after it and "
        "no code fence. Every key it defines must be present. It has to validate against this "
        f"JSON Schema:\n{schema}"
    )


def first_json_object(text: str) -> str | None:
    """The first balanced `{...}` in the reply, ignoring braces inside strings. A model that
    answers with a fence, or with a sentence before the object, still parses."""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def parse_typed(text: str, output: type[T]) -> T:
    """The reply as a validated `output`, or an `LlmError` that says which way it went wrong."""
    blob = first_json_object(text)
    if blob is None:
        raise LlmError(f"The model returned no JSON object for {output.__name__}")
    try:
        data = json.loads(blob)
    except ValueError as exc:
        raise LlmError(f"The model's JSON for {output.__name__} would not parse: {exc}") from exc
    try:
        return output.model_validate(data)
    except ValidationError as exc:
        raise LlmError(
            f"The model's reply did not match {output.__name__}: {exc.error_count()} validation error(s)"
        ) from exc


class Llm:
    """The pipeline's DeepSeek client. Construct once (`get_llm()`) and share."""

    def __init__(self, settings: LlmSettings | None = None, client: anthropic.AsyncAnthropic | None = None) -> None:
        self.settings = settings or LlmSettings.from_env()
        self._client = client

    @property
    def client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            key, base_url = credentials()
            kwargs: dict[str, Any] = {
                "base_url": base_url or self.settings.base_url,
                "timeout": self.settings.timeout,
                "max_retries": self.settings.max_retries,
            }
            if key:
                kwargs["api_key"] = key
            self._client = anthropic.AsyncAnthropic(**kwargs)
        return self._client

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        effort: str | None = None,
        max_tokens: int | None = None,
        cache: bool = False,
        tools: list[dict[str, Any]] | None = None,
    ) -> tuple[str, Usage]:
        """The text of the model's reply. `cache=True` marks the request's stable prefix (put the
        document in `system` so every stage that reads it shares it); DeepSeek caches context by
        itself, so the mark costs nothing and is honoured again on Anthropic."""
        message, usage = await self._stream(self._params(prompt, system, effort, max_tokens, cache, tools))
        text = _text_of(message)
        if not text.strip():
            raise LlmError("The model returned no text")
        return text, usage

    async def extract(
        self,
        prompt: str,
        output: type[T],
        *,
        system: str | None = None,
        effort: str | None = None,
        max_tokens: int | None = None,
        cache: bool = False,
        tools: list[dict[str, Any]] | None = None,
    ) -> tuple[T, Usage]:
        """A validated instance of the pydantic model `output`. The schema goes in the prompt and
        the reply is validated here, because DeepSeek does not carry structured outputs."""
        params = self._params(prompt + json_instruction(output), system, effort, max_tokens, cache, tools)
        message, usage = await self._stream(params)
        return parse_typed(_text_of(message), output), usage

    async def extract_streaming(
        self,
        prompt: str,
        output: type[T],
        *,
        on_element: Callable[[str, dict[str, Any]], Awaitable[None]],
        system: str | None = None,
        effort: str | None = None,
        max_tokens: int | None = None,
        cache: bool = False,
        tools: list[dict[str, Any]] | None = None,
    ) -> tuple[T, Usage]:
        """Like `extract`, and while the reply streams, `on_element(key, item)` is awaited for
        each object that closes inside one of the result's top-level lists (`key` names the
        list). The validated whole is still returned at the end; a stage can use it to catch
        anything the incremental pass did not hand over."""
        params = self._params(prompt + json_instruction(output), system, effort, max_tokens, cache, tools)
        scanner = JsonArrayElements()

        async def on_text(delta: str) -> None:
            for key, element in scanner.feed(delta):
                try:
                    item = json.loads(element)
                except ValueError:
                    continue  # cannot happen for a closed element; the final parse still has it
                if isinstance(item, dict):
                    await on_element(key, item)

        message, usage = await self._stream(params, on_text=on_text)
        return parse_typed(_text_of(message), output), usage

    def _params(self, prompt: str, system: str | None, effort: str | None, max_tokens: int | None, cache: bool, tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        effort = effort or self.settings.effort
        if effort not in EFFORTS:
            raise ValueError(f"effort must be one of {', '.join(EFFORTS)}, not {effort!r}")
        params: dict[str, Any] = {
            "model": self.settings.model,
            "max_tokens": output_budget(max_tokens or self.settings.max_tokens),
            "messages": [{"role": "user", "content": prompt}],
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": effort},
        }
        if tools:
            params["tools"] = tools
        if system and cache:
            # The breakpoint sits on the system block, so every stage that sends the same
            # document (the system prefix) reads it from the cache whatever its task says.
            params["system"] = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        elif system:
            params["system"] = system
        elif cache:
            params["cache_control"] = {"type": "ephemeral"}
        return params

    async def _stream(self, params: dict[str, Any], on_text: Callable[[str], Awaitable[None]] | None = None) -> tuple[Any, Usage]:
        """One turn, however many requests it takes. A turn can stop to run a local tool
        (`tool_use`), or pause after a server search (`pause_turn`); either way it is sent back
        with what it asked for, up to the budgets above, and every request's usage is added up."""
        started = time.perf_counter()
        params = dict(params)
        tools = list(params.get("tools") or [])
        budget = {t["name"]: int(t.get("_max_uses", 0)) for t in tools if "_max_uses" in t}
        if tools:
            # `_max_uses` is ours, not the API's; it never goes over the wire.
            params["tools"] = [{k: v for k, v in t.items() if k != "_max_uses"} for t in tools]
        messages = list(params["messages"])
        totals = [0, 0, 0, 0]  # input, output, cache read, cache write
        paused = 0
        rounds = 0
        while True:
            params["messages"] = messages
            message = await self._send(params, on_text)
            usage = getattr(message, "usage", None)
            for i, field in enumerate(("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")):
                totals[i] += getattr(usage, field, 0) or 0
            stop = getattr(message, "stop_reason", None)
            if stop == "tool_use":
                if rounds >= MAX_TOOL_ROUNDS:
                    raise LlmError(f"The model asked for tools {rounds + 1} times without answering.")
                rounds += 1
                results = await self._run_tools(message, budget)
                messages = [*messages, {"role": "assistant", "content": message.content}, {"role": "user", "content": results}]
                continue
            if stop != "pause_turn":
                break
            if paused >= MAX_PAUSES:
                raise LlmError(f"The model paused the turn {paused + 1} times without answering; its tools are taking longer than the stage allows.")
            paused += 1
            messages = [*messages, {"role": "assistant", "content": message.content}]
        usage = Usage(
            model=getattr(message, "model", params["model"]),
            input_tokens=totals[0],
            output_tokens=totals[1],
            cache_read_tokens=totals[2],
            cache_write_tokens=totals[3],
            stop_reason=getattr(message, "stop_reason", None),
            request_id=getattr(message, "_request_id", None),
            seconds=time.perf_counter() - started,
        )
        if usage.stop_reason == "max_tokens":
            raise LlmError(
                f"The model's reply was cut off at {params['max_tokens']} tokens (AUDITOR_OUTPUT_HEADROOM "
                f"{OUTPUT_HEADROOM:g}x); raise the stage's budget or the headroom, or ask for less."
            )
        if usage.stop_reason == "refusal":
            details = getattr(message, "stop_details", None)
            category = getattr(details, "category", None) if details is not None else None
            raise LlmError(f"The model declined the request ({category or 'unspecified'}).")
        return message, usage

    async def _run_tools(self, message: Any, budget: dict[str, int]) -> list[dict[str, Any]]:
        """Every local tool the turn asked for, run here, as `tool_result` blocks. A tool that
        fails answers with the reason rather than raising: the model can say it found nothing,
        which is a result the evidence stages know how to record."""
        results: list[dict[str, Any]] = []
        for block in message.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            name = getattr(block, "name", "")
            payload = getattr(block, "input", None) or {}
            if budget.get(name, 0) <= 0:
                text, error = f"The {name} budget for this request is used up.", True
            else:
                budget[name] = budget[name] - 1
                text, error = await _run_tool(name, payload)
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": text, "is_error": error})
        return results

    async def _send(self, params: dict[str, Any], on_text: Callable[[str], Awaitable[None]] | None = None) -> Any:
        """One request, with every way it can fail said in the person's terms."""
        try:
            async with self.client.messages.stream(**params) as stream:
                if on_text is not None:
                    async for event in stream:
                        if getattr(event, "type", None) == "text":
                            await on_text(event.text)
                message = await stream.get_final_message()
        except anthropic.AuthenticationError as exc:
            raise LlmError("DeepSeek refused the credentials. Set DEEPSEEK_API_KEY (in backend/.env or the environment).") from exc
        except anthropic.NotFoundError as exc:
            raise LlmError(f"Model {params['model']!r} was not found; check AUDITOR_MODEL.") from exc
        except anthropic.RateLimitError as exc:
            retry_after = exc.response.headers.get("retry-after", "a moment")
            raise LlmError(f"DeepSeek is rate-limiting this key; retry after {retry_after} s.") from exc
        except anthropic.BadRequestError as exc:
            raise LlmError(f"DeepSeek rejected the request: {exc.message}") from exc
        except anthropic.APIStatusError as exc:
            raise LlmError(f"DeepSeek answered HTTP {exc.status_code}: {exc.message}") from exc
        except anthropic.APITimeoutError as exc:
            raise LlmError(f"DeepSeek did not answer within {self.settings.timeout:.0f} s.") from exc
        except anthropic.APIConnectionError as exc:
            raise LlmError(f"DeepSeek could not be reached: {exc}") from exc
        except httpx.TimeoutException as exc:
            # Raised bare from inside the stream when the connection goes quiet mid-response.
            raise LlmError(f"The stream went quiet for longer than the read timeout ({type(exc).__name__}); retry, or raise the timeout.") from exc
        except httpx.HTTPError as exc:
            raise LlmError(f"The stream broke: {type(exc).__name__}: {exc}") from exc
        except ValidationError as exc:
            raise LlmError(f"The model's reply did not match the expected shape: {exc.error_count()} validation error(s)") from exc
        except TypeError as exc:
            # The SDK raises a plain TypeError, not an API error, when it has no credentials at all.
            if "authentication" not in str(exc).lower():
                raise
            raise LlmError(
                "No DeepSeek credentials found. Put DEEPSEEK_API_KEY in backend/.env (copy .env.example) or export it."
            ) from exc
        return message


def _text_of(message: Any) -> str:
    """Every text block of a reply, joined. `thinking` blocks are not text and never appear."""
    return "".join(getattr(block, "text", "") for block in message.content if getattr(block, "type", None) == "text")


async def _run_tool(name: str, payload: dict[str, Any]) -> tuple[str, bool]:
    """(what to send back, whether it is an error). The only local tool is `web_fetch`, and it
    is the reason this module imports the ingester: the page a quote comes from has to be read
    the same way a document is, or a verified quote would not mean the same thing."""
    if name != "web_fetch":
        return f"There is no tool called {name!r}.", True
    url = str(payload.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return f"{url!r} is not an absolute http(s) URL.", True
    try:
        text = await asyncio.to_thread(_fetch_text, url)
    except Exception as exc:  # any fetch or parse failure is an answer, not a crash
        return f"{url} could not be read: {type(exc).__name__}: {exc}", True
    if not text.strip():
        return f"{url} has no readable text (it may be a JavaScript shell).", True
    if len(text) > FETCH_CONTENT_CHARS:
        text = text[:FETCH_CONTENT_CHARS] + f"\n\n[truncated at {FETCH_CONTENT_CHARS} characters]"
    return f"{url}\n\n{text}", False


def _fetch_text(url: str) -> str:
    """The readable text of a page or PDF, by the same route `auditor.ingest` reads a document."""
    from .ingest import fetch as fetch_module
    from .ingest.html import html_blocks

    fetched = fetch_module.fetch(url)
    if fetched.is_pdf:
        from .ingest import pdf_blocks

        return "\n\n".join(block.text for block in pdf_blocks(fetched.body).blocks)
    if fetched.content_type.startswith("text/plain") or fetched.is_json:
        return fetched.text
    return "\n\n".join(block.text for block in html_blocks(fetched.text, fetched.url).blocks)


_llm: Llm | None = None


def get_llm() -> Llm:
    """The shared client for the pipeline."""
    global _llm
    if _llm is None:
        _llm = Llm()
    return _llm


# ----------------------------------------------------------------------------- CLI


class _Check(BaseModel):
    """Structured output for the `check` command, so the typed path is exercised too."""

    greeting: str
    model_family: str


async def _check(settings: LlmSettings) -> int:
    llm = Llm(settings)
    key, base_url = credentials()
    print(f"model {settings.model} at {base_url}, effort {settings.effort} (carried, ignored by DeepSeek), streaming")
    if not key:
        print("error: no DEEPSEEK_API_KEY (or ANTHROPIC_API_KEY) found", file=sys.stderr)
        return 1
    try:
        text, usage = await llm.complete("Reply with the single word OK.", max_tokens=200)
        print(f"complete: {text.strip()!r}  ({usage.describe()})")
        result, usage = await llm.extract(
            "Say hello, and name the model family you are (for example DeepSeek or Sonnet).", _Check, max_tokens=800
        )
        print(f"extract:  {result.model_dump()}  ({usage.describe()})")
    except LlmError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m auditor.llm", description="Check the DeepSeek setup with one small call.")
    parser.add_argument("command", choices=["check"])
    parser.add_argument("--model", help=f"override AUDITOR_MODEL (default {DEFAULT_MODEL})")
    parser.add_argument("--effort", choices=EFFORTS, help=f"override AUDITOR_EFFORT (default {DEFAULT_EFFORT})")
    args = parser.parse_args(argv)
    settings = LlmSettings.from_env()
    if args.model or args.effort:
        settings = LlmSettings(
            model=args.model or settings.model,
            effort=args.effort or settings.effort,
            max_tokens=settings.max_tokens,
            base_url=settings.base_url,
        )
    return asyncio.run(_check(settings))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

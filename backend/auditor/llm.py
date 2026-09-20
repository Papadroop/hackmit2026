"""Claude calls for the pipeline stages (roadmap steps 11-17).

One place for the model, effort and thinking defaults, the client, and the three call shapes the
stages need: `complete` for text, `extract` for a typed (pydantic) result, and
`extract_streaming` for a typed result whose list items are handed over one by one while Claude
is still writing (the live progression of design-doc D7). Every request streams, so a whole
document in the prompt never hits an HTTP timeout, and every result comes back with its token
usage so a stage can report what it cost.

Any call can pass `tools`; `web_tools()` builds the search and fetch server tools external
verification (step 14) uses to look for evidence. A turn that runs server tools may come back
with `stop_reason: "pause_turn"` before it has answered: `_stream` sends it back to continue,
up to `MAX_PAUSES` times, so a stage never sees a silently truncated result.

Defaults, and the environment variables that change them (read from the environment and from
`backend/.env`):

    ANTHROPIC_API_KEY   the key; the SDK also accepts ANTHROPIC_AUTH_TOKEN or an `ant auth login` profile
    AUDITOR_MODEL       claude-sonnet-5 (Sonnet at high effort is the team's default for now;
                        claude-opus-5 is the step up)
    AUDITOR_EFFORT      high (low | medium | high | xhigh | max)

Thinking is adaptive on every request. Check the setup with `python -m auditor.llm check`.
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

DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_EFFORT = "high"
EFFORTS = ("low", "medium", "high", "xhigh", "max")
DEFAULT_MAX_TOKENS = 16000
ENV_FILE = Path(__file__).resolve().parents[1] / ".env"

# A turn that runs server tools can pause; this is how often we send it back to continue.
MAX_PAUSES = 4

# The direct search and fetch tools, not the `_20260209` dynamic-filtering pair. Those run the
# search inside a code-execution sandbox, so the page arrives as a variable the model has to
# print rather than as text in front of it. Measured on the Ørsted page: the filtering pair
# spent 228 s writing plumbing (and hitting the sandbox's own 90 s detection timeout) and
# returned no quotable evidence at all; the direct pair returned five verbatim quotes in 30 s.
# A stage whose product is a quote wants the page in the context, so these are the defaults.
# AUDITOR_WEB_TOOLS=filtering switches back.
WEB_SEARCH_TOOL = "web_search_20250305"
WEB_FETCH_TOOL = "web_fetch_20250910"
FILTERING_WEB_SEARCH_TOOL = "web_search_20260209"
FILTERING_WEB_FETCH_TOOL = "web_fetch_20260209"


# A fetched page lands in the turn whole. An SEC filing is millions of tokens, so six of them
# put a retrieval call over the 1M context window — which is exactly how one Shell batch failed
# before this cap existed. Enough for the part of a filing a quote comes from, not the filing.
FETCH_CONTENT_TOKENS = int(os.environ.get("AUDITOR_FETCH_CONTENT_TOKENS", "40000"))


def web_tools(*, searches: int = 6, fetches: int = 6) -> list[dict[str, Any]]:
    """Claude's own search and fetch tools, capped. They run on Anthropic's servers, so nothing
    here executes them; `web_fetch` only opens URLs already in the conversation, which in
    practice means the ones the search returned."""
    filtering = os.environ.get("AUDITOR_WEB_TOOLS", "").lower() == "filtering"
    return [
        {"type": FILTERING_WEB_SEARCH_TOOL if filtering else WEB_SEARCH_TOOL, "name": "web_search", "max_uses": searches},
        {
            "type": FILTERING_WEB_FETCH_TOOL if filtering else WEB_FETCH_TOOL,
            "name": "web_fetch",
            "max_uses": fetches,
            "max_content_tokens": FETCH_CONTENT_TOKENS,
        },
    ]

T = TypeVar("T", bound=BaseModel)


class LlmError(Exception):
    """A call did not produce a usable result. The message says why in the person's terms."""


def load_env(path: Path = ENV_FILE) -> bool:
    """Read `backend/.env` into the environment without overriding what is already set."""
    if not path.is_file():
        return False
    from dotenv import load_dotenv

    return load_dotenv(path, override=False)


@dataclass(frozen=True)
class LlmSettings:
    model: str = DEFAULT_MODEL
    effort: str = DEFAULT_EFFORT
    max_tokens: int = DEFAULT_MAX_TOKENS
    timeout: float = 600.0
    max_retries: int = 2

    def __post_init__(self) -> None:
        if self.effort not in EFFORTS:
            raise ValueError(f"effort must be one of {', '.join(EFFORTS)}, not {self.effort!r}")

    @classmethod
    def from_env(cls) -> "LlmSettings":
        load_env()
        values: dict[str, Any] = {}
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
    element is complete, so a chunk boundary can fall anywhere."""

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


class Llm:
    """The pipeline's Claude client. Construct once (`get_llm()`) and share."""

    def __init__(self, settings: LlmSettings | None = None, client: anthropic.AsyncAnthropic | None = None) -> None:
        self.settings = settings or LlmSettings.from_env()
        self._client = client

    @property
    def client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            load_env()
            self._client = anthropic.AsyncAnthropic(timeout=self.settings.timeout, max_retries=self.settings.max_retries)
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
        """The text of Claude's reply. `cache=True` caches the request's stable prefix (put the
        document in `system` so every stage that reads it shares the cache)."""
        message, usage = await self._stream(self._params(prompt, system, effort, max_tokens, cache, tools))
        text = "".join(block.text for block in message.content if block.type == "text")
        if not text.strip():
            raise LlmError("Claude returned no text")
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
        """A validated instance of the pydantic model `output` (structured outputs)."""
        params = self._params(prompt, system, effort, max_tokens, cache, tools)
        params["output_format"] = output
        message, usage = await self._stream(params)
        parsed = getattr(message, "parsed_output", None)
        if parsed is None:
            raise LlmError(f"Claude returned no {output.__name__}")
        return parsed, usage

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
        params = self._params(prompt, system, effort, max_tokens, cache, tools)
        params["output_format"] = output
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
        parsed = getattr(message, "parsed_output", None)
        if parsed is None:
            raise LlmError(f"Claude returned no {output.__name__}")
        return parsed, usage

    def _params(self, prompt: str, system: str | None, effort: str | None, max_tokens: int | None, cache: bool, tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        effort = effort or self.settings.effort
        if effort not in EFFORTS:
            raise ValueError(f"effort must be one of {', '.join(EFFORTS)}, not {effort!r}")
        params: dict[str, Any] = {
            "model": self.settings.model,
            "max_tokens": max_tokens or self.settings.max_tokens,
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
        """One turn, however many requests it takes. A turn that runs server tools can stop with
        `pause_turn` before it has written its answer; it is sent back to continue, its content
        appended, up to `MAX_PAUSES` times, and the token usage of every request is added up."""
        started = time.perf_counter()
        params = dict(params)
        messages = list(params["messages"])
        totals = [0, 0, 0, 0]  # input, output, cache read, cache write
        paused = 0
        while True:
            params["messages"] = messages
            message = await self._send(params, on_text)
            usage = getattr(message, "usage", None)
            for i, field in enumerate(("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")):
                totals[i] += getattr(usage, field, 0) or 0
            if getattr(message, "stop_reason", None) != "pause_turn":
                break
            if paused >= MAX_PAUSES:
                raise LlmError(f"Claude paused the turn {paused + 1} times without answering; its tools are taking longer than the stage allows.")
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
            raise LlmError(f"Claude's reply was cut off at {params['max_tokens']} tokens; raise max_tokens or ask for less.")
        if usage.stop_reason == "refusal":
            details = getattr(message, "stop_details", None)
            category = getattr(details, "category", None) if details is not None else None
            raise LlmError(f"Claude declined the request ({category or 'unspecified'}).")
        return message, usage

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
            raise LlmError("Claude refused the credentials. Set ANTHROPIC_API_KEY (in backend/.env or the environment).") from exc
        except anthropic.NotFoundError as exc:
            raise LlmError(f"Model {params['model']!r} was not found; check AUDITOR_MODEL.") from exc
        except anthropic.RateLimitError as exc:
            retry_after = exc.response.headers.get("retry-after", "a moment")
            raise LlmError(f"Claude is rate-limiting this key; retry after {retry_after} s.") from exc
        except anthropic.BadRequestError as exc:
            raise LlmError(f"Claude rejected the request: {exc.message}") from exc
        except anthropic.APIStatusError as exc:
            raise LlmError(f"Claude answered HTTP {exc.status_code}: {exc.message}") from exc
        except anthropic.APITimeoutError as exc:
            raise LlmError(f"Claude did not answer within {self.settings.timeout:.0f} s.") from exc
        except anthropic.APIConnectionError as exc:
            raise LlmError(f"Claude could not be reached: {exc}") from exc
        except httpx.TimeoutException as exc:
            # Raised bare from inside the stream when the connection goes quiet mid-response.
            raise LlmError(f"Claude's stream went quiet for longer than the read timeout ({type(exc).__name__}); retry, or raise the timeout.") from exc
        except httpx.HTTPError as exc:
            raise LlmError(f"Claude's stream broke: {type(exc).__name__}: {exc}") from exc
        except ValidationError as exc:
            # Structured outputs guarantee the schema; this guards the typed parse all the same.
            raise LlmError(f"Claude's reply did not match the expected shape: {exc.error_count()} validation error(s)") from exc
        except TypeError as exc:
            # The SDK raises a plain TypeError, not an API error, when it has no credentials at all.
            if "authentication" not in str(exc).lower():
                raise
            raise LlmError(
                "No Claude credentials found. Put ANTHROPIC_API_KEY in backend/.env (copy .env.example) or export it."
            ) from exc
        return message


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
    print(f"model {settings.model}, effort {settings.effort}, adaptive thinking, streaming")
    try:
        text, usage = await llm.complete("Reply with the single word OK.", max_tokens=64)
        print(f"complete: {text.strip()!r}  ({usage.describe()})")
        result, usage = await llm.extract(
            "Say hello, and name the model family you are (for example Sonnet or Opus).", _Check, max_tokens=256
        )
        print(f"extract:  {result.model_dump()}  ({usage.describe()})")
    except LlmError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m auditor.llm", description="Check the Claude setup with one small call.")
    parser.add_argument("command", choices=["check"])
    parser.add_argument("--model", help=f"override AUDITOR_MODEL (default {DEFAULT_MODEL})")
    parser.add_argument("--effort", choices=EFFORTS, help=f"override AUDITOR_EFFORT (default {DEFAULT_EFFORT})")
    args = parser.parse_args(argv)
    settings = LlmSettings.from_env()
    if args.model or args.effort:
        settings = LlmSettings(model=args.model or settings.model, effort=args.effort or settings.effort, max_tokens=settings.max_tokens)
    return asyncio.run(_check(settings))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

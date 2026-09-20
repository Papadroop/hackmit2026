"""Claude calls for the pipeline stages (roadmap steps 11-17).

One place for the model, effort and thinking defaults, the client, and the two call shapes the
stages need: `complete` for text and `extract` for a typed (pydantic) result. Every request
streams, so a whole document in the prompt never hits an HTTP timeout, and every result comes
back with its token usage so a stage can report what it cost.

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
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

import anthropic
from pydantic import BaseModel

DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_EFFORT = "high"
EFFORTS = ("low", "medium", "high", "xhigh", "max")
DEFAULT_MAX_TOKENS = 16000
ENV_FILE = Path(__file__).resolve().parents[1] / ".env"

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
        cached = f", {self.cache_read_tokens} from cache" if self.cache_read_tokens else ""
        return f"{self.model}: {self.input_tokens} in{cached}, {self.output_tokens} out, {self.seconds:.1f} s"


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
    ) -> tuple[str, Usage]:
        """The text of Claude's reply. `cache=True` caches the request's stable prefix (put the
        document in `system` so every stage that reads it shares the cache)."""
        message, usage = await self._stream(self._params(prompt, system, effort, max_tokens, cache))
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
    ) -> tuple[T, Usage]:
        """A validated instance of the pydantic model `output` (structured outputs)."""
        params = self._params(prompt, system, effort, max_tokens, cache)
        params["output_format"] = output
        message, usage = await self._stream(params)
        parsed = getattr(message, "parsed_output", None)
        if parsed is None:
            raise LlmError(f"Claude returned no {output.__name__}")
        return parsed, usage

    def _params(self, prompt: str, system: str | None, effort: str | None, max_tokens: int | None, cache: bool) -> dict[str, Any]:
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
        if system:
            params["system"] = system
        if cache:
            params["cache_control"] = {"type": "ephemeral"}
        return params

    async def _stream(self, params: dict[str, Any]) -> tuple[Any, Usage]:
        started = time.perf_counter()
        try:
            async with self.client.messages.stream(**params) as stream:
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
        except TypeError as exc:
            # The SDK raises a plain TypeError, not an API error, when it has no credentials at all.
            if "authentication" not in str(exc).lower():
                raise
            raise LlmError(
                "No Claude credentials found. Put ANTHROPIC_API_KEY in backend/.env (copy .env.example) or export it."
            ) from exc
        usage = Usage(
            model=getattr(message, "model", params["model"]),
            input_tokens=getattr(message.usage, "input_tokens", 0) or 0,
            output_tokens=getattr(message.usage, "output_tokens", 0) or 0,
            cache_read_tokens=getattr(message.usage, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(message.usage, "cache_creation_input_tokens", 0) or 0,
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

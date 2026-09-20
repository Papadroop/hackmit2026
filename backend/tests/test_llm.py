"""The Claude client's defaults and plumbing, with a fake SDK client (no network)."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import anthropic
import httpx2 as httpx
import pytest
from pydantic import BaseModel

from auditor import llm as llm_module
from auditor.llm import DEFAULT_EFFORT, DEFAULT_MODEL, Llm, LlmError, LlmSettings


class FakeMessages:
    """Records the params of each `stream(...)` call and answers with a canned final message."""

    def __init__(self, message=None, error: Exception | None = None) -> None:
        self.calls: list[dict] = []
        self.message = message or text_message("OK")
        self.error = error

    @asynccontextmanager
    async def stream(self, **params):
        self.calls.append(params)
        if self.error is not None:
            raise self.error
        message = self.message

        class Stream:
            async def get_final_message(self):
                return message

        yield Stream()


def text_message(text: str, *, stop_reason: str = "end_turn", parsed=None, **extra):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=12, output_tokens=3, cache_read_input_tokens=0, cache_creation_input_tokens=0),
        model=DEFAULT_MODEL,
        _request_id="req_test",
        parsed_output=parsed,
        **extra,
    )


def make_llm(messages: FakeMessages, **settings) -> Llm:
    client = SimpleNamespace(messages=messages)
    return Llm(LlmSettings(**settings), client=client)  # type: ignore[arg-type]


def run(coro):
    return asyncio.run(coro)


def test_defaults_are_sonnet_at_high_effort(monkeypatch):
    for name in ("AUDITOR_MODEL", "AUDITOR_EFFORT", "AUDITOR_MAX_TOKENS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(llm_module, "load_env", lambda *a, **k: False)
    settings = LlmSettings.from_env()
    assert settings.model == "claude-sonnet-5" and settings.effort == "high" and settings.max_tokens == 16000


def test_settings_come_from_the_environment(monkeypatch):
    monkeypatch.setattr(llm_module, "load_env", lambda *a, **k: False)
    monkeypatch.setenv("AUDITOR_MODEL", "claude-opus-5")
    monkeypatch.setenv("AUDITOR_EFFORT", "XHIGH")
    monkeypatch.setenv("AUDITOR_MAX_TOKENS", "32000")
    settings = LlmSettings.from_env()
    assert (settings.model, settings.effort, settings.max_tokens) == ("claude-opus-5", "xhigh", 32000)
    monkeypatch.setenv("AUDITOR_EFFORT", "extreme")
    with pytest.raises(ValueError, match="effort must be one of"):
        LlmSettings.from_env()


def test_dotenv_is_read_without_overriding_the_environment(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("AUDITOR_MODEL=claude-opus-5\nAUDITOR_EFFORT=max\n")
    monkeypatch.delenv("AUDITOR_MODEL", raising=False)
    monkeypatch.setenv("AUDITOR_EFFORT", "low")
    assert llm_module.load_env(env) is True
    assert LlmSettings.from_env() == LlmSettings(model="claude-opus-5", effort="low")
    assert llm_module.load_env(tmp_path / "missing") is False


def test_complete_sends_the_defaults_and_returns_text_with_usage():
    fake = FakeMessages()
    text, usage = run(make_llm(fake).complete("Reply with OK.", system="Be brief."))
    assert text == "OK"
    assert usage.model == DEFAULT_MODEL and usage.input_tokens == 12 and usage.output_tokens == 3
    assert usage.request_id == "req_test" and usage.stop_reason == "end_turn"
    [params] = fake.calls
    assert params["model"] == DEFAULT_MODEL
    assert params["output_config"] == {"effort": DEFAULT_EFFORT}
    assert params["thinking"] == {"type": "adaptive"}
    assert params["max_tokens"] == 16000
    assert params["system"] == "Be brief."
    assert params["messages"] == [{"role": "user", "content": "Reply with OK."}]
    assert "cache_control" not in params and "output_format" not in params


def test_per_call_overrides_and_caching():
    fake = FakeMessages()
    run(make_llm(fake, model="claude-opus-5", effort="medium").complete("x", effort="max", max_tokens=500, cache=True))
    [params] = fake.calls
    assert params["model"] == "claude-opus-5"
    assert params["output_config"] == {"effort": "max"} and params["max_tokens"] == 500
    assert params["cache_control"] == {"type": "ephemeral"}
    with pytest.raises(ValueError):
        run(make_llm(fake).complete("x", effort="huge"))


class Claim(BaseModel):
    text: str
    kind: str


def test_extract_uses_structured_outputs():
    fake = FakeMessages(text_message('{"text": "net zero by 2050", "kind": "commitment"}', parsed=Claim(text="net zero by 2050", kind="commitment")))
    claim, usage = run(make_llm(fake).extract("Find the claim.", Claim))
    assert claim == Claim(text="net zero by 2050", kind="commitment")
    assert fake.calls[0]["output_format"] is Claim
    empty = FakeMessages(text_message("", parsed=None))
    with pytest.raises(LlmError, match="no Claim"):
        run(make_llm(empty).extract("Find the claim.", Claim))


def test_truncation_and_refusal_are_errors():
    with pytest.raises(LlmError, match="cut off at 16000"):
        run(make_llm(FakeMessages(text_message("partial", stop_reason="max_tokens"))).complete("x"))
    refused = text_message("", stop_reason="refusal", stop_details=SimpleNamespace(category="cyber", explanation="no"))
    with pytest.raises(LlmError, match="declined.*cyber"):
        run(make_llm(FakeMessages(refused)).complete("x"))
    with pytest.raises(LlmError, match="no text"):
        run(make_llm(FakeMessages(text_message("   "))).complete("x"))


def api_error(cls, status: int, headers: dict | None = None):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(status, request=request, headers=headers or {}, json={"error": {"message": "nope"}})
    return cls("nope", response=response, body=None)


@pytest.mark.parametrize(
    "error, message",
    [
        (api_error(anthropic.AuthenticationError, 401), "ANTHROPIC_API_KEY"),
        (api_error(anthropic.NotFoundError, 404), "AUDITOR_MODEL"),
        (api_error(anthropic.RateLimitError, 429, {"retry-after": "7"}), "retry after 7"),
        (api_error(anthropic.BadRequestError, 400), "rejected the request"),
        (api_error(anthropic.InternalServerError, 503), "HTTP 503"),
        (anthropic.APITimeoutError(httpx.Request("POST", "https://api.anthropic.com/v1/messages")), "within 600 s"),
        (anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")), "could not be reached"),
        (TypeError("Could not resolve authentication method. Expected one of api_key, auth_token, or credentials to be set."), "No Claude credentials"),
    ],
)
def test_sdk_errors_become_plain_messages(error, message):
    with pytest.raises(LlmError, match=message):
        run(make_llm(FakeMessages(error=error)).complete("x"))


def test_shared_client_is_constructed_lazily(monkeypatch):
    monkeypatch.setattr(llm_module, "_llm", None)
    monkeypatch.setattr(llm_module, "load_env", lambda *a, **k: False)
    monkeypatch.delenv("AUDITOR_MODEL", raising=False)
    monkeypatch.delenv("AUDITOR_EFFORT", raising=False)
    shared = llm_module.get_llm()
    assert shared is llm_module.get_llm()
    assert shared.settings.model == DEFAULT_MODEL
    assert shared._client is None, "no SDK client until the first call"

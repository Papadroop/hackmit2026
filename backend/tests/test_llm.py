"""The DeepSeek client's defaults and plumbing, with a fake SDK client (no network)."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import anthropic
import httpx2 as httpx
import pytest
from pydantic import BaseModel

from auditor import llm as llm_module
from auditor.llm import DEFAULT_EFFORT, DEFAULT_MODEL, JsonArrayElements, Llm, LlmError, LlmSettings


class FakeMessages:
    """Records the params of each `stream(...)` call and answers with a canned final message."""

    def __init__(self, message=None, error: Exception | None = None, chunks: list[str] | None = None) -> None:
        self.calls: list[dict] = []
        self.message = message or text_message("OK")
        self.error = error
        self.chunks = chunks

    @asynccontextmanager
    async def stream(self, **params):
        self.calls.append(params)
        if self.error is not None:
            raise self.error
        message = self.message
        chunks = self.chunks or []

        class Stream:
            def __init__(self) -> None:
                self.iterated = False

            async def __aiter__(self):
                self.iterated = True
                yield SimpleNamespace(type="thinking", thinking="hmm")
                for chunk in chunks:
                    yield SimpleNamespace(type="text", text=chunk, snapshot="")

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


def test_defaults_are_deepseek_at_high_effort(monkeypatch):
    for name in ("AUDITOR_MODEL", "AUDITOR_EFFORT", "AUDITOR_MAX_TOKENS", "DEEPSEEK_BASE_URL", "ANTHROPIC_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(llm_module, "load_env", lambda *a, **k: False)
    settings = LlmSettings.from_env()
    assert settings.model == "deepseek-flash" and settings.effort == "high" and settings.max_tokens == 8000
    assert settings.base_url == "https://api.deepseek.com/anthropic"


def test_settings_come_from_the_environment(monkeypatch):
    monkeypatch.setattr(llm_module, "load_env", lambda *a, **k: False)
    monkeypatch.setenv("AUDITOR_MODEL", "deepseek-reasoner")
    monkeypatch.setenv("AUDITOR_EFFORT", "XHIGH")
    monkeypatch.setenv("AUDITOR_MAX_TOKENS", "32000")
    settings = LlmSettings.from_env()
    assert (settings.model, settings.effort, settings.max_tokens) == ("deepseek-reasoner", "xhigh", 32000)
    monkeypatch.setenv("AUDITOR_EFFORT", "extreme")
    with pytest.raises(ValueError, match="effort must be one of"):
        LlmSettings.from_env()


def test_dotenv_is_read_without_overriding_the_environment(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("AUDITOR_MODEL=deepseek-reasoner\nAUDITOR_EFFORT=max\n")
    monkeypatch.delenv("AUDITOR_MODEL", raising=False)
    monkeypatch.setenv("AUDITOR_EFFORT", "low")
    assert llm_module.load_env(env) is True
    assert LlmSettings.from_env() == LlmSettings(model="deepseek-reasoner", effort="low", base_url=LlmSettings.from_env().base_url)
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
    assert params["max_tokens"] == 8000 * 3, "the reasoning gets room on top of the answer's budget"
    assert params["system"] == "Be brief."
    assert params["messages"] == [{"role": "user", "content": "Reply with OK."}]
    assert "cache_control" not in params
    assert "output_format" not in params, "DeepSeek does not carry structured outputs"


def test_per_call_overrides_and_caching():
    fake = FakeMessages()
    run(make_llm(fake, model="deepseek-reasoner", effort="medium").complete("x", effort="max", max_tokens=500, cache=True))
    [params] = fake.calls
    assert params["model"] == "deepseek-reasoner"
    assert params["output_config"] == {"effort": "max"} and params["max_tokens"] == 1500
    assert params["cache_control"] == {"type": "ephemeral"}, "no system block: the breakpoint goes on the whole request"
    run(make_llm(fake).complete("x", system="Doc.", cache=True))
    params = fake.calls[-1]
    assert params["system"] == [{"type": "text", "text": "Doc.", "cache_control": {"type": "ephemeral"}}], "the breakpoint sits on the document block so every stage shares it"
    assert "cache_control" not in params
    with pytest.raises(ValueError):
        run(make_llm(fake).complete("x", effort="huge"))


class Claim(BaseModel):
    text: str
    kind: str


def test_extract_sends_the_schema_and_validates_the_reply():
    # DeepSeek's compatibility endpoint drops `output_format`, so the schema travels in the
    # prompt and the reply is validated here instead.
    fake = FakeMessages(text_message('{"text": "net zero by 2050", "kind": "commitment"}'))
    claim, usage = run(make_llm(fake).extract("Find the claim.", Claim))
    assert claim == Claim(text="net zero by 2050", kind="commitment")
    sent = fake.calls[0]["messages"][0]["content"]
    assert sent.startswith("Find the claim.") and "JSON Schema" in sent and '"kind"' in sent
    assert "output_format" not in fake.calls[0]
    with pytest.raises(LlmError, match="no JSON object"):
        run(make_llm(FakeMessages(text_message("I could not find one."))).extract("Find it.", Claim))
    with pytest.raises(LlmError, match="did not match Claim"):
        run(make_llm(FakeMessages(text_message('{"text": "x"}'))).extract("Find it.", Claim))


def test_a_fenced_or_chatty_reply_still_parses():
    fenced = text_message('Sure:\n```json\n{"text": "t", "kind": "k"}\n```\nHope that helps.')
    claim, _ = run(make_llm(FakeMessages(fenced)).extract("Find the claim.", Claim))
    assert claim == Claim(text="t", kind="k")


def test_truncation_and_refusal_are_errors():
    with pytest.raises(LlmError, match="cut off at 24000"):
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
        (api_error(anthropic.AuthenticationError, 401), "DEEPSEEK_API_KEY"),
        (api_error(anthropic.NotFoundError, 404), "AUDITOR_MODEL"),
        (api_error(anthropic.RateLimitError, 429, {"retry-after": "7"}), "retry after 7"),
        (api_error(anthropic.BadRequestError, 400), "rejected the request"),
        (api_error(anthropic.InternalServerError, 503), "HTTP 503"),
        (anthropic.APITimeoutError(httpx.Request("POST", "https://api.anthropic.com/v1/messages")), "within 600 s"),
        (anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")), "could not be reached"),
        (TypeError("Could not resolve authentication method. Expected one of api_key, auth_token, or credentials to be set."), "No DeepSeek credentials"),
        (httpx.ReadTimeout(""), "went quiet"),
        (httpx.RemoteProtocolError("peer closed connection"), "stream broke"),
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


# ----------------------------------------------------------------------------- streaming elements


ROOT = '{"signals": [{"kind": "hedge", "quotes": ["we {believe}", "a \\"quoted\\" ]word"], "n": {"x": [1, {"y": 2}]}}, {"kind": "vague_term"}], "note": "x [y] {z}", "tags": ["a", "b"], "clarity": [{"claim_id": "C1", "score": 0.5}]}'


@pytest.mark.parametrize("size", [1, 2, 5, 13, 10_000])
def test_json_array_elements_hands_over_each_object_as_it_closes(size):
    scanner = JsonArrayElements()
    out: list[tuple[str, str]] = []
    for i in range(0, len(ROOT), size):
        out += scanner.feed(ROOT[i : i + size])
    assert [k for k, _ in out] == ["signals", "signals", "clarity"]
    import json

    assert json.loads(out[0][1]) == {"kind": "hedge", "quotes": ["we {believe}", 'a "quoted" ]word'], "n": {"x": [1, {"y": 2}]}}
    assert json.loads(out[1][1]) == {"kind": "vague_term"}
    assert json.loads(out[2][1]) == {"claim_id": "C1", "score": 0.5}


def test_json_array_elements_ignores_scalars_and_strings_that_look_like_keys():
    scanner = JsonArrayElements()
    assert scanner.feed('{"a": "items", "items": [1, "two", {"k": "v"}], "b": {"items": [{"nested": 1}]}}') == [("items", '{"k": "v"}')]


class Review(BaseModel):
    class Item(BaseModel):
        kind: str

    signals: list[Item]
    clarity: list[dict]


def test_extract_streaming_hands_over_elements_then_returns_the_whole():
    text = '{"signals": [{"kind": "hedge"}, {"kind": "vague"}], "clarity": [{"claim_id": "C1"}]}'
    parsed = Review(signals=[Review.Item(kind="hedge"), Review.Item(kind="vague")], clarity=[{"claim_id": "C1"}])
    messages = FakeMessages(text_message(text), chunks=[text[:15], text[15:40], text[40:]])
    llm = make_llm(messages)
    seen: list[tuple[str, dict]] = []

    async def on_element(key, item):
        seen.append((key, item))

    result, usage = run(llm.extract_streaming("go", Review, on_element=on_element, system="doc", cache=True))
    assert seen == [("signals", {"kind": "hedge"}), ("signals", {"kind": "vague"}), ("clarity", {"claim_id": "C1"})]
    assert result == parsed and usage.output_tokens == 3
    params = messages.calls[0]
    assert "output_format" not in params
    assert params["system"] == [{"type": "text", "text": "doc", "cache_control": {"type": "ephemeral"}}]
    assert "JSON Schema" in params["messages"][0]["content"]


def test_extract_streaming_without_a_usable_result_is_an_error():
    messages = FakeMessages(text_message("{}"), chunks=["{}"])

    async def on_element(key, item):
        raise AssertionError("nothing to hand over")

    with pytest.raises(LlmError, match="did not match Review"):
        run(make_llm(messages).extract_streaming("go", Review, on_element=on_element))


def test_a_shape_mismatch_inside_the_stream_is_a_plain_error():
    from pydantic import ValidationError

    try:
        Review.model_validate({"signals": "nope"})
    except ValidationError as exc:
        error = exc
    llm = make_llm(FakeMessages(error=error))
    with pytest.raises(LlmError, match="did not match the expected shape"):
        run(llm.complete("hi"))


# ----------------------------------------------------------------------------- local tools


class SequenceMessages(FakeMessages):
    """Answers each `stream(...)` with the next canned message, so a tool round-trip can be
    played out: ask for a tool, then answer once the result comes back."""

    def __init__(self, messages: list) -> None:
        super().__init__(messages[0])
        self.queue = list(messages)

    @asynccontextmanager
    async def stream(self, **params):
        self.message = self.queue.pop(0) if self.queue else self.message
        async with super().stream(**params) as stream:
            yield stream


def tool_message(name: str, payload: dict, *, id: str = "tu_1"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", name=name, input=payload, id=id)],
        stop_reason="tool_use",
        usage=SimpleNamespace(input_tokens=5, output_tokens=2, cache_read_input_tokens=0, cache_creation_input_tokens=0),
        model=DEFAULT_MODEL,
        _request_id="req_tool",
    )


def test_web_tools_pair_a_server_search_with_a_local_fetch():
    search, fetch = llm_module.web_tools(searches=3, fetches=2)
    assert search["type"] == llm_module.WEB_SEARCH_TOOL and search["max_uses"] == 3
    assert "type" not in fetch and fetch["name"] == "web_fetch", "fetch is ours: DeepSeek rejects Anthropic's"
    assert fetch["_max_uses"] == 2


def test_a_local_tool_call_is_run_and_its_result_sent_back(monkeypatch):
    monkeypatch.setattr(llm_module, "_run_tool", _fake_tool("Example Domain."))
    fake = SequenceMessages([tool_message("web_fetch", {"url": "https://example.com"}), text_message("It says Example Domain.")])
    text, usage = run(make_llm(fake).complete("Read it.", tools=llm_module.web_tools(fetches=2)))
    assert text == "It says Example Domain."
    assert usage.input_tokens == 5 + 12, "every request in the turn is counted"
    sent = fake.calls[0]["tools"]
    assert all("_max_uses" not in tool for tool in sent), "the budget is ours and never goes over the wire"
    result = fake.calls[1]["messages"][-1]["content"]
    assert result == [{"type": "tool_result", "tool_use_id": "tu_1", "content": "Example Domain.", "is_error": False}]


def test_a_tool_beyond_its_budget_answers_rather_than_running(monkeypatch):
    calls: list[str] = []

    async def counting(name, payload):
        calls.append(name)
        return "page", False

    monkeypatch.setattr(llm_module, "_run_tool", counting)
    fake = SequenceMessages([
        tool_message("web_fetch", {"url": "https://a.example"}, id="t1"),
        tool_message("web_fetch", {"url": "https://b.example"}, id="t2"),
        text_message("done"),
    ])
    run(make_llm(fake).complete("Read both.", tools=llm_module.web_tools(fetches=1)))
    assert calls == ["web_fetch"], "the second call is refused, not run"
    refused = fake.calls[2]["messages"][-1]["content"][0]
    assert refused["is_error"] is True and "budget" in refused["content"]


def test_an_unknown_tool_is_an_answer_not_a_crash():
    assert run(llm_module._run_tool("nonsense", {})) == ("There is no tool called 'nonsense'.", True)
    text, error = run(llm_module._run_tool("web_fetch", {"url": "not-a-url"}))
    assert error is True and "absolute http(s) URL" in text


def test_a_turn_that_never_stops_asking_for_tools_is_an_error(monkeypatch):
    monkeypatch.setattr(llm_module, "_run_tool", _fake_tool("page"))
    forever = SequenceMessages([tool_message("web_fetch", {"url": "https://example.com"})] * 40)
    with pytest.raises(LlmError, match="asked for tools"):
        run(make_llm(forever).complete("Loop.", tools=llm_module.web_tools(fetches=99)))


def _fake_tool(answer: str):
    async def run_tool(name, payload):
        return answer, False

    return run_tool


def test_the_output_budget_leaves_room_for_reasoning_and_stops_at_the_ceiling(monkeypatch):
    # DeepSeek charges its reasoning to max_tokens, so a stage's answer budget is not the whole
    # ask. Measured: 1,408 tokens of answer against 12,819 of reasoning on one match call.
    assert llm_module.output_budget(12000) == 36000
    monkeypatch.setattr(llm_module, "OUTPUT_CEILING", 20000)
    assert llm_module.output_budget(12000) == 20000
    monkeypatch.setattr(llm_module, "OUTPUT_HEADROOM", 1.0)
    assert llm_module.output_budget(9000) == 9000, "headroom 1 is the old behaviour, for Anthropic"

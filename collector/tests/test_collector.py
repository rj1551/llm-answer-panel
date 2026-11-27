"""Offline tests for the collector: fake SSM, fake R2 and fake engine calls."""

import hashlib
import json
from datetime import UTC, datetime

import pytest

import engines
import handler

SCHEMA = {
    "response_id",
    "run_id",
    "run_date",
    "engine",
    "model_requested",
    "model_returned",
    "prompt_id",
    "prompt_version",
    "category",
    "sample_idx",
    "request_params",
    "requested_at",
    "latency_ms",
    "status",
    "error_message",
    "response_text",
    "citations",
    "input_tokens",
    "output_tokens",
    "search_calls",
    "est_cost_usd",
}
NOW = datetime(2026, 11, 28, 14, 0, 5, tzinfo=UTC)


class FakeSSM:
    def __init__(self):
        self.names = []

    def get_parameter(self, Name, WithDecryption):
        assert WithDecryption
        self.names.append(Name)
        return {"Parameter": {"Value": f"secret-for-{Name}"}}


class FakeS3:
    def __init__(self):
        self.puts = []  # (key, body) in write order

    def put_object(self, Bucket, Key, Body, ContentType):
        self.puts.append((Key, Body))

    def jsonl(self, suffix):
        body = next(b for k, b in self.puts if k.endswith(suffix))
        return [json.loads(line) for line in body.decode().splitlines()]


def ok_call(prompt, api_key):
    parsed = {
        "model_returned": "m-1",
        "response_text": f"answer to {prompt}",
        "citations": ["https://x"],
        "input_tokens": 10,
        "output_tokens": 20,
        "search_calls": 1,
        "est_cost_usd": 0.01,
        "effective_params": {"temperature": 1.0},
    }
    return {"input": prompt}, parsed


@pytest.fixture
def fake_engines(monkeypatch):
    calls = {"openai": ok_call, "gemini": ok_call}
    for name in calls:
        monkeypatch.setitem(engines.ENGINES[name], "call", lambda p, k, n=name: calls[n](p, k))
    return calls


def run(event=None, remaining=900.0):
    ssm, s3 = FakeSSM(), FakeS3()
    manifest = handler.collect(
        event or {},
        ssm=ssm,
        s3=s3,
        bucket="b",
        remaining_s=lambda: remaining,
        now=NOW,
        sleep=lambda s: None,
    )
    return manifest, ssm, s3


def test_row_count_schema_and_grain(fake_engines):
    prompts, _ = handler.load_prompts()
    expected = len(prompts["prompts"]) * prompts["samples_per_prompt"]
    _manifest, _, s3 = run()
    for engine in ("openai", "gemini"):
        rows = s3.jsonl(f"{engine}.jsonl")
        assert len(rows) == expected
        assert all(set(r) == SCHEMA for r in rows)
        grain = {(r["run_id"], r["engine"], r["prompt_id"], r["sample_idx"]) for r in rows}
        assert len(grain) == expected
        assert {r["sample_idx"] for r in rows} == set(range(prompts["samples_per_prompt"]))
        assert all(r["status"] == "ok" and r["run_date"] == "2026-11-28" for r in rows)
    assert len({r["response_id"] for r in s3.jsonl("openai.jsonl")}) == expected


def test_manifest_is_written_last_and_lists_files(fake_engines):
    manifest, _, s3 = run()
    keys = [k for k, _ in s3.puts]
    assert keys[-1].endswith("/_manifest.json")
    assert keys[0].startswith(f"raw/panel/dt=2026-11-28/run={manifest['run_id']}/")
    assert {f["engine"]: f["rows"] for f in manifest["files"]} == {"openai": 144, "gemini": 144}


def test_prompt_version_is_sha256_of_file(fake_engines):
    manifest, _, s3 = run()
    expected = hashlib.sha256(handler.PROMPTS_PATH.read_bytes()).hexdigest()
    assert manifest["prompt_version"] == expected
    assert {r["prompt_version"] for r in s3.jsonl("openai.jsonl")} == {expected}


def test_starter_prompts_are_valid():
    prompts, _ = handler.load_prompts()
    ids = [p["id"] for p in prompts["prompts"]]
    assert len(ids) == len(set(ids)) == 72
    assert prompts["samples_per_prompt"] == 2
    per_category = {}
    for p in prompts["prompts"]:
        per_category[p["category"]] = per_category.get(p["category"], 0) + 1
    assert set(per_category.values()) == {12} and len(per_category) == 6


def test_engines_filter_runs_only_requested_engine(fake_engines):
    manifest, ssm, _s3 = run({"engines": ["gemini"]})
    assert [f["engine"] for f in manifest["files"]] == ["gemini"]
    assert ssm.names == ["/llm-panel/GEMINI_API_KEY"]


def test_unknown_engine_is_rejected(fake_engines):
    with pytest.raises(ValueError):
        run({"engines": ["claude"]})


def test_high_error_rate_raises_after_files_are_written(fake_engines):
    def failing(prompt, api_key):
        raise engines.PermanentError("HTTP 401: bad key")

    fake_engines["gemini"] = failing
    ssm, s3 = FakeSSM(), FakeS3()
    with pytest.raises(RuntimeError, match="gemini"):
        handler.collect(
            {}, ssm=ssm, s3=s3, bucket="b", remaining_s=lambda: 900.0, now=NOW, sleep=lambda s: None
        )
    assert s3.puts[-1][0].endswith("/_manifest.json")
    rows = s3.jsonl("gemini.jsonl")
    assert len(rows) == 144 and all(r["status"] == "error" for r in rows)
    assert all("401" in r["error_message"] for r in rows)
    assert all(r["status"] == "ok" for r in s3.jsonl("openai.jsonl"))


def test_retryable_errors_are_retried_then_succeed():
    attempts = []

    def flaky(prompt, api_key):
        attempts.append(1)
        if len(attempts) < 3:
            raise engines.RetryableError("HTTP 429")
        return ok_call(prompt, api_key)

    sleeps = []
    _body, _parsed, error = handler.call_with_retries(flaky, "q", "k", sleep=sleeps.append)
    assert error is None and len(attempts) == 3
    assert len(sleeps) == 2 and sleeps[1] > sleeps[0]


def test_retries_give_up_after_three():
    attempts = []

    def always_429(prompt, api_key):
        attempts.append(1)
        raise engines.RetryableError("HTTP 429")

    _, _, error = handler.call_with_retries(always_429, "q", "k", sleep=lambda s: None)
    assert len(attempts) == 1 + handler.MAX_RETRIES
    assert error.startswith("after 3 retries")


def test_permanent_errors_are_not_retried():
    attempts = []

    def bad_request(prompt, api_key):
        attempts.append(1)
        raise engines.PermanentError("HTTP 400")

    _, _, error = handler.call_with_retries(bad_request, "q", "k", sleep=lambda s: None)
    assert len(attempts) == 1 and error == "HTTP 400"


def test_empty_answer_counts_as_error():
    def empty(prompt, api_key):
        body, parsed = ok_call(prompt, api_key)
        return body, {**parsed, "response_text": "  "}

    _, _, error = handler.call_with_retries(empty, "q", "k", sleep=lambda s: None)
    assert error == "empty response_text"


def test_near_deadline_writes_error_rows_instead_of_calling(fake_engines):
    def must_not_run(prompt, api_key):
        raise AssertionError("called past the deadline")

    fake_engines["openai"] = must_not_run
    fake_engines["gemini"] = must_not_run
    with pytest.raises(RuntimeError):
        run(remaining=30.0)


def test_request_params_record_sent_and_effective(fake_engines):
    _, _, s3 = run({"engines": ["openai"]})
    params = json.loads(s3.jsonl("openai.jsonl")[0]["request_params"])
    assert params["sent"] == {"input": "What laptop should I buy for college?"}
    assert params["effective"] == {"temperature": 1.0}


# --- Parsers, on trimmed copies of real response shapes -----------------------------------


def test_openai_request_caps_searches_and_sets_us_location():
    body = engines.openai_request("q")
    assert body["max_tool_calls"] == 1
    assert body["tools"][0]["user_location"]["country"] == "US"
    assert body["model"] == engines.OPENAI_MODEL


def test_parse_openai_uses_billed_search_count_not_output_items():
    out = {
        "model": "gpt-6-luna",
        "temperature": 1.0,
        "top_p": 0.98,
        "max_tool_calls": 1,
        "reasoning": {"effort": "medium"},
        "output": [
            {"type": "reasoning"},
            {"type": "web_search_call", "status": "completed", "action": {"type": "search"}},
            {"type": "web_search_call", "status": "searching", "action": {"type": "open_page"}},
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": "Try a drip brewer.",
                        "annotations": [{"type": "url_citation", "url": "https://a.example/x"}],
                    }
                ],
            },
        ],
        "usage": {
            "input_tokens": 13000,
            "output_tokens": 800,
            "input_tokens_details": {"cached_tokens": 4000, "cache_write_tokens": 0},
        },
        "tool_usage": {"web_search": {"num_requests": 1}},
    }
    p = engines.parse_openai(out)
    assert p["search_calls"] == 1
    assert p["citations"] == ["https://a.example/x"]
    assert p["response_text"] == "Try a drip brewer."
    expected = (9000 * 0.10 + 4000 * 0.01 + 800 * 0.50) / 1e6 + 0.01
    assert p["est_cost_usd"] == pytest.approx(expected, abs=1e-6)


def test_parse_gemini_reads_grounding_and_thinking_tokens():
    out = {
        "modelVersion": "gemini-3.5-flash-lite",
        "candidates": [
            {
                "finishReason": "STOP",
                "content": {"parts": [{"text": "Consider "}, {"text": "a midrange model."}]},
                "groundingMetadata": {
                    "webSearchQueries": ["best laptops 2026", "college laptops"],
                    "groundingChunks": [{"web": {"uri": "https://v.example/1", "title": "t"}}],
                },
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 10,
            "candidatesTokenCount": 1000,
            "thoughtsTokenCount": 100,
        },
    }
    p = engines.parse_gemini(out)
    assert p["response_text"] == "Consider a midrange model."
    assert p["search_calls"] == 2 and p["citations"] == ["https://v.example/1"]
    assert p["output_tokens"] == 1100
    assert p["model_returned"] == "gemini-3.5-flash-lite"


def test_parse_gemini_handles_blocked_answer_without_candidates():
    p = engines.parse_gemini({"promptFeedback": {"blockReason": "SAFETY"}})
    assert p["response_text"] == "" and p["citations"] == []

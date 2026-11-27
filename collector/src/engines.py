"""One API call per engine, returned as the engine-specific part of a record (SPEC §3).

Plain HTTP (urllib) instead of the vendor SDKs: the exact request body is what we record
in `request_params`, and the Lambda package stays free of compiled dependencies.
"""

import json
import urllib.error
import urllib.request

# --- Settings (log changes in DECISIONS.md) ---------------------------------------------

OPENAI_MODEL = "gpt-6-luna"  # no dated snapshot exists; model_returned is recorded per row
OPENAI_URL = "https://api.openai.com/v1/responses"
GEMINI_MODEL = "gemini-3.5-flash-lite"
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)
GEMINI_GROUNDING = True
HTTP_TIMEOUT_S = 120

# Estimated list prices, USD. est_cost_usd is an estimate (SPEC §3), not the bill.
# gpt-6-luna per 1M tokens, from the OpenAI pricing page on 2026-11-27.
OPENAI_PRICE = {
    "input": 0.10,
    "cached": 0.01,
    "cache_write_30m": 0.125,
    "output": 0.50,
    "search": 0.010,
}
# gemini-3.5-flash-lite paid tier per 1M tokens; search at list price per query, ignoring
# the 5,000 free monthly queries, so the estimate errs high.
GEMINI_PRICE = {"input": 0.30, "output": 2.50, "search": 0.014}


class RetryableError(Exception):
    """Rate limit, server error or network problem: worth another attempt."""


class PermanentError(Exception):
    """Bad request, auth or not-found: retrying would fail the same way."""


def _post(url: str, headers: dict, body: dict) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={**headers, "Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        detail = f"HTTP {e.code}: {e.read().decode(errors='replace')[:500]}"
        if e.code == 429 or e.code >= 500:
            raise RetryableError(detail) from e
        raise PermanentError(detail) from e
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise RetryableError(f"network: {e}") from e


# --- OpenAI -----------------------------------------------------------------------------


def openai_request(prompt: str) -> dict:
    return {
        "model": OPENAI_MODEL,
        "input": prompt,
        "tools": [
            {"type": "web_search", "user_location": {"type": "approximate", "country": "US"}}
        ],
        # At most one search per answer: keeps cost in budget and every answer on the same
        # search budget (DECISIONS 2026-11-27).
        "max_tool_calls": 1,
        "reasoning": {"effort": "medium"},
        "store": False,
    }


def parse_openai(out: dict) -> dict:
    text, citations = "", []
    for item in out.get("output", []):
        if item.get("type") != "message":
            continue
        for part in item.get("content", []):
            if part.get("type") == "output_text":
                text += part.get("text", "")
                citations += [
                    a["url"] for a in part.get("annotations", []) if a.get("type") == "url_citation"
                ]
    usage = out.get("usage") or {}
    details = usage.get("input_tokens_details") or {}
    cached = details.get("cached_tokens", 0) or 0
    written = details.get("cache_write_tokens", 0) or 0
    input_tokens = usage.get("input_tokens", 0) or 0
    output_tokens = usage.get("output_tokens", 0) or 0
    # Billed searches. Output items also include page opens the cap blocked, which aren't billed.
    searches = ((out.get("tool_usage") or {}).get("web_search") or {}).get("num_requests", 0) or 0
    p = OPENAI_PRICE
    cost = (
        (input_tokens - cached - written) * p["input"]
        + cached * p["cached"]
        + written * p["cache_write_30m"]
        + output_tokens * p["output"]
    ) / 1e6 + searches * p["search"]
    return {
        "model_returned": out.get("model"),
        "response_text": text,
        "citations": citations,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "search_calls": searches,
        "est_cost_usd": round(cost, 6),
        "effective_params": {
            "temperature": out.get("temperature"),
            "top_p": out.get("top_p"),
            "reasoning": out.get("reasoning"),
            "max_tool_calls": out.get("max_tool_calls"),
        },
    }


def call_openai(prompt: str, api_key: str) -> tuple[dict, dict]:
    body = openai_request(prompt)
    out = _post(OPENAI_URL, {"Authorization": f"Bearer {api_key}"}, body)
    return body, parse_openai(out)


# --- Gemini -----------------------------------------------------------------------------


def gemini_request(prompt: str) -> dict:
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
    if GEMINI_GROUNDING:
        body["tools"] = [{"google_search": {}}]
    return body


def parse_gemini(out: dict) -> dict:
    cand = (out.get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []))
    gm = cand.get("groundingMetadata") or {}
    citations = [
        c["web"]["uri"] for c in gm.get("groundingChunks", []) if c.get("web", {}).get("uri")
    ]
    searches = len(gm.get("webSearchQueries") or [])
    usage = out.get("usageMetadata") or {}
    input_tokens = usage.get("promptTokenCount", 0) or 0
    # Thinking tokens are billed as output.
    output_tokens = (usage.get("candidatesTokenCount", 0) or 0) + (
        usage.get("thoughtsTokenCount", 0) or 0
    )
    p = GEMINI_PRICE
    cost = (input_tokens * p["input"] + output_tokens * p["output"]) / 1e6 + searches * p["search"]
    return {
        "model_returned": out.get("modelVersion"),
        "response_text": text,
        "citations": citations,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "search_calls": searches,
        "est_cost_usd": round(cost, 6),
        "effective_params": {"finish_reason": cand.get("finishReason")},
    }


def call_gemini(prompt: str, api_key: str) -> tuple[dict, dict]:
    body = gemini_request(prompt)
    out = _post(GEMINI_URL, {"x-goog-api-key": api_key}, body)
    return body, parse_gemini(out)


ENGINES = {
    "openai": {
        "model": OPENAI_MODEL,
        "call": call_openai,
        "key_param": "/llm-panel/OPENAI_API_KEY",
    },
    "gemini": {
        "model": GEMINI_MODEL,
        "call": call_gemini,
        "key_param": "/llm-panel/GEMINI_API_KEY",
    },
}

"""Daily panel collector (SPEC §3).

Runs every prompt x sample against each engine, writes one JSONL file per engine to R2,
then the manifest LAST. Failed calls become rows with status = "error", never gaps.
Raises after writing if any engine's error rate is above 10%, so the CloudWatch alarm fires.
"""

import hashlib
import json
import os
import random
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import boto3
import yaml

import engines

PROMPTS_PATH = Path(__file__).with_name("prompts.yaml")
MAX_RETRIES = 3  # retries after the first attempt
BACKOFF_BASE_S = 2.0
WORKERS = {"openai": 8, "gemini": 4}
ERROR_RATE_LIMIT = 0.10
# Stop starting new calls this long before the Lambda timeout, so files still get written.
DEADLINE_MARGIN_S = 90


def load_prompts(path: Path = PROMPTS_PATH) -> tuple[dict, str]:
    raw = path.read_bytes()
    return yaml.safe_load(raw), hashlib.sha256(raw).hexdigest()


def get_secret(ssm, name: str) -> str:
    return ssm.get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]


def call_with_retries(call, prompt: str, api_key: str, sleep=time.sleep):
    """Return (request_body, parsed, error_message). Retries only retryable failures."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            body, parsed = call(prompt, api_key)
            if not parsed["response_text"].strip():
                # An empty answer would block the day's audit (SPEC §7); count it as an error.
                return body, parsed, "empty response_text"
            return body, parsed, None
        except engines.PermanentError as e:
            return None, None, str(e)
        except engines.RetryableError as e:
            if attempt == MAX_RETRIES:
                return None, None, f"after {MAX_RETRIES} retries: {e}"
            sleep(BACKOFF_BASE_S * 2**attempt + random.uniform(0, 1))
    raise AssertionError("unreachable")


def make_record(
    base: dict, task: dict, requested_at: datetime, latency_ms: int, body, parsed, error
) -> dict:
    parsed = parsed or {}
    request_params = {"sent": body, "effective": parsed.get("effective_params")}
    return {
        "response_id": str(uuid.uuid4()),
        **base,
        "prompt_id": task["id"],
        "category": task["category"],
        "sample_idx": task["sample_idx"],
        "request_params": json.dumps(request_params, sort_keys=True),
        "requested_at": requested_at.isoformat(),
        "latency_ms": latency_ms,
        "status": "error" if error else "ok",
        "error_message": error,
        "model_returned": parsed.get("model_returned"),
        "response_text": parsed.get("response_text", ""),
        "citations": parsed.get("citations", []),
        "input_tokens": parsed.get("input_tokens", 0),
        "output_tokens": parsed.get("output_tokens", 0),
        "search_calls": parsed.get("search_calls", 0),
        "est_cost_usd": parsed.get("est_cost_usd", 0.0),
    }


def run_engine(
    engine: str,
    prompts: dict,
    prompt_version: str,
    run_id: str,
    run_date: str,
    api_key: str,
    remaining_s,
    sleep=time.sleep,
) -> list[dict]:
    spec = engines.ENGINES[engine]
    base = {
        "run_id": run_id,
        "run_date": run_date,
        "engine": engine,
        "model_requested": spec["model"],
        "prompt_version": prompt_version,
    }
    tasks = [
        {**p, "sample_idx": i}
        for p in prompts["prompts"]
        for i in range(prompts["samples_per_prompt"])
    ]

    def one(task):
        requested_at = datetime.now(UTC)
        if remaining_s() < DEADLINE_MARGIN_S:
            return make_record(
                base, task, requested_at, 0, None, None, "skipped: Lambda deadline near"
            )
        t0 = time.monotonic()
        body, parsed, error = call_with_retries(spec["call"], task["text"], api_key, sleep)
        latency_ms = int((time.monotonic() - t0) * 1000)
        return make_record(base, task, requested_at, latency_ms, body, parsed, error)

    with ThreadPoolExecutor(WORKERS[engine]) as pool:
        return list(pool.map(one, tasks))


def to_jsonl(records: list[dict]) -> bytes:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records).encode()


def collect(event: dict, *, ssm, s3, bucket: str, remaining_s, now=None, sleep=time.sleep) -> dict:
    now = now or datetime.now(UTC)
    run_date = now.date().isoformat()
    run_id = now.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    selected = event.get("engines") or list(engines.ENGINES)
    unknown = set(selected) - set(engines.ENGINES)
    if unknown:
        raise ValueError(f"unknown engines: {sorted(unknown)}")

    prompts, prompt_version = load_prompts()
    prefix = f"raw/panel/dt={run_date}/run={run_id}"

    def collect_engine(engine):
        api_key = get_secret(ssm, engines.ENGINES[engine]["key_param"])
        return engine, run_engine(
            engine, prompts, prompt_version, run_id, run_date, api_key, remaining_s, sleep
        )

    # Engines run side by side, each with its own worker pool.
    with ThreadPoolExecutor(len(selected)) as pool:
        results = list(pool.map(collect_engine, selected))

    files, error_rates = [], {}
    for engine, records in results:
        key = f"{prefix}/{engine}.jsonl"
        s3.put_object(
            Bucket=bucket, Key=key, Body=to_jsonl(records), ContentType="application/x-ndjson"
        )
        errors = sum(r["status"] == "error" for r in records)
        error_rates[engine] = errors / len(records)
        files.append(
            {
                "engine": engine,
                "key": key,
                "rows": len(records),
                "errors": errors,
                "est_cost_usd": round(sum(r["est_cost_usd"] for r in records), 4),
            }
        )

    manifest = {
        "run_id": run_id,
        "run_date": run_date,
        "prompt_version": prompt_version,
        "samples_per_prompt": prompts["samples_per_prompt"],
        "prompt_count": len(prompts["prompts"]),
        "started_at": now.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "files": files,
    }
    # Written LAST: the sensor only loads runs that have a manifest (SPEC §3).
    s3.put_object(
        Bucket=bucket,
        Key=f"{prefix}/_manifest.json",
        Body=json.dumps(manifest, indent=2).encode(),
        ContentType="application/json",
    )

    too_high = {e: round(r, 3) for e, r in error_rates.items() if r > ERROR_RATE_LIMIT}
    if too_high:
        # Deliberate failure after the files are saved, so the Lambda Errors alarm fires.
        raise RuntimeError(f"error rate above {ERROR_RATE_LIMIT:.0%} in run {run_id}: {too_high}")
    return manifest


def lambda_handler(event, context):
    ssm = boto3.client("ssm")
    s3 = boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT_URL"],
        aws_access_key_id=get_secret(ssm, "/llm-panel/R2_ACCESS_KEY_ID"),
        aws_secret_access_key=get_secret(ssm, "/llm-panel/R2_SECRET_ACCESS_KEY"),
        region_name="auto",
    )
    manifest = collect(
        event or {},
        ssm=ssm,
        s3=s3,
        bucket=os.environ["R2_BUCKET"],
        remaining_s=lambda: context.get_remaining_time_in_millis() / 1000,
    )
    summary = {k: manifest[k] for k in ("run_id", "run_date", "prompt_version")}
    summary["files"] = manifest["files"]
    print(json.dumps(summary))
    return summary

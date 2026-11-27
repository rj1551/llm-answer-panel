# SPEC: llm-answer-panel
 
How each part works, why it was chosen, and what was rejected. Decisions still open are in section 12, each with a suggested default. Change anything you disagree with, and log the change in DECISIONS.md.
 
---
 
## 1. What this project shows
 
**The question:** how much of the uncertainty in a brand's mention rate comes from rerun randomness (asking the same wording again), and how much from which wording was asked? So how many distinct prompts and how many reruns does a trustworthy number need?

**The estimand:** a brand's mention rate across the questions real people ask in a category. Each real person asks once, so the population being sampled is *prompts*, and reruns are a second, smaller source of noise. The split between the two is the intraclass correlation ρ (law of total variance): if ρ is high, reruns are wasted budget and wording drives the result.

**Why it matters:** AI-visibility tools sell a number like "ChatGPT mentions your brand in 40% of answers," usually from a fixed, short prompt list run a few times. LLM answers are random and wording-sensitive, so such a number is mostly noise. The pipeline measures both sources of that noise directly.

**Framing:** results describe specific models called through the official APIs (e.g. "OpenAI model X via the API, with web search"), not the ChatGPT or Gemini consumer apps, which add their own system prompts, memory and personalization.
 
**The planned findings:**
 
1. **The sample-size curve.** Use the Wilson score interval to show how a mention rate's 95% confidence interval narrows as samples grow. One prompt with 5 samples gives an interval tens of points wide. Pinning a rate within ±5 points takes about 385 samples at p = 0.5, from n = z²·p(1−p)/E² = 1.96²·0.25/0.05² ≈ 384. That is the worst case: at p = 0.1 it is about 139. No single prompt-day can get there. Precise estimates require **pooling across prompts and days**, and the analysis shows how much pooling is needed. Wilson assumes independent samples, but samples of one prompt cluster around that prompt's own rate. So every pooled rate also gets a **cluster bootstrap interval** (resample prompts, then days) and an effective sample size n_eff = n / design effect. The gap between the Wilson and cluster intervals is part of the finding. Report ρ per engine and category, and the resulting trade-off: for a fixed budget, how the interval width changes with more prompts versus more reruns.
2. **Real movement vs. noise.** Plot each brand's daily mention rate in a category on a **p-chart**: a control chart whose limits come from the binomial sampling error. Days outside the limits are actual changes, such as a model update. Days inside are noise. Because prompts differ, the counts vary more than binomial, so a plain p-chart would flag too many days. The main chart is a **Laney p′-chart**, which widens the limits by the observed overdispersion, with the plain p-chart beside it for comparison. Count how many days fall outside versus the roughly 0.3% expected by chance.
3. **One WildChat finding.** Measure how often real users of the WildChat chatbot (WildChat-4.8M: free access to OpenAI models through the API, Apr 2023 – Jul 2025, mostly gpt-4o and gpt-4.1-mini) ask for product recommendations, and which brands the answers mention, by category. These answers came from models **without web search**, so they are a separate finding (at most a "pre-search" reference point), never compared directly with panel mention rates. WildChat's main job in the panel is as the source of real prompt wording.
 
**Not in scope:** dashboards, a web app, modeling what *causes* a brand to be mentioned, or scraping consumer chat apps.
 
---
 
## 2. Architecture
 
```
            daily, in AWS (runs even if the laptop is off)
 EventBridge Scheduler ──> Lambda collector ──> OpenAI API + Gemini API
                               │   reads keys from Parameter Store (/llm-panel/*)
                               ▼
                 Cloudflare R2: raw/panel/dt=YYYY-MM-DD/...  (immutable)
                               │
            on the laptop      ▼
 Dagster sensor ──> load day into staging ──> audit checks ──> publish
                                                                  │
 WildChat-4.8M parquet (Hugging Face) ──> Dagster asset ──> ClickHouse raw
                                                                  ▼
                                    dbt: staging ──> intermediate ──> marts
                                                                  ▼
                                    analysis scripts ──> charts in README
```
 
**Why it's split this way:** collecting and processing are separate jobs.
 
- **Collection** has to happen every day, because answers belong to the day they were generated and a missed day can never be backfilled. It runs in the cloud.
- **Processing** can happen whenever the laptop is on. The raw files wait in R2, and the Dagster sensor catches up on any days it missed.
 
| Component | Why | Rejected alternative |
|---|---|---|
| Lambda + EventBridge Scheduler | Runs while the laptop is off, fits the permanent free limits, and is a real AWS serverless pattern | GitHub Actions cron (works, but says nothing about AWS); laptop cron (misses days) |
| Cloudflare R2 | Storage that's free permanently, with no egress fees for the daily download, and it speaks the S3 API | S3: the free credits last 6 months and downloads are billed. Switching is a config change, because the endpoint and bucket come from `.env`. |
| Parameter Store (SecureString) | Free standard tier, encrypted, and the Lambda role can read it | Secrets Manager: $0.40 per secret per month, and its rotation feature isn't needed |
| ClickHouse | Matches the posting's stack; columnar storage suits large scans and aggregations | Snowflake: a possible extra later, running the same models for a cost comparison |
| dbt (dbt-clickhouse) | SQL transformations with tests on each model's grain, as the posting asks | Hand-written SQL scripts |
| Dagster | Asset-based orchestration with sensors and asset checks, as the posting asks | Airflow (heavier for local use) |
 
---
 
## 3. The daily collector (Lambda)
 
**Trigger:** EventBridge Scheduler, once a day (run time: see §12). The schedule has an **end date 21 days after the first run**, so collection stops by itself (about $36 of OpenAI spend). Automatic retries are off: the Scheduler retry policy and the function's async `MaximumRetryAttempts` are both 0, so one bad day can't turn into 3 paid runs. Reruns are manual.
**Region:** us-east-2. **Networking:** no VPC. A VPC would need a NAT gateway, at about $30+ a month.
**Timeout:** Lambda's maximum is 15 minutes, so calls run in parallel through a small thread pool (start with 8 workers). At 150 calls per engine, that should finish in a few minutes.
 
**Inputs, as files in the repo, deployed with the function:**
- `collector/prompts.yaml`: about 30 prompts, each with an `id`, `category` and `text`. Starter prompts first; WildChat-derived prompts replace them in session 6, and the old file is kept in git history.
- `collector/brands.yaml`: brands to track for each category, with aliases (e.g. `HP: [hp, hewlett-packard]`).
 
**Per run:** each prompt × `samples_per_prompt` (a config value, see §12) × 2 engines, so about 300 calls a day.
- **OpenAI:** a current small model with web search turned on (see §12), with the search user location set explicitly to US so results don't depend on where AWS routes the request. Web search costs $10 per 1,000 calls, so about $1.70 a day.
- **Gemini:** Flash-Lite with Google Search grounding, on the free tier. Throttle to stay under the free tier's per-minute and per-day limits. In session 2, check the real limits on the key: if Gemini alone needs more than about 8 minutes, run each engine as its own invocation so throttling can't time out the OpenAI half.
 
**Retries:** up to 3 per call, with exponential backoff. A call that still fails is written as a row with `status = "error"`, never skipped, so the audit checks can count failures.
 
**Output:** one JSONL file per engine per run:
 
```
raw/panel/dt=2026-11-28/run=<run_id>/openai.jsonl
raw/panel/dt=2026-11-28/run=<run_id>/gemini.jsonl
raw/panel/dt=2026-11-28/run=<run_id>/_manifest.json   ← written LAST
```
 
The manifest lists the files and their row counts, and the sensor loads a run only once the manifest exists. That way it never loads a half-written run. A rerun on the same day gets a new `run_id` and never overwrites earlier files: raw data is immutable.
 
**Record schema (one line per API call):**
 
| Field | Type | Notes |
|---|---|---|
| response_id | string | UUID |
| run_id, run_date | string, date | |
| engine | string | `openai` \| `gemini` |
| model_requested, model_returned | string | Comparing the two catches silent model changes |
| prompt_id, prompt_version, category | string | `prompt_version` = SHA-256 of the bundled prompts.yaml content, computed at runtime (the Lambda has no git) |
| sample_idx | int | 0 to `samples_per_prompt` − 1 |
| request_params | string (JSON) | temperature, top_p, system prompt, tool and search settings as sent; a changed default would otherwise be invisible |
| requested_at | timestamp (UTC) | |
| latency_ms | int | |
| status, error_message | string | `ok` \| `error` |
| response_text | string | |
| citations | array of string | URLs returned by the search tool |
| input_tokens, output_tokens, search_calls | int | |
| est_cost_usd | float | From a price table in the code; an estimate, labeled as such |
 
**Least-privilege execution role, defined in the SAM template:** `ssm:GetParameter` on `/llm-panel/*`, `kms:Decrypt` for the Parameter Store key, and permission to write CloudWatch logs. Nothing else. The R2 write token is read from Parameter Store, since IAM can't grant access to Cloudflare.
 
**Alerting:** a CloudWatch alarm on Lambda errors notifies an SNS topic, which emails you. Failed calls become error rows, so a run where every call fails would still succeed and never trigger the alarm. So after writing the manifest, the handler raises an exception on purpose if any engine's error rate is above 10%. The files are already saved, and the alarm fires. A second alarm fires if the Lambda has **fewer than 1 invocation in 26 hours** (missing data counts as breaching), which catches a broken or misconfigured schedule that the error alarm can't see. Disable it after day 21. For manual reruns, the handler takes an optional `engines` list, so a failed engine can be rerun alone.
 
---
 
## 4. Loading and write-audit-publish (laptop)
 
**Sensor:** a Dagster sensor checks R2 every 15 minutes while Dagster is running. For each new `_manifest.json`, it starts one `(run_date, engine)` partition per engine file the manifest lists.
 
**Which run counts:** a day can have more than one run (a timed-out half-run with no manifest, or a manual rerun after a failed audit). The published data for each `(run_date, engine)` is always the **latest complete run** (latest manifest listing that engine). Each engine publishes on its own, so a Gemini outage doesn't block OpenAI's answers.
 
**Write:** first drop that `(run_date, engine)` partition in `staging.panel_responses`, then load the run's JSONL into it. A failed attempt stays in staging until the day is retried, and forever in R2.
 
**Audit:** run the checks in §7 on that run only, including a blocking check that staging holds **exactly one `run_id`** for the day and engine (the duplicate check keys on `run_id`, so two mixed runs would otherwise pass and double n).
 
**Publish:** if every blocking check passes, run ClickHouse `ALTER TABLE raw.panel_responses REPLACE PARTITION (<day>, '<engine>') FROM staging.panel_responses`. That's an atomic swap of that engine's whole day: readers see either the old version or the new one, never a mix. Reloading a day is safe, because it replaces the day instead of duplicating it. If a blocking check fails, nothing is published, the Dagster run fails, and the failed data stays in staging to investigate.
 
**WildChat:** a one-time asset downloads the parquet files from `allenai/WildChat-4.8M` (ODC-BY, non-toxic subset, about 15 GB) into `data/` (not committed) and loads them into `raw.wildchat_conversations`, one partition per file. After loading, plot daily conversation counts and exclude any stretch with obvious bot-driven spikes; record the chosen date window in DECISIONS.md.
 
---
 
## 5. ClickHouse tables
 
| Table | Grain | Engine / ORDER BY / PARTITION BY | Why |
|---|---|---|---|
| `staging.panel_responses` | one row per API call | Same structure as the published table | Must match it exactly for `REPLACE PARTITION` |
| `raw.panel_responses` | one row per API call | MergeTree, `ORDER BY (category, prompt_id, run_id, sample_idx)`, `PARTITION BY (run_date, engine)`; `LowCardinality(String)` for engine, category, status, model_requested, model_returned | Each publish is one atomic swap of one engine's day, so one engine's failure never blocks the other. `run_date` and `engine` are constant within a partition, so they aren't repeated in the sort key; the marts group by category. |
| `raw.wildchat_conversations` | one row per conversation, keyed by `conversation_id` (the first turn's `turn_identifier`) | MergeTree, `ORDER BY (timestamp, conversation_id)`, `PARTITION BY source_file` | Loaded once; time-ordered. `conversation_hash` is not unique (identical conversations share it), so it is kept only as a content hash. One partition per parquet file makes the 15 GB load resumable and each file reloadable. The `header` field (user agent, accept-language) is not loaded; `hashed_ip`, `country` and `language` are kept for per-user English sampling. |
 
Day × engine partitions are fine at this volume (about 42 over the 21-day panel). At production scale you'd partition by month and swap at a finer level. Note that in DECISIONS.md.
 
---
 
## 6. dbt models
 
| Layer | Model | Grain (one row per…) | Main tests |
|---|---|---|---|
| staging | `stg_panel__responses` | API call | `unique(response_id)`; unique on `(run_id, engine, prompt_id, sample_idx)`; `accepted_values(engine, status)` |
| staging | `stg_wildchat__conversations` | conversation | `unique(conversation_id)` |
| staging | `stg_wildchat__turns` | turn (conversation × turn index) | unique on `(conversation_id, turn_index)` |
| intermediate | `int_panel__brand_mentions` | `status = ok` response × tracked brand in its category (error rows excluded, so they never count as "not mentioned") | unique on `(response_id, brand)`; `mentioned` not null |
| intermediate | `int_wildchat__commercial_turns` | user turn, tagged by the intent rules | unique on `(conversation_id, turn_index)` |
| intermediate | `int_wildchat__brand_mentions` | assistant turn × brand | unique on `(conversation_id, turn_index, brand)` |
| marts | `fct_panel_mentions_daily` | day × engine × prompt × brand: n, k, rate, wilson_low, wilson_high | rate between 0 and 1; n ≤ `samples_per_prompt` |
| marts | `fct_panel_category_daily` | day × engine × category × brand, pooled across prompts | Same, plus p-chart and Laney p′ limits |
| marts | `fct_run_costs` | run × engine: calls, tokens, est_cost_usd, error_rate (the one place error rows are counted) | Nothing missing for runs that exist |
| marts | `fct_wildchat_brand_share` | category × brand | Shares sum to 1 per category, within 1e-9 (floating-point sums aren't exact) |
 
**How a mention is detected:** a case-insensitive, whole-word match on a brand or any of its aliases. This is deliberately simple and transparent. Its weaknesses (e.g. "Apple" the fruit) are listed in the README, and its accuracy is measured against hand labels (§8).
 
**One brand list:** `collector/brands.yaml` is the only source. A `make` step generates `dbt/seeds/brands.csv` from it, and CI fails if the two differ, so the collector and the matcher never track different brands.
 
**SQL vs. Python:** the marts hold counts, Wilson intervals and p-chart / Laney p′ limits, all plain SQL. The cluster bootstrap, ρ and n_eff need resampling, so they are computed in `analysis/` (Python) from the marts.
 
**Materialization:** every model is a plain table, rebuilt in full on each `dbt build`. The panel is about 6,300 rows over 21 days, which ClickHouse rebuilds in under a second, and a full rebuild always picks up republished days. A typical "new days only" incremental model would silently keep the old version of a republished day. At production scale you'd use `incremental_strategy='insert_overwrite'` by partition, so republished days get rebuilt; the README says so.
 
---
 
## 7. Data-quality checks
 
| Check | Blocking? | Why |
|---|---|---|
| Schema matches the expected columns and types | **Block** | A change in an API's response format would silently corrupt everything downstream |
| Row count = prompts × samples × engines (±0) | **Block** | Failed calls are written as error rows, so the count must be exact |
| No duplicate `(run_id, engine, prompt_id, sample_idx)` | **Block** | Duplicates inflate n and shrink the confidence intervals |
| Exactly one `run_id` per day and engine in staging | **Block** | Two runs mixed together would each pass the duplicate check and double n |
| Error rate ≤ 10% per engine | **Block** | Above that, the day's rates are unreliable |
| `response_text` not empty when `status = ok` | **Block** | |
| `model_returned` differs from the previous day | Warn | Expected occasionally; mark it on the charts |
| Median response length moves > 50% from the 7-day median | Warn | Often a sign of a model or prompt change |
| Daily est. cost > $3 | Warn | Spending guardrail |
| Freshness: no new run in 36 hours | Warn | The collector may be broken (only seen when Dagster runs; the CloudWatch invocation alarm in §3 covers the rest) |
| Share of `ok` responses with zero citations jumps versus the 7-day median, per engine | Warn | Web search may have silently stopped, so answers would come from model memory |
| `prompt_version` differs from the previous day | Warn | The prompt set changed; the p-chart restarts there, and the change is marked on the charts |
 
---
 
## 8. WildChat analysis
 
**Population:** English user turns (`language`) in the chosen date window (§4). Sampling is **per user** via `hashed_ip`, capped at a few turns per user, so one heavy user can't dominate. Every share states this denominator.
 
1. **Commercial-intent tagging:** keyword and pattern rules on user turns, such as "best … for", "recommend", "which … should I buy", "vs", "alternatives to". **Category rules** sit in the same versioned seed: a turn is "commercial in category X" if it matches an intent rule **and** that category's keyword list (e.g. "laptop", "notebook" → laptops). Commercial turns that match no category count toward the overall share only. Hand labels record the category too.
2. **Validation:** before labeling, write `LABELING.md`: the definition of a commercial question and about five borderline examples, so labels stay consistent from the first to the last. Then draw a stratified random sample of 200 user turns, half tagged by the rules and half not. **You label them by hand**, in a CSV saved as a dbt seed, which Claude Code never fills in. A script reports precision and recall. Precision comes straight from the tagged half. Recall must **weight each half by its size in the population**: the untagged half stands for far more turns, so the naive 200-sample recall would be badly inflated. Report recall with a confidence interval, which will be wide. If precision is under 0.8, revise the rules before reporting the finding.
3. **Brand mentions:** run the same matcher from §6 on the assistant's replies to commercial turns.
4. **Finding:** the share of conversations with a commercial question, and the top brands mentioned per category, with a sample size beside every number.
5. **Deriving the panel prompts (session 6):** automatic filters first: the first user message of a conversation (so it stands alone without earlier context), 5–40 words, matches an intent rule and a category, names no tracked brand (the matcher finds nothing in the prompt), English, per-user cap, near-duplicates removed. Then draw a **random** sample of the number per category set in §12 (about 12, so about 72 in all) from those candidates and read only those. Reject only for a clear, logged reason: personal details, not really a product question, or unreadable. Replace a rejected prompt with the next random draw, never a hand-picked favorite, so the sample stays representative.
 
**Rules:** report aggregate figures only. Never publish raw conversation text, with one stated exception: the panel prompts in `prompts.yaml` are short product questions taken from WildChat. ODC-BY allows redistribution with attribution. Credit WildChat (ODC-BY) in the README and state the exception there.
 
---
 
## 9. Costs and limits
 
| Item | Expected cost |
|---|---|
| OpenAI with web search | ≈ $1.70/day × 21 days ≈ $36 in total; hard spending limit $40/month kept as a safety net (verify it blocks calls, not just alerts) |
| Gemini (free tier) | $0 |
| Lambda, EventBridge Scheduler, Parameter Store, CloudWatch | $0 (permanent free limits) |
| Cloudflare R2 | $0 (under 10 GB) |
| SAM deploy bucket (S3) | Cents at most |
 
Ask before running any job that makes more than 1,000 API calls.
 
---
 
## 10. CI
 
A GitHub Actions workflow runs on every PR: start a ClickHouse service container, `dbt deps`, `dbt build` against small fixture data in `dbt/seeds/ci/`, Python unit tests (brand matcher, Wilson interval, intent rules), and `ruff`. A PR can't merge unless this passes.
 
---
 
## 11. Repo layout
 
```
llm-answer-panel/
├── collector/            Lambda handler, prompts.yaml, brands.yaml, template.yaml (SAM), tests/
├── orchestration/        Dagster project: assets, sensor, checks
├── dbt/                  dbt project: models/{staging,intermediate,marts}, seeds/, tests/
├── analysis/             scripts that build the README charts from marts
├── docker-compose.yml    ClickHouse
├── Makefile              make up / load / build / test
├── .env.example          key names only, no values
├── .github/workflows/ci.yml
├── README.md  SPEC.md  PLAN.md  DECISIONS.md  CLAUDE.md
└── data/                 (gitignored) WildChat parquet
```
 
---
 
## 12. Open decisions (defaults shown; yours to confirm or change)
 
| Decision | Default | What to weigh |
|---|---|---|
| OpenAI model | The current cheapest model that supports web search | Bigger models cost more per token; web search is $10 per 1,000 calls either way |
| Daily run time | 14:00 UTC (9 am ET) | Spread the time across days, or keep it fixed? A fixed time keeps time of day from adding noise. |
| Categories (about 6) | Laptops, running shoes, CRM software, project-management tools, credit cards, coffee makers | Mix consumer and B2B; each needs at least 5 brands people really compare |
| Samples per prompt | 5 | More samples per prompt = better per-prompt estimates but higher cost; more prompts = broader coverage |
| Web search on Gemini | On (grounding) | Off would compare answers from the model's memory alone, an interesting variant |
| Prompt wording | Neutral, with no brand named in the prompt | Prompts that name a brand ("X vs Y") would inflate those brands' mentions |
 
---
 
## 13. How to make this yours before building
 
Start the first Claude Code session in plan mode with: *"Read SPEC.md. Walk me through it one section at a time and explain the reasoning. After each section, ask me a question that checks I understood, and challenge anything that looks wrong or over-engineered. Then help me decide section 12. Record every change in DECISIONS.md."*
 
You're done when you can explain three things without notes: why collection and processing are separate, why write-audit-publish uses a partition swap, and why one prompt-day's mention rate means almost nothing.
 
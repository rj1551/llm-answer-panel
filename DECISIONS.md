# DECISIONS

One line per design choice or change to SPEC.md, with one line of why.

| Date | Section | Decision | Why |
|---|---|---|---|
| 2026-11-25 | §1 | Frame results as "OpenAI/Gemini model X via the API", not "ChatGPT"/"Gemini app" | The API with web search isn't the consumer app (no app system prompt, memory or personalization), so claiming the app would overstate what we measured |
| 2026-11-25 | §1 | Describe WildChat as GPT-3.5/GPT-4 chatbot users via the OpenAI API (2023–2024), not "ChatGPT users" | Same honesty point: WildChat was a separate chatbot built on the API, and its data is older than the panel's |
| 2026-11-25 | §1, §6 | Report a cluster bootstrap interval (prompts, then days) and n_eff next to every pooled Wilson interval | Samples of one prompt cluster around that prompt's own rate, so Wilson on pooled n is too narrow |
| 2026-11-25 | §1, §6 | Main control chart is a Laney p′-chart, with the plain p-chart shown for comparison | Differences between prompts cause overdispersion, so plain binomial limits would flag noise as real movement |
| 2026-11-25 | §1 | State that n ≈ 385 is the worst case (p = 0.5); about 139 at p = 0.1 | Stops readers from treating 385 as a universal number |
| 2026-11-25 | §1 | Reframe the research question: split mention-rate uncertainty into rerun noise and wording noise (ρ), with the estimand = rate across real prompts in a category | Real users ask once, so the population being sampled is prompts; reruns are only the second source of noise, and the ρ split tells vendors where to spend budget |
| 2026-11-25 | §1 | WildChat brand shares are a separate finding, never compared with panel rates; WildChat's main role is prompt wording | WildChat answers came from 2023–24 models without web search, so they differ from the panel in model, year and search |
| 2026-11-25 | §1, §2, §4 | Use WildChat-4.8M (non-toxic, ODC-BY, through Jul 2025) instead of WildChat-1M | Same license, but mostly gpt-4o/gpt-4.1-mini instead of 2023 models, plus `language`, `country` and `hashed_ip` for English-only, per-user prompt sampling |
| 2026-11-25 | §4 | After loading WildChat, inspect daily conversation counts and exclude bot-driven spikes | A paper using 4.8M found irregular traffic spikes late in the period that would skew prompt sampling |
| 2026-11-25 | §3 | Raise an exception after writing files if any engine's error rate > 10% | Failed calls are error rows, so Lambda's Errors metric would never fire on a fully failed run |
| 2026-11-25 | §3 | Scheduler retry policy and Lambda async MaximumRetryAttempts both set to 0 | Default async retries would turn one bad day (now a deliberate exception) into up to 3 paid runs |
| 2026-11-25 | §3 | Add a `request_params` JSON field and set the OpenAI web-search user location to US | The project measures randomness, so sampling settings must be recorded; search results vary by location |
| 2026-11-25 | §3 | `prompt_version` = SHA-256 of prompts.yaml content instead of the git hash | The deployed Lambda has no git; a content hash is exact and needs nothing at build time |
| 2026-11-25 | §3, §6 | `samples_per_prompt` is a config value; sample_idx range and the n test use it | §12 may change it from 5, and hard-coded 5s would break silently |
| 2026-11-25 | §3 | Measure Gemini's free-tier limits in session 2; split into per-engine invocations if Gemini needs > ~8 min | Throttled grounding calls could push one combined run past the 15-minute Lambda limit |
| 2026-11-26 | §3, §9 | Collect for 21 days, enforced by an end date on the EventBridge schedule; keep the $40 cap | 31 days × $1.70 ≈ $53 would hit the $40 cap around day 23; 21 days (≈ $36) is enough for standard p′-chart limits and lands before the outreach follow-up |
| 2026-11-27 | §4 | The published day is the latest complete run; add a blocking check for exactly one `run_id` per day in staging | Days can have several runs, and the duplicate check keys on `run_id`, so mixed runs would silently double n |
| 2026-11-27 | §4 | The write step drops the day's staging partition before loading | Otherwise a retry would insert on top of the failed attempt's rows |
| 2026-11-27 | §4, §5 | WildChat table gets a `source_file` column and `PARTITION BY source_file` | §4 and §5 disagreed; per-file partitions make the 15 GB load resumable and each file reloadable |
| 2026-11-27 | §5 | WildChat key is `conversation_id` = first turn's `turn_identifier`; `conversation_hash` kept only as a content hash | The 4.8M card says `conversation_hash` is not unique |
| 2026-11-27 | §5 | Don't load WildChat `header`; keep `hashed_ip`, `country`, `language` | Load only the personal data the analysis needs |
| 2026-11-27 | §5 | Panel `ORDER BY (engine, category, prompt_id, run_id, sample_idx)`; `LowCardinality(String)` for low-distinct columns | `run_date` is constant within a daily partition, and the marts group by engine and category |
| 2026-11-27 | §5 | Daily partitions for the panel; at production scale, partition by month and swap at a finer level | About 21–365 partitions is fine here; thousands of small partitions would slow merges and metadata |
| 2026-11-27 | §6 | All WildChat models keyed on `conversation_id` instead of `conversation_hash` | Applies the §5 key decision; hash-based unique tests would fail on identical conversations |
| 2026-11-27 | §6 | Every model is a full-refresh table, not incremental; README names `insert_overwrite` by partition as the at-scale approach | About 6,300 rows rebuild in under a second, and "new days only" incremental models would miss republished days |
| 2026-11-27 | §6 | Brand mentions use only `status = ok` responses; errors are counted only in `fct_run_costs` | Otherwise a failed call would count as "brand not mentioned" and bias rates down |
| 2026-11-27 | §6 | `collector/brands.yaml` is the single brand list; `make` generates `dbt/seeds/brands.csv` and CI checks they match | Two hand-kept lists would drift, and the matcher would track different brands than the collector |
| 2026-11-27 | §1, §6 | Cluster bootstrap, ρ and n_eff are computed in `analysis/` (Python), not in dbt marts; drop the `n_eff ≤ n` mart test | Resampling is awkward in SQL; the marts keep counts, Wilson and control-chart limits |
| 2026-11-27 | §6 | WildChat brand-share test allows a 1e-9 tolerance on the sum | Floating-point sums come out as 0.9999999, which an exact test would fail |
| 2026-11-27 | §3, §4, §5, §7 | Partition the panel by `(run_date, engine)`; the run rules and the one-`run_id` check apply per day and engine; manual reruns can target one engine | With a whole-day partition, one engine's error rate would block the other's good data, and 21 days leaves little room to lose any |
| 2026-11-27 | §5 | Panel `ORDER BY (category, prompt_id, run_id, sample_idx)` | `engine` is now constant within a partition, like `run_date` |
| 2026-11-27 | §7 | Warn when the share of zero-citation `ok` responses jumps, per engine | If web search silently stops, the panel measures model memory instead |
| 2026-11-27 | §7 | Warn when `prompt_version` changes; restart the p-chart there and mark the charts | A changed prompt set would otherwise look like a change in the model |
| 2026-11-27 | §3, §7 | CloudWatch alarm on < 1 Lambda invocation in 26 h (missing data breaches); disable after day 21 | The error alarm can't see a run that never happens, and Dagster freshness only runs when the laptop is on |
| 2026-11-27 | §8 | Recall is weighted by each stratum's population size and reported with a CI; precision comes from the tagged stratum | The 50/50 sample over-represents tagged turns, so naive recall would be inflated (e.g. 98% vs. a true ~29%) |
| 2026-11-27 | §8 | Write `LABELING.md` (definition plus borderline examples) before hand-labeling | Without a written rule, borderline labels drift between the first and the last example |
| 2026-11-27 | §8 | WildChat population = English user turns in the chosen window, sampled per user (`hashed_ip`) with a per-user cap | Stops one heavy user dominating, and makes every share's denominator explicit |
| 2026-11-27 | §8 | Category keyword rules in the intent seed; "commercial in category X" = intent rule and category keywords both match | Finding 3 and the session-6 prompt selection both need a category, and nothing assigned one |
| 2026-11-27 | §8 | Panel prompts: automatic filters, then a random draw per category; read only the drawn ~72 and reject only for logged reasons | Reading all of WildChat is impossible, and hand-picking favorites would bias the prompt sample |
| 2026-11-27 | §8 | State one exception to "never publish conversation text": the short WildChat product questions in `prompts.yaml` | ODC-BY allows it, the risk is negligible for short product questions, and the spec contradicted itself otherwise |
| 2026-11-27 | §9 | Treat $1.70/day as an estimate; measure the real spend after the first manual run and set the final budget in §12 | Search-result content is billed as input tokens on top of the per-search fee, so the real figure may be ≈ $2/day (≈ $42) |
| 2026-11-27 | §9 | Dedicated OpenAI project and key with "Enforce a hard limit" on (already done) | Budgets are alert-only unless enforcement is on; a separate project keeps other usage out of the cap |
| 2026-11-27 | §9 | The schedule is deployed disabled; the user enables it after checking the first run's cost | 21 days ≈ 6,300 calls exceeds the CLAUDE.md "ask before 1,000 calls" line |
| 2026-11-27 | §9 | Confirm AWS always-free limits and the Gemini grounding quota in session 2; README notes Google's free-tier data use | AWS changed its free plan in July 2025, and Gemini's free-tier terms differ from the paid tier |
| 2026-11-27 | §2 | Reject GitHub Actions cron for collection because scheduled workflows can be delayed, skipped or auto-disabled | A technical reason beats "says nothing about AWS", and missed days can't be recovered |
| 2026-11-27 | §10 | Add `cfn-lint`, `dagster definitions validate` and the brands sync check to CI | CI otherwise tested only SQL and Python, not the deploy template or the Dagster code |
| 2026-11-27 | §10, PLAN | Make the repo public in session 7 (after gitleaks), then add branch protection | Free GitHub only enforces branch protection on public repos, and session 7's "PR is blocked" test needs it |
| 2026-11-27 | §11 | Layout lists LABELING.md, generated brands.csv, CI fixtures and analysis/tests | Keeps the layout in sync with the §6 and §8 decisions; the statistics code needs tests too |
| 2026-11-27 | §12 | OpenAI model: cheapest current mini with Responses `web_search`, pinned to a dated snapshot; confirm in session 2 | The per-search fee dominates cost; a pinned snapshot keeps `model_returned` stable |
| 2026-11-27 | §12 | Run time fixed at 14:00 UTC | Stops time of day adding noise |
| 2026-11-27 | §12 | Categories chosen by data: from a shortlist of 8, keep the 6 with the most filtered WildChat candidate prompts (session 5) | Prompts must come from real questions; credit cards dropped from the default (US-only brands, hedged answers, ambiguous names) |
| 2026-11-27 | §12 | Ambiguous brand names use multiword or case-sensitive aliases only | Whole-word matching on "On" or "Monday" would match ordinary words |
| 2026-11-27 | §3, §12 | 12 prompts per category × 2 samples (144 calls per engine per day) | Distinct prompts are the bottleneck; 2 samples is the minimum that measures ρ |
| 2026-11-27 | §9, §12 | If measured cost > ≈ $1.80/day, raise the hard limit to $50 instead of cutting prompts | About $10 more in the worst case, versus losing the scarcest input |
| 2026-11-27 | §3, §12, PLAN | Enable the 21-day schedule after session 6; earlier runs are manual tests, excluded from analysis | All 21 days share one prompt set, so the p-chart never restarts |
| 2026-11-27 | §12 | Gemini web search on; prompt wording neutral with no brand named | Keeps the engines comparable, and brand-naming prompts would inflate mentions |
| 2026-11-27 | §11, session 1 | ClickHouse image pinned to `clickhouse/clickhouse-server:25.8` (LTS) | A floating `latest` tag could change SQL behaviour between sessions |
| 2026-11-27 | §11, session 1 | Expose only the HTTP port 8123, bound to 127.0.0.1 | dbt-clickhouse and clickhouse-connect both use HTTP; nothing else should reach the database |
| 2026-11-27 | §4, §5, session 1 | An init script creates the `raw` and `staging` databases; dbt models build into `analytics` | Loaders and the publish swap need both databases to exist; keeping dbt output separate stops a model from overwriting loaded data |
| 2026-11-27 | §11, session 1 | ClickHouse settings default to local values (user `panel`) in Compose, dbt and Dagster; `.env` overrides them | `make up` works before any key is set, and all three tools share one set of names |
| 2026-11-27 | §11, session 1 | One root venv and `pyproject.toml` with exact pins for dbt, Dagster and the ClickHouse client | Their dependencies overlap; one pinned environment avoids conflicts and drift |
| 2026-11-27 | §11, session 1 | `make` commands run through `dotenv run --no-override` | dbt doesn't read `.env` itself; `--no-override` lets a variable set in the shell win for one-off runs |
| 2026-11-27 | §11, session 1 | `dbt/profiles.yml` is committed; it holds only `env_var()` lookups | Anyone cloning the repo (and CI) can run dbt without building a profile by hand |
| 2026-11-27 | §11, session 1 | `DAGSTER_HOME` = `.dagster_home/` in the repo (gitignored) | Run history survives restarts of `dagster dev` instead of living in a temporary folder |
| 2026-11-27 | §11, session 1 | Live ClickHouse test is opt-in (`make test-live`); `make test` and `make validate` work offline | CI and quick checks shouldn't need a running server |
| 2026-11-27 | §12 | Delete the leftover pre-decision §12 table from SPEC.md | It still said 5 samples per prompt and listed credit cards, contradicting the settled §12 |
| 2026-11-27 | §3, session 2 | Deploy from the laptop with `aws login` (short-lived console-session credentials), not `aws configure` access keys | No long-lived access key sits on disk, so a leaked laptop or file can't give lasting access to the account |
| 2026-11-27 | §3, §12 | OpenAI model = `gpt-6-luna` | Cheapest current (non-deprecated) model with `web_search`; `gpt-5.4-mini`, the only current mini with a snapshot, would cost ≈ $67 over 21 days |
| 2026-11-27 | §3, §12 | Accept that `gpt-6-luna` has no dated snapshot; `model_returned` per row plus the §7 warning covers it | No pinnable version exists for any affordable current model |
| 2026-11-27 | §3, §9 | OpenAI requests set `max_tool_calls: 1` | Uncapped, 8 of 10 test answers searched twice (≈ $69 for 21 days); capped ≈ $34, and every answer gets the same search budget |
| 2026-11-27 | §3 | `search_calls` = `tool_usage.web_search.num_requests`, not a count of `web_search_call` items | With the cap, a blocked `open_page` item still appears in the output but isn't billed |
| 2026-11-27 | §3 | Reasoning effort `medium` and `store: false` sent explicitly | Pins today's default so a silent default change can't alter answers; responses aren't kept on OpenAI's side |
| 2026-11-27 | §3 | `request_params` holds both what was sent and the effective values the API reports (temperature, top_p, reasoning) | Reasoning models don't accept temperature, so the only way to record it is from the response |
| 2026-11-27 | §3, §12 | Gemini grounding needs the paid tier; decision on paid vs. grounding off is open | Every free-tier grounded call returned 429 and 2.5 Flash-Lite is closed to new users (tested 2026-11-27) |
| 2026-11-27 | §3 | Gemini `est_cost_usd` charges every search query at list price ($0.014), ignoring the 5,000 free per month | An estimate that errs high is safer for the cost guardrail |
| 2026-11-27 | §3 | Call both APIs with plain HTTP (urllib), not the vendor SDKs | The recorded request is exactly what was sent, and the package has no compiled dependencies to break across architectures |
| 2026-11-27 | §3 | Retry only 429, 5xx and network errors; 4xx fail at once | Retrying a bad request or bad key costs time and fails the same way |
| 2026-11-27 | §3, §7 | An empty `response_text` is written as an error row | Otherwise one empty answer would block the whole day in the audit instead of counting toward the 10% error rate |
| 2026-11-27 | §3 | Stop starting calls 90 s before the Lambda timeout; the rest become `skipped` error rows | The files and manifest still get written, the row count stays exact, and the error alarm fires |
| 2026-11-27 | §3 | Engines run in parallel threads, 8 workers for OpenAI and 4 for Gemini | Whole run ≈ 4 min measured per-call latency (10–15 s); Gemini gets fewer workers to stay under its rate limits |
| 2026-11-27 | §3, §11 | Lambda code lives in `collector/src/`; `brands.yaml` arrives in session 5 | Keeps tests and the template out of the deployed zip; the collector never reads brands, and the categories aren't final yet |
| 2026-11-27 | §3 | Starter prompts use the first 6 shortlist categories, 12 neutral questions each | Same shape as the final panel (72 × 2), so the manual runs measure real cost and duration |
| 2026-11-27 | §3 | R2 endpoint, bucket and alert email are deploy-time parameters read from `.env`; none are in the repo | The repo will be public, and Parameter Store is for secrets |
| 2026-11-27 | §3 | Lambda on python3.12, x86_64, 512 MB, 30-day log retention | Matches the laptop's Python so `sam build` needs no container; logs can't pile up costs |
| 2026-11-27 | §3 | `kms:Decrypt` limited by `kms:ViaService = ssm` | The role can decrypt only through Parameter Store, never a key directly |
| 2026-11-27 | §3 | One `CollectionEnabled` parameter turns on both the schedule and the missing-run alarm's actions; the end date is a parameter set at enable time | The missing-run alarm would email every day while the schedule is off; the end date depends on the first scheduled day |
| 2026-11-27 | §3 | `make invoke` runs synchronously with `AWS_MAX_ATTEMPTS=1` and a 960 s read timeout | The CLI's default 60 s timeout would retry and start a second paid run |
| 2026-11-27 | §3, §9, §12 | Gemini runs on the paid tier with grounding on, AI Studio spend cap $15 | Measured 1.6 queries per answer (10 calls): ≈ $8–13 for the panel, and it keeps both engines searching as §12 decided |
| 2026-11-27 | §3, §7 | Accept that Gemini skips search on some answers (2 of 10 in the test); don't force it | The API has no switch to force a search; the §7 zero-citation warning tracks the share per engine |
| 2026-11-27 | §7 (open) | The $3/day est-cost warning will fire every day, because Gemini's estimate charges every query at list price (≈ $3.60/day) | Settle in session 6: per-engine thresholds, or count the free 5,000 per month in the estimate |
| 2026-11-27 | §9, §12 | OpenAI budget stays at the $40 hard limit | Real spend on the first test day was $1.77 including ≈ $0.17 of test calls, so ≈ $1.60 per panel run, under the $1.80 trigger for raising it |
| 2026-11-27 | §9 | Raise the Gemini AI Studio cap from $15 to $20 before enabling the schedule | The full Lambda run measured 1.76 queries per answer, so a panel inside one billing month costs ≈ $16 |
| 2026-11-27 | §7, §8 | Note for the analysis: Gemini skipped search on 9 of 24 project-management answers, versus 0–3 of 24 elsewhere | Search use differs by category, so Gemini's PM mention rates partly reflect model memory; report the share alongside them |

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

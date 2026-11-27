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

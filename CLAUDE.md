# LLM answer panel
Portfolio project: Dagster + dbt + ClickHouse pipeline on WildChat and a
daily LLM prompt panel.
Read SPEC.md before any task. Log every design choice in DECISIONS.md
with one line of why.
## Rules
- Never read, print or edit .env. Code loads keys at runtime with python-
dotenv.
- Use official APIs only. Never scrape consumer chat apps.
- Raw data in R2 is immutable: write new dated files, never overwrite.
The Lambda never runs in a VPC. All AWS resources live in us-east-2, next
to the Parameter Store keys.
- Every new model gets dbt tests on its grain. Every new asset gets an
asset check.
- Respect the cost caps in SPEC.md. Ask before anything that sends more
than 1,000 API calls.
- Small commits, one feature at a time. Run the tests before saying
something works.
"""Dagster entry point. Assets, the R2 sensor and asset checks arrive in later sessions."""

from dagster import Definitions
from dotenv import load_dotenv

from orchestration.resources import clickhouse_from_env

load_dotenv()

defs = Definitions(
    resources={"clickhouse": clickhouse_from_env()},
)

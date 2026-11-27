import os

import pytest

from orchestration.definitions import defs
from orchestration.resources import clickhouse_from_env


def test_definitions_load():
    defs.resolve_all_job_defs()
    assert "clickhouse" in defs.resources


@pytest.mark.skipif(
    os.getenv("CLICKHOUSE_LIVE") != "1", reason="set CLICKHOUSE_LIVE=1 with ClickHouse running"
)
def test_clickhouse_has_panel_databases():
    client = clickhouse_from_env().get_client()
    assert client.command("SELECT 1") == 1
    databases = set(client.query("SHOW DATABASES").result_columns[0])
    assert {"raw", "staging"} <= databases

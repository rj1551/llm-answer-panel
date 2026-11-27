"""Shared Dagster resources."""

import os

import clickhouse_connect
from clickhouse_connect.driver.client import Client
from dagster import ConfigurableResource


class ClickHouseResource(ConfigurableResource):
    """Connection to the local ClickHouse server over HTTP."""

    host: str
    port: int
    user: str
    password: str

    def get_client(self) -> Client:
        return clickhouse_connect.get_client(
            host=self.host, port=self.port, username=self.user, password=self.password
        )


def clickhouse_from_env() -> ClickHouseResource:
    """Build the resource from .env, with the same defaults as docker-compose.yml."""
    return ClickHouseResource(
        host=os.getenv("CLICKHOUSE_HOST", "localhost"),
        port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
        user=os.getenv("CLICKHOUSE_USER", "panel"),
        password=os.getenv("CLICKHOUSE_PASSWORD", "panel_local"),
    )

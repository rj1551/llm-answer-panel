-- Runs once, when the ClickHouse volume is first created.
-- raw:     published data (panel after the audit, WildChat as loaded)
-- staging: panel days waiting for the audit (write-audit-publish, SPEC §4)
-- Tables are created by the loading assets in later sessions.
CREATE DATABASE IF NOT EXISTS raw;
CREATE DATABASE IF NOT EXISTS staging;

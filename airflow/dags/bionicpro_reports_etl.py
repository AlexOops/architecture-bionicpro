from __future__ import annotations

from datetime import datetime

import clickhouse_connect
import psycopg2
from airflow.decorators import dag, task


SOURCE_DB_CONFIG = {
    "host": "source_db",
    "port": 5432,
    "dbname": "bionicpro_source",
    "user": "bionicpro",
    "password": "bionicpro",
}

CLICKHOUSE_CONFIG = {
    "host": "clickhouse",
    "port": 8123,
    "username": "bionicpro",
    "password": "bionicpro",
}


@dag(
    dag_id="bionicpro_reports_etl",
    description="Prepare BionicPRO user reports mart from CRM and telemetry data",
    schedule="0 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["bionicpro", "reports", "etl"],
)
def bionicpro_reports_etl():
    @task
    def prepare_clickhouse_schema() -> None:
        client = clickhouse_connect.get_client(**CLICKHOUSE_CONFIG)

        client.command("CREATE DATABASE IF NOT EXISTS reports")

        client.command(
            """
            CREATE TABLE IF NOT EXISTS reports.user_report_daily
            (
                username String,
                full_name String,
                prosthesis_id String,
                serial_number String,
                report_date Date,
                events_count UInt64,
                avg_response_time_ms Float64,
                avg_battery_level Float64,
                avg_signal_quality Float64,
                total_movements UInt64,
                period_started_at DateTime,
                period_finished_at DateTime,
                etl_loaded_at DateTime
            )
            ENGINE = ReplacingMergeTree(etl_loaded_at)
            ORDER BY (username, report_date, prosthesis_id)
            """
        )

    @task
    def build_user_report_mart() -> int:
        pg_conn = psycopg2.connect(**SOURCE_DB_CONFIG)
        ch_client = clickhouse_connect.get_client(**CLICKHOUSE_CONFIG)

        query = """
            SELECT
                c.username,
                c.full_name,
                p.prosthesis_id,
                p.serial_number,
                DATE(t.event_ts) AS report_date,
                COUNT(*) AS events_count,
                AVG(t.response_time_ms)::float AS avg_response_time_ms,
                AVG(t.battery_level)::float AS avg_battery_level,
                AVG(t.signal_quality)::float AS avg_signal_quality,
                SUM(t.movement_count)::bigint AS total_movements,
                MIN(t.event_ts) AS period_started_at,
                MAX(t.event_ts) AS period_finished_at
            FROM telemetry_events t
            JOIN prostheses p ON p.prosthesis_id = t.prosthesis_id
            JOIN crm_clients c ON c.user_id = p.user_id
            GROUP BY
                c.username,
                c.full_name,
                p.prosthesis_id,
                p.serial_number,
                DATE(t.event_ts)
            ORDER BY c.username, report_date, p.prosthesis_id
        """

        with pg_conn:
            with pg_conn.cursor() as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()

        ch_client.command("TRUNCATE TABLE reports.user_report_daily")

        if not rows:
            return 0

        etl_loaded_at = datetime.utcnow()

        prepared_rows = [
            (
                row[0],
                row[1],
                row[2],
                row[3],
                row[4],
                int(row[5]),
                float(row[6]),
                float(row[7]),
                float(row[8]),
                int(row[9]),
                row[10],
                row[11],
                etl_loaded_at,
            )
            for row in rows
        ]

        ch_client.insert(
            "reports.user_report_daily",
            prepared_rows,
            column_names=[
                "username",
                "full_name",
                "prosthesis_id",
                "serial_number",
                "report_date",
                "events_count",
                "avg_response_time_ms",
                "avg_battery_level",
                "avg_signal_quality",
                "total_movements",
                "period_started_at",
                "period_finished_at",
                "etl_loaded_at",
            ],
        )

        return len(prepared_rows)

    prepare_clickhouse_schema() >> build_user_report_mart()


bionicpro_reports_etl()

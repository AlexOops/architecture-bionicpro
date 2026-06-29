from __future__ import annotations

import os
from datetime import date
from typing import Any

import clickhouse_connect
import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from jwt import PyJWKClient


KEYCLOAK_INTERNAL_URL = os.getenv("KEYCLOAK_INTERNAL_URL", "http://keycloak:8080")
KEYCLOAK_ISSUER = os.getenv(
    "KEYCLOAK_ISSUER",
    "http://localhost:8080/realms/reports-realm",
)
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "reports-realm")
KEYCLOAK_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "reports-frontend")

CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "clickhouse")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "bionicpro")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "bionicpro")

JWKS_URL = (
    f"{KEYCLOAK_INTERNAL_URL}/realms/{KEYCLOAK_REALM}"
    "/protocol/openid-connect/certs"
)

app = FastAPI(title="BionicPRO Reports API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

_jwks_client = PyJWKClient(JWKS_URL)


def to_iso(value: Any) -> str | None:
    if value is None:
        return None

    if hasattr(value, "isoformat"):
        return value.isoformat()

    return str(value)


def get_clickhouse_client():
    return clickhouse_connect.get_client(
        host=CLICKHOUSE_HOST,
        port=CLICKHOUSE_PORT,
        username=CLICKHOUSE_USER,
        password=CLICKHOUSE_PASSWORD,
    )


def get_current_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")

    token = authorization.removeprefix("Bearer ").strip()

    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token)

        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=KEYCLOAK_ISSUER,
            options={"verify_aud": False},
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    authorized_party = payload.get("azp")
    if authorized_party != KEYCLOAK_CLIENT_ID:
        raise HTTPException(status_code=403, detail="Invalid authorized party")

    username = payload.get("preferred_username")
    if not username:
        raise HTTPException(status_code=403, detail="Token does not contain username")

    return payload


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/reports")
def get_own_report(
    report_date: date | None = Query(default=None, description="Report date YYYY-MM-DD"),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    username = current_user["preferred_username"]
    ch_client = get_clickhouse_client()

    max_date_result = ch_client.query(
        """
        SELECT max(report_date)
        FROM reports.user_report_daily
        WHERE username = {username:String}
        """,
        parameters={"username": username},
    )

    max_processed_date = (
        max_date_result.result_rows[0][0]
        if max_date_result.result_rows and max_date_result.result_rows[0]
        else None
    )

    if max_processed_date is None:
        raise HTTPException(
            status_code=404,
            detail="Report data is not prepared for current user yet",
        )

    selected_date = report_date or max_processed_date

    if selected_date > max_processed_date:
        raise HTTPException(
            status_code=409,
            detail=(
                "Requested period is not processed by Airflow yet. "
                f"Latest available date is {to_iso(max_processed_date)}."
            ),
        )

    result = ch_client.query(
        """
        SELECT
            username,
            full_name,
            prosthesis_id,
            serial_number,
            report_date,
            events_count,
            avg_response_time_ms,
            avg_battery_level,
            avg_signal_quality,
            total_movements,
            period_started_at,
            period_finished_at,
            etl_loaded_at
        FROM reports.user_report_daily
        WHERE username = {username:String}
          AND report_date = {report_date:Date}
        ORDER BY prosthesis_id
        """,
        parameters={
            "username": username,
            "report_date": selected_date,
        },
    )

    rows = list(result.named_results())

    if not rows:
        raise HTTPException(
            status_code=404,
            detail="Report for requested period was not found",
        )

    prostheses = [
        {
            "prosthesisId": row["prosthesis_id"],
            "serialNumber": row["serial_number"],
            "eventsCount": int(row["events_count"]),
            "avgResponseTimeMs": round(float(row["avg_response_time_ms"]), 2),
            "avgBatteryLevel": round(float(row["avg_battery_level"]), 2),
            "avgSignalQuality": round(float(row["avg_signal_quality"]), 3),
            "totalMovements": int(row["total_movements"]),
            "periodStartedAt": to_iso(row["period_started_at"]),
            "periodFinishedAt": to_iso(row["period_finished_at"]),
        }
        for row in rows
    ]

    total_events = sum(item["eventsCount"] for item in prostheses)
    total_movements = sum(item["totalMovements"] for item in prostheses)

    response = {
        "username": username,
        "fullName": rows[0]["full_name"],
        "reportDate": to_iso(selected_date),
        "latestProcessedDate": to_iso(max_processed_date),
        "summary": {
            "prosthesesCount": len(prostheses),
            "totalEvents": total_events,
            "totalMovements": total_movements,
        },
        "prostheses": prostheses,
    }

    return JSONResponse(
        content=response,
        headers={
            "Content-Disposition": (
                f'attachment; filename="bionicpro-report-{username}-{to_iso(selected_date)}.json"'
            )
        },
    )
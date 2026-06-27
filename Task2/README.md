# Task2 — Разработка сервиса отчётов

## Цель

Добавить отдельный сервис отчётов для пользователей BionicPRO.

Пользователь должен иметь возможность скачать отчёт о работе своего протеза. Отчёт не должен рассчитываться в момент запроса: API должен читать уже подготовленные данные из OLAP-витрины.

## Что реализовано

В рамках задания добавлены:

- архитектура решения для подготовки и получения отчётов;
- ETL-процесс на Apache Airflow;
- источник данных CRM и telemetry на PostgreSQL;
- OLAP-хранилище ClickHouse;
- витрина отчётности `reports.user_report_daily`;
- backend-сервис отчётов на Python / FastAPI;
- endpoint `GET /reports`;
- проверка access token через Keycloak JWKS;
- ограничение доступа: пользователь получает только свой отчёт;
- UI-кнопка скачивания отчёта.

## Файлы решения

```text
Task2/
├── README.md
└── diagrams/
    ├── bionicpro_reports_to_be.puml
    └── bionicpro_reports_to_be.png

report-api/
├── Dockerfile
├── main.py
└── requirements.txt

airflow/
├── Dockerfile
├── requirements.txt
└── dags/
    └── bionicpro_reports_etl.py

source-db/
└── init.sql
```

Также изменены:

```text
docker-compose.yaml
frontend/src/components/ReportPage.tsx
```

## Архитектура решения

### Общий поток данных

1. CRM и telemetry-данные хранятся в source DB.
2. Airflow по расписанию запускает ETL-процесс.
3. DAG извлекает данные из CRM и telemetry.
4. Данные агрегируются в разрезе пользователя, даты и протеза.
5. Готовая витрина записывается в ClickHouse.
6. Report API читает отчёт из ClickHouse.
7. Frontend вызывает `GET /reports` и скачивает готовый JSON-отчёт.

## Компоненты

### Source DB

PostgreSQL используется как источник данных для локальной проверки.

Таблицы:

- `crm_clients` — клиенты;
- `prostheses` — протезы клиентов;
- `telemetry_events` — события работы протезов.

Эти таблицы имитируют данные CRM и данные с датчиков протеза.

### Apache Airflow

Airflow отвечает за регулярную подготовку витрины.

DAG:

```text
bionicpro_reports_etl
```

Расписание:

```text
0 * * * *
```

То есть DAG запускается раз в час.

Задачи DAG:

1. `prepare_clickhouse_schema` — создаёт базу и таблицу в ClickHouse.
2. `build_user_report_mart` — извлекает данные из PostgreSQL, агрегирует их и записывает в ClickHouse.

### ClickHouse

ClickHouse используется как OLAP-база для хранения готовой отчётной витрины.

Таблица:

```text
reports.user_report_daily
```

Основные поля:

- `username`;
- `full_name`;
- `prosthesis_id`;
- `serial_number`;
- `report_date`;
- `events_count`;
- `avg_response_time_ms`;
- `avg_battery_level`;
- `avg_signal_quality`;
- `total_movements`;
- `period_started_at`;
- `period_finished_at`;
- `etl_loaded_at`.

Ключ сортировки:

```text
(username, report_date, prosthesis_id)
```

Такой ключ выбран, чтобы быстро получать отчёт конкретного пользователя за обработанную дату.

### Report API

Backend реализован на Python / FastAPI.

Endpoint:

```http
GET /reports
Authorization: Bearer <access_token>
```

API не принимает `user_id` от клиента. Пользователь определяется из JWT:

```text
preferred_username
```

После этого API читает из ClickHouse только строки, где:

```text
username = preferred_username
```

Это защищает отчёты других пользователей от доступа через подмену параметров запроса.

## Ограничение доступа

Доступ к отчёту ограничен на backend-стороне.

Алгоритм:

1. Frontend отправляет запрос с `Authorization: Bearer <access_token>`.
2. Report API получает JWKS из Keycloak.
3. API проверяет подпись JWT.
4. API проверяет issuer токена.
5. API проверяет `azp`, чтобы токен был выдан клиенту `reports-frontend`.
6. API берёт `preferred_username` из токена.
7. API возвращает отчёт только по этому username.

Неаутентифицированный пользователь получает:

```text
401 Authentication required
```

Пользователь не может запросить чужой отчёт, потому что API не использует пользовательский `user_id` из query params.

## Обработка периода отчёта

Пользователь может запросить только данные за период, который уже обработан Airflow.

Если дата не передана, API возвращает отчёт за последнюю доступную обработанную дату.

Если пользователь запрашивает дату позже последней обработанной даты, API возвращает:

```text
409 Requested period is not processed by Airflow yet
```

Это защищает систему от попытки строить отчёт по данным, которых ещё нет в OLAP-витрине.

## UI

В `ReportPage` добавлена кнопка:

```text
Download Report
```

При нажатии frontend:

1. Проверяет, что пользователь аутентифицирован.
2. Берёт access token из Keycloak.
3. Отправляет запрос на `GET /reports`.
4. Получает готовый отчёт.
5. Скачивает его как JSON-файл.

## Запуск

Полная пересборка:

```bash
docker compose down
docker compose up -d --build
```

Проверить контейнеры:

```bash
docker compose ps
```

Ожидаемые сервисы:

```text
frontend
keycloak
keycloak_db
source_db
clickhouse
reports-api
airflow
```

## Проверка Airflow

Airflow UI:

```text
http://localhost:8081
```

Логин:

```text
admin / admin
```

Проверить DAG:

```bash
docker compose exec airflow airflow dags list | grep bionicpro
```

Запустить DAG вручную:

```bash
docker compose exec airflow airflow dags trigger bionicpro_reports_etl
```

## Проверка ClickHouse

После выполнения DAG проверить витрину:

```bash
docker compose exec clickhouse clickhouse-client --query "SELECT username, report_date, prosthesis_id, events_count FROM reports.user_report_daily"
```

Ожидаемый результат: строки для пользователей:

```text
prothetic1
prothetic2
prothetic3
```

## Проверка API

Healthcheck:

```bash
curl -i http://localhost:8000/health
```

Ожидаемый результат:

```json
{"status":"ok"}
```

Проверка закрытого доступа без токена:

```bash
curl -i http://localhost:8000/reports
```

Ожидаемый результат:

```text
401 Authentication required
```

## Проверка UI

1. Открыть frontend:

```text
http://localhost:3000
```

2. Войти пользователем:

```text
prothetic1 / prothetic123
```

3. Нажать:

```text
Download Report
```

4. Должен скачаться файл:

```text
bionicpro-report-prothetic1-YYYY-MM-DD.json
```

Отчёт содержит только данные пользователя `prothetic1`.

## Проверка безопасности

Перед сдачей проверено:

- неаутентифицированный пользователь не может вызвать `/reports`;
- frontend отправляет access token в `Authorization` header;
- Report API проверяет JWT через Keycloak JWKS;
- Report API не принимает `user_id` с frontend;
- username берётся только из JWT;
- отчёт читается из OLAP-витрины ClickHouse;
- сложные вычисления не выполняются в момент пользовательского запроса;
- пользователь получает данные только за период, который уже обработан Airflow.

## Итог

Решение добавляет отдельный сервис отчётов и закрывает требования задания:

- Airflow готовит отчётную витрину по расписанию;
- ClickHouse хранит заранее рассчитанные отчёты;
- Python / FastAPI backend отдаёт отчёт через `/reports`;
- доступ ограничен только собственными данными пользователя;
- UI позволяет скачать готовый отчёт;
- архитектура масштабируется: тяжёлая обработка вынесена в ETL, а API выполняет только быстрый read из OLAP.

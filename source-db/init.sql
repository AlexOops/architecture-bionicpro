CREATE TABLE IF NOT EXISTS crm_clients (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prostheses (
    prosthesis_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES crm_clients(user_id),
    serial_number TEXT NOT NULL,
    model TEXT NOT NULL,
    installed_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS telemetry_events (
    event_id BIGSERIAL PRIMARY KEY,
    prosthesis_id TEXT NOT NULL REFERENCES prostheses(prosthesis_id),
    event_ts TIMESTAMP NOT NULL,
    battery_level INTEGER NOT NULL,
    response_time_ms INTEGER NOT NULL,
    signal_quality NUMERIC(5, 2) NOT NULL,
    movement_count INTEGER NOT NULL
);

INSERT INTO crm_clients (user_id, username, full_name, email)
VALUES
    ('u-001', 'prothetic1', 'Prothetic One', 'prothetic1@example.com'),
    ('u-002', 'prothetic2', 'Prothetic Two', 'prothetic2@example.com'),
    ('u-003', 'prothetic3', 'Prothetic Three', 'prothetic3@example.com')
ON CONFLICT (user_id) DO NOTHING;

INSERT INTO prostheses (prosthesis_id, user_id, serial_number, model, installed_at)
VALUES
    ('p-001', 'u-001', 'BP-RU-0001', 'BionicPRO Arm v1', NOW() - INTERVAL '90 days'),
    ('p-002', 'u-002', 'BP-RU-0002', 'BionicPRO Arm v1', NOW() - INTERVAL '60 days'),
    ('p-003', 'u-003', 'BP-RU-0003', 'BionicPRO Hand v2', NOW() - INTERVAL '30 days')
ON CONFLICT (prosthesis_id) DO NOTHING;

INSERT INTO telemetry_events (
    prosthesis_id,
    event_ts,
    battery_level,
    response_time_ms,
    signal_quality,
    movement_count
)
SELECT
    'p-001',
    NOW() - INTERVAL '1 day' + (gs * INTERVAL '30 minutes'),
    80 - (gs % 20),
    72 + (gs % 25),
    0.85 + ((gs % 10)::numeric / 100),
    10 + (gs % 8)
FROM generate_series(1, 24) AS gs;

INSERT INTO telemetry_events (
    prosthesis_id,
    event_ts,
    battery_level,
    response_time_ms,
    signal_quality,
    movement_count
)
SELECT
    'p-002',
    NOW() - INTERVAL '1 day' + (gs * INTERVAL '40 minutes'),
    75 - (gs % 15),
    80 + (gs % 35),
    0.80 + ((gs % 12)::numeric / 100),
    8 + (gs % 7)
FROM generate_series(1, 18) AS gs;

INSERT INTO telemetry_events (
    prosthesis_id,
    event_ts,
    battery_level,
    response_time_ms,
    signal_quality,
    movement_count
)
SELECT
    'p-003',
    NOW() - INTERVAL '1 day' + (gs * INTERVAL '45 minutes'),
    90 - (gs % 10),
    68 + (gs % 18),
    0.88 + ((gs % 8)::numeric / 100),
    12 + (gs % 6)
FROM generate_series(1, 16) AS gs;

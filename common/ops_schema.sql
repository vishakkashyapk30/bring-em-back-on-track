-- Operational store (SQLite, WAL): approvals, audit log, hardship events. Append-only where noted.

CREATE TABLE IF NOT EXISTS audit_log (            -- append-only
    audit_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    user_id       TEXT NOT NULL,
    role          TEXT NOT NULL,
    event_type    TEXT NOT NULL,   -- query | score | nba_decision | override | edit | summary_approve |
                                   -- simulator_run | refusal | hardship_flag | batch_approve | identity_review
    entity_type   TEXT,
    entity_id     TEXT,
    input_hash    TEXT,
    output_hash   TEXT,
    payload_json  TEXT
);

CREATE TRIGGER IF NOT EXISTS audit_log_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_log_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;

CREATE TABLE IF NOT EXISTS nba_decisions (
    decision_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    case_id       TEXT NOT NULL,
    golden_id     TEXT,
    proposed_json TEXT NOT NULL,   -- action + explanation as shown
    decision      TEXT NOT NULL,   -- approve | edit | override
    final_json    TEXT,
    reason_code   TEXT,
    note          TEXT,
    user_id       TEXT NOT NULL,
    audit_id      INTEGER REFERENCES audit_log(audit_id)
);

CREATE TABLE IF NOT EXISTS hardship_flag_events (
    event_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    golden_id     TEXT NOT NULL,
    from_level    TEXT NOT NULL,
    to_level      TEXT NOT NULL,
    source        TEXT NOT NULL,   -- agent_coded | customer_form | model | llm_flag | rule_s7 | radar | specialist
    reviewer_id   TEXT,
    reason        TEXT,
    program_id    TEXT,
    audit_id      INTEGER REFERENCES audit_log(audit_id)
);

CREATE TABLE IF NOT EXISTS call_summaries (
    contact_id    TEXT PRIMARY KEY,
    draft_json    TEXT NOT NULL,
    approved_json TEXT,
    status        TEXT NOT NULL DEFAULT 'draft',   -- draft | approved
    edited_fields TEXT,
    prompt_version TEXT,
    provider      TEXT,
    approved_by   TEXT,
    approved_ts   TEXT
);

CREATE TABLE IF NOT EXISTS simulator_runs (
    run_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    case_id       TEXT NOT NULL,
    user_id       TEXT NOT NULL,
    levers_json   TEXT NOT NULL,
    result_json   TEXT NOT NULL,
    chosen        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS batches (
    batch_id      TEXT PRIMARY KEY,
    created_ts    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    kind          TEXT NOT NULL,   -- digital_reminders | radar_playbook | outage_playbook
    strategy_code TEXT,
    items_json    TEXT NOT NULL,
    sample_json   TEXT,            -- the 2% sample shown first
    status        TEXT NOT NULL DEFAULT 'pending',
    approved_by   TEXT,
    approved_ts   TEXT
);

CREATE TABLE IF NOT EXISTS identity_reviews (
    pair_id       TEXT PRIMARY KEY,
    left_id       TEXT NOT NULL,
    right_id      TEXT NOT NULL,
    match_probability REAL,
    verdict       TEXT,            -- link | no_link | unsure
    reviewer_id   TEXT,
    ts            TEXT
);

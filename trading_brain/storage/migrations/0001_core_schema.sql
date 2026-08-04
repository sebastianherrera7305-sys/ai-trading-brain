-- Core operational schema -- ARCHITECTURE.md §18, scoped per
-- docs/specs/01-storage-and-event-bus.md (research schema, §32, is a
-- later migration/subsystem, not this one).
--
-- signals, trades, and settings_audit_log are APPEND-ONLY: no UPDATE or
-- DELETE statement should ever be written against them outside
-- TradeRepository.record_exit()'s one narrow, named exception (see the
-- spec doc's Data Contracts section for why that's the one legitimate
-- mutation this schema has).

CREATE TABLE signals (
    trade_id             TEXT PRIMARY KEY,
    symbol                TEXT NOT NULL,
    strategy_name           TEXT NOT NULL,
    generated_at               TIMESTAMPTZ NOT NULL,
    direction                    TEXT NOT NULL,
    entry                          DOUBLE NOT NULL,
    stop_loss                        DOUBLE NOT NULL,
    take_profit                        DOUBLE NOT NULL,
    invalidation_price                   DOUBLE NOT NULL,
    tier                                    TEXT NOT NULL,
    checklist_json                            TEXT NOT NULL,
    ai_win_probability                           DOUBLE,
    ai_rationale                                    TEXT,
    ai_model_version                                   TEXT,
    regime_at_signal                                      TEXT,
    risk_decision                                            TEXT NOT NULL,
    risk_reason                                                 TEXT,
    portfolio_decision                                             TEXT,
    account_mode                                                      TEXT NOT NULL
);

CREATE TABLE trades (
    trade_id         TEXT PRIMARY KEY REFERENCES signals(trade_id),
    broker_order_id    TEXT,
    filled_at             TIMESTAMPTZ,
    fill_price               DOUBLE,
    quantity                    INTEGER,
    exit_index                     INTEGER,
    exit_price                        DOUBLE,
    exit_at                              TIMESTAMPTZ,
    outcome                                 TEXT,
    realized_r                                 DOUBLE
);

CREATE SEQUENCE regime_history_id_seq START 1;
CREATE TABLE regime_history (
    id           BIGINT PRIMARY KEY DEFAULT nextval('regime_history_id_seq'),
    symbol        TEXT NOT NULL,
    regime         TEXT NOT NULL,
    confidence      DOUBLE NOT NULL,
    as_of             TIMESTAMPTZ NOT NULL
);

CREATE SEQUENCE settings_audit_log_id_seq START 1;
CREATE TABLE settings_audit_log (
    id           BIGINT PRIMARY KEY DEFAULT nextval('settings_audit_log_id_seq'),
    field         TEXT NOT NULL,
    old_value      TEXT,
    new_value       TEXT,
    changed_by        TEXT NOT NULL,
    changed_at           TIMESTAMPTZ NOT NULL
);

CREATE SEQUENCE account_snapshots_id_seq START 1;
CREATE TABLE account_snapshots (
    id          BIGINT PRIMARY KEY DEFAULT nextval('account_snapshots_id_seq'),
    account_mode TEXT NOT NULL,
    equity        DOUBLE NOT NULL,
    open_positions INTEGER NOT NULL,
    as_of            TIMESTAMPTZ NOT NULL
);

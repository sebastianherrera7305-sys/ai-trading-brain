-- Registry schema -- ARCHITECTURE.md §30/§32, shaped per ADR-0002
-- (append-only status transition log, not a mutable status column).
-- See docs/specs/02-registry.md for the full data contract reasoning.

CREATE TABLE experiments (
    experiment_id              TEXT PRIMARY KEY,
    experiment_type              TEXT NOT NULL,
    code_git_hash                  TEXT NOT NULL,
    config_json                       TEXT NOT NULL,
    metrics_json                        TEXT NOT NULL,
    dataset_snapshot_id                    TEXT,
    validation_standard_version              TEXT,
    random_seed                                 INTEGER,
    started_at                                     TIMESTAMPTZ,
    completed_at                                      TIMESTAMPTZ
);

CREATE TABLE registry_artifacts (
    artifact_id              TEXT PRIMARY KEY,
    artifact_type               TEXT NOT NULL,
    version                        TEXT NOT NULL,
    source_experiment_id              TEXT NOT NULL REFERENCES experiments(experiment_id),
    created_at                           TIMESTAMPTZ NOT NULL
);

CREATE SEQUENCE registry_transitions_id_seq START 1;
CREATE TABLE registry_status_transitions (
    id                          BIGINT PRIMARY KEY DEFAULT nextval('registry_transitions_id_seq'),
    artifact_id                    TEXT NOT NULL REFERENCES registry_artifacts(artifact_id),
    status                            TEXT NOT NULL,
    transitioned_at                     TIMESTAMPTZ NOT NULL,
    promoted_by                            TEXT NOT NULL,
    promotion_checklist_snapshot              TEXT
);

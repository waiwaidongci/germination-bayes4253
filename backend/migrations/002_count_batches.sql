-- Count source batch import: source attribution on lot counts and immutable batch ledger.
-- Fresh deployments get these objects from SQLAlchemy metadata; this script upgrades existing databases.
ALTER TABLE lot_counts ADD COLUMN IF NOT EXISTS source_batch TEXT NOT NULL DEFAULT '';
ALTER TABLE lot_counts ADD COLUMN IF NOT EXISTS source_version INTEGER NOT NULL DEFAULT 0;
ALTER TABLE lot_counts ADD COLUMN IF NOT EXISTS content_hash TEXT NOT NULL DEFAULT '';
ALTER TABLE lot_counts ADD COLUMN IF NOT EXISTS updated_at TEXT NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS count_batches (
    id SERIAL PRIMARY KEY,
    study_id INTEGER NOT NULL REFERENCES germination_studies(id),
    source_batch TEXT NOT NULL,
    version INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    content JSON NOT NULL,
    status TEXT NOT NULL,
    total_lots INTEGER NOT NULL,
    accepted_lots INTEGER NOT NULL DEFAULT 0,
    rejected_rows JSON NOT NULL DEFAULT '[]',
    conflict_with INTEGER REFERENCES count_batches(id),
    actor TEXT NOT NULL,
    published_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_count_batch_study_source_version
    ON count_batches (study_id, source_batch, version);
CREATE INDEX IF NOT EXISTS count_batch_study_idx ON count_batches (study_id, id);

-- Migration 014: Quarantine resolution audit table
-- Description: Tracks admin actions taken on quarantine_event rows.
--              raw.quarantine_event is append-only (prevent_modification trigger),
--              so resolution state is recorded here rather than deleting rows.
--              Resolved quarantine_ids are filtered out of the admin resolve UI.
--
-- Actions:
--   'deleted'  — record discarded; no downstream ingestion
--   'requeued' — record re-inserted into raw.transaction_event with a corrected
--                c_id and will be promoted by the next transform.py run
--
-- Depends on: 008 (raw.quarantine_event must exist), Create_auth.sql (auth.users)

BEGIN;

CREATE TABLE raw.quarantine_resolution (
    resolution_id   UUID                     DEFAULT gen_random_uuid() PRIMARY KEY,
    quarantine_id   UUID                     NOT NULL
                        REFERENCES raw.quarantine_event(quarantine_id),
    action          VARCHAR(20)              NOT NULL
                        CHECK (action IN ('deleted', 'requeued')),
    new_c_id        UUID,
    resolved_by     INT                      REFERENCES auth.users(id),
    resolved_at     TIMESTAMPTZ              DEFAULT NOW()
);

CREATE INDEX idx_quarantine_resolution_qid
    ON raw.quarantine_resolution (quarantine_id);

COMMIT;

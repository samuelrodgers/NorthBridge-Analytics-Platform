-- Migration 016: Add dirty_value column to raw.quarantine_event
-- Description: Stores the original pre-normalisation string for the field
--              that caused the quarantine failure. Lets admins see the
--              actual bad data (e.g. "99,00.9", "14-32-2026", "ACME Corp")
--              in the resolve UI instead of just the failure code.
--
--   dirty_value TEXT — nullable; NULL for failures where no pre-norm string
--                      exists (e.g. NULL_COMPANY_ID where the field was
--                      genuinely absent). Populated by pipeline.py from the
--                      snapshot taken before normalisation begins.
--
-- Note: raw.quarantine_event has an append-only BEFORE UPDATE OR DELETE
-- trigger. ALTER TABLE is DDL and is not affected by that trigger.
--
-- Depends on: 008 (raw.quarantine_event must exist)

BEGIN;

ALTER TABLE raw.quarantine_event
    ADD COLUMN dirty_value TEXT;

COMMENT ON COLUMN raw.quarantine_event.dirty_value IS
    'Pre-normalisation raw string for the failing field. NULL if field was absent.';

COMMIT;

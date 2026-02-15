-- Function to enforce immutability of raw tables
-- > Not attached < --

CREATE OR REPLACE FUNCTION raw.prevent_modification()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Raw tables are append-only';
END;
$$ LANGUAGE plpgsql;

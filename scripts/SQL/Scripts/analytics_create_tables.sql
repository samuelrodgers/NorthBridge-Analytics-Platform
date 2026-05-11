-- Northbridge Analytics Platform — Base Schema
-- Creates the analytics, raw, and supporting objects that migrations 001-007
-- are written against.  Running this script followed by every migration in
-- sequence produces the production schema captured in structure_dump.sql.
--
-- Schemas: analytics (star-schema warehouse), raw (append-only ingestion)
-- Auth schema is created separately in Create_auth.sql.

BEGIN;

-- ============================================================
-- Schemas
-- ============================================================

CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS raw;

-- ============================================================
-- Dimension tables  (analytics)
-- ============================================================

CREATE TABLE analytics.d_currency (
    cncy_code  CHAR(3)      DEFAULT 'XXX' NOT NULL,
    cncy_name  VARCHAR(60)  NOT NULL,

    CONSTRAINT d_currency_pkey PRIMARY KEY (cncy_code)
);



CREATE TABLE analytics.d_company (
    c_id          UUID         DEFAULT gen_random_uuid() NOT NULL,
    c_name        VARCHAR(60)  NOT NULL,
    industry      VARCHAR(60)  NOT NULL,
    hq_country    VARCHAR(60)  NOT NULL,
    default_cncy  CHAR(3)      NOT NULL,

    CONSTRAINT d_company_pkey PRIMARY KEY (c_id)
);



CREATE TABLE analytics.d_time (
    time_id       UUID       DEFAULT gen_random_uuid() NOT NULL,
    t_stamp       TIMESTAMP WITH TIME ZONE  NOT NULL,
    fisc_quarter  SMALLINT   NOT NULL,
    day_of_week   SMALLINT   NOT NULL,

    CONSTRAINT d_time_pkey PRIMARY KEY (time_id)
);


-- ============================================================
-- Fact tables  (analytics)
-- ============================================================

CREATE TABLE analytics.f_transaction (
    tx_id    UUID           DEFAULT gen_random_uuid() NOT NULL,
    amount   NUMERIC(18,4)  NOT NULL,
    c_id     UUID           NOT NULL,
    time_id  UUID           NOT NULL,
    cncy     CHAR(3)        CONSTRAINT f_transaction_quote_cncy_not_null NOT NULL,

    CONSTRAINT f_transaction_pkey PRIMARY KEY (tx_id),

    CONSTRAINT f_transaction_c_id_fkey
        FOREIGN KEY (c_id) REFERENCES analytics.d_company (c_id),

    CONSTRAINT f_transaction_time_id_fkey
        FOREIGN KEY (time_id) REFERENCES analytics.d_time (time_id)
);



CREATE INDEX idx_f_transaction_c_id    ON analytics.f_transaction (c_id);
CREATE INDEX idx_f_transaction_time_id ON analytics.f_transaction (time_id);


CREATE TABLE analytics.f_fx_rate (
    fx_id      UUID           DEFAULT gen_random_uuid() NOT NULL,
    rate       NUMERIC(14,7)  CONSTRAINT f_fx_rate_amount_not_null NOT NULL,
    base_cncy  CHAR(3)        NOT NULL,
    quote_cncy CHAR(3)        NOT NULL,

    CONSTRAINT f_fx_rate_pkey PRIMARY KEY (fx_id),

    CONSTRAINT f_fx_rate_base_cncy_fkey
        FOREIGN KEY (base_cncy) REFERENCES analytics.d_currency (cncy_code),

    CONSTRAINT f_fx_rate_quote_cncy_fkey
        FOREIGN KEY (quote_cncy) REFERENCES analytics.d_currency (cncy_code)
);

CREATE TABLE analytics.f_conversion (
    cx_id        UUID           DEFAULT gen_random_uuid() NOT NULL,
    base_amount  NUMERIC(18,4)  NOT NULL,
    fee_amount   NUMERIC(16,4)  NOT NULL,
    fx_id        UUID           NOT NULL,
    tx_id        UUID           NOT NULL,

    CONSTRAINT f_conversion_pkey PRIMARY KEY (cx_id),

    CONSTRAINT f_conversion_one_per_tx UNIQUE (tx_id),

    CONSTRAINT f_transaction_tx_id_fkey
        FOREIGN KEY (tx_id) REFERENCES analytics.f_transaction (tx_id)
);

CREATE INDEX idx_f_conversion_tx_id ON analytics.f_conversion (tx_id);

-- ============================================================
-- Functions  (analytics)
-- ============================================================

-- validate_conversion_currency — ensures that the transaction currency
-- matches the FX rate base currency when inserting into f_conversion.
-- Preserved across all migrations; referenced by migration 003 which
-- updates the local variable types from CHAR(3) to VARCHAR(3).

CREATE FUNCTION analytics.validate_conversion_currency()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_tx_cncy   char(3);
    v_base_cncy char(3);
BEGIN
    SELECT cncy INTO v_tx_cncy
    FROM analytics.f_transaction
    WHERE tx_id = NEW.tx_id;

    SELECT base_cncy INTO v_base_cncy
    FROM analytics.f_fx_rate
    WHERE fx_id = NEW.fx_id;

    IF v_tx_cncy IS DISTINCT FROM v_base_cncy THEN
        RAISE EXCEPTION
            'Transaction currency (%) does not match FX base currency (%)',
            v_tx_cncy, v_base_cncy;
    END IF;

    RETURN NEW;
END;
$$;

-- apply_conversion — trigger function that was used to overwrite
-- f_transaction.amount with a converted value.  Removed by migration 006.
-- The original function body is not preserved in version control; this
-- stub exists so that migration 006's DROP FUNCTION succeeds cleanly.

CREATE FUNCTION analytics.apply_conversion()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'apply_conversion stub — should be dropped by migration 006';
END;
$$;

-- ============================================================
-- Triggers  (analytics)
-- ============================================================

CREATE TRIGGER trg_validate_conversion_currency
    BEFORE INSERT OR UPDATE ON analytics.f_conversion
    FOR EACH ROW EXECUTE FUNCTION analytics.validate_conversion_currency();

CREATE TRIGGER trg_apply_conversion
    BEFORE INSERT ON analytics.f_conversion
    FOR EACH ROW EXECUTE FUNCTION analytics.apply_conversion();

-- ============================================================
-- Functions  (raw)
-- ============================================================

CREATE FUNCTION raw.prevent_modification()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'Raw tables are append-only';
END;
$$;

-- ============================================================
-- Raw ingestion tables
-- ============================================================

CREATE TABLE raw.fx_rate (
    fx_rate_id           UUID                     DEFAULT gen_random_uuid() NOT NULL,
    base_cncy            VARCHAR(3)               NOT NULL,
    quote_cncy           VARCHAR(3)               NOT NULL,
    fx_timestamp         TIMESTAMP WITH TIME ZONE NOT NULL,
    rate                 NUMERIC(14,7)            NOT NULL,
    ingestion_timestamp  TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    source               VARCHAR(50)              DEFAULT 'api' NOT NULL,

    CONSTRAINT fx_rate_pkey PRIMARY KEY (fx_rate_id),

    CONSTRAINT idx_fx_rate_cncy_ts
        UNIQUE (base_cncy, quote_cncy, fx_timestamp)
);

CREATE INDEX idx_fx_rate_ts_brin
    ON raw.fx_rate USING brin (fx_timestamp);


CREATE TABLE raw.transaction_event (
    tx_id                UUID                     DEFAULT gen_random_uuid()
                         CONSTRAINT transaction_tx_id_not_null          NOT NULL,
    c_id                 UUID
                         CONSTRAINT transaction_c_id_not_null           NOT NULL,
    base_cncy            VARCHAR(3)
                         CONSTRAINT transaction_cncy_code_not_null      NOT NULL,
    tx_timestamp         TIMESTAMP WITH TIME ZONE
                         CONSTRAINT transaction_tx_timestamp_not_null   NOT NULL,
    amount               NUMERIC(18,4)
                         CONSTRAINT transaction_amount_not_null         NOT NULL,
    ingestion_timestamp  TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    quote_cncy           CHAR(3),
    fee_amount           NUMERIC(16,4),

    CONSTRAINT transaction_pkey PRIMARY KEY (tx_id)
);

CREATE INDEX idx_tx_event_cncy_timestamp
    ON raw.transaction_event USING btree (base_cncy, quote_cncy, tx_timestamp);

COMMIT;

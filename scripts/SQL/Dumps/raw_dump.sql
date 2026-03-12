--
-- PostgreSQL database dump
--

\restrict 7ezrn8Gr6dsA1JjHLmjqa9j2t6eGUBBiUwRTjrE3JUbK7BRYS7LFmcyufS9W1ne

-- Dumped from database version 18.1
-- Dumped by pg_dump version 18.1

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: raw; Type: SCHEMA; Schema: -; Owner: alex_analytics
--

CREATE SCHEMA raw;


ALTER SCHEMA raw OWNER TO alex_analytics;

--
-- Name: prevent_modification(); Type: FUNCTION; Schema: raw; Owner: alex_analytics
--

CREATE FUNCTION raw.prevent_modification() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    RAISE EXCEPTION 'Raw tables are append-only';
END;
$$;


ALTER FUNCTION raw.prevent_modification() OWNER TO alex_analytics;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: fx_rate; Type: TABLE; Schema: raw; Owner: alex_analytics
--

CREATE TABLE raw.fx_rate (
    fx_rate_id uuid DEFAULT gen_random_uuid() NOT NULL,
    base_cncy character varying(3) NOT NULL,
    quote_cncy character varying(3) NOT NULL,
    fx_timestamp timestamp with time zone NOT NULL,
    rate numeric(14,7) NOT NULL,
    ingestion_timestamp timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    source character varying(50) DEFAULT 'api'::character varying NOT NULL
);


ALTER TABLE raw.fx_rate OWNER TO alex_analytics;

--
-- Name: transaction_event; Type: TABLE; Schema: raw; Owner: alex_analytics
--

CREATE TABLE raw.transaction_event (
    tx_id uuid DEFAULT gen_random_uuid() CONSTRAINT transaction_tx_id_not_null NOT NULL,
    c_id uuid CONSTRAINT transaction_c_id_not_null NOT NULL,
    base_cncy character varying(3) CONSTRAINT transaction_cncy_code_not_null NOT NULL,
    tx_timestamp timestamp with time zone CONSTRAINT transaction_tx_timestamp_not_null NOT NULL,
    amount numeric(18,4) CONSTRAINT transaction_amount_not_null NOT NULL,
    ingestion_timestamp timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    quote_cncy character(3),
    fee_amount numeric(16,4)
);


ALTER TABLE raw.transaction_event OWNER TO alex_analytics;

--
-- Data for Name: fx_rate; Type: TABLE DATA; Schema: raw; Owner: alex_analytics
--

COPY raw.fx_rate (fx_rate_id, base_cncy, quote_cncy, fx_timestamp, rate, ingestion_timestamp, source) FROM stdin;
\.


--
-- Data for Name: transaction_event; Type: TABLE DATA; Schema: raw; Owner: alex_analytics
--

COPY raw.transaction_event (tx_id, c_id, base_cncy, tx_timestamp, amount, ingestion_timestamp, quote_cncy, fee_amount) FROM stdin;
\.


--
-- Name: fx_rate fx_rate_pkey; Type: CONSTRAINT; Schema: raw; Owner: alex_analytics
--

ALTER TABLE ONLY raw.fx_rate
    ADD CONSTRAINT fx_rate_pkey PRIMARY KEY (fx_rate_id);


--
-- Name: fx_rate idx_fx_rate_cncy_ts; Type: CONSTRAINT; Schema: raw; Owner: alex_analytics
--

ALTER TABLE ONLY raw.fx_rate
    ADD CONSTRAINT idx_fx_rate_cncy_ts UNIQUE (base_cncy, quote_cncy, fx_timestamp);


--
-- Name: transaction_event transaction_pkey; Type: CONSTRAINT; Schema: raw; Owner: alex_analytics
--

ALTER TABLE ONLY raw.transaction_event
    ADD CONSTRAINT transaction_pkey PRIMARY KEY (tx_id);


--
-- Name: idx_fx_rate_ts_brin; Type: INDEX; Schema: raw; Owner: alex_analytics
--

CREATE INDEX idx_fx_rate_ts_brin ON raw.fx_rate USING brin (fx_timestamp);


--
-- Name: idx_tx_event_cncy_timestamp; Type: INDEX; Schema: raw; Owner: alex_analytics
--

CREATE INDEX idx_tx_event_cncy_timestamp ON raw.transaction_event USING btree (base_cncy, quote_cncy, tx_timestamp);


--
-- PostgreSQL database dump complete
--

\unrestrict 7ezrn8Gr6dsA1JjHLmjqa9j2t6eGUBBiUwRTjrE3JUbK7BRYS7LFmcyufS9W1ne


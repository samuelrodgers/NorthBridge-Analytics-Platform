--
-- PostgreSQL database dump
--

\restrict FHrW7vYmOC8NceiqsifbycOgdPUzHUbe5BhGWaRaQzlHVN2bMuvX1rHd9cxvwi5

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
-- Name: analytics; Type: SCHEMA; Schema: -; Owner: alex_analytics
--

CREATE SCHEMA analytics;


ALTER SCHEMA analytics OWNER TO alex_analytics;

--
-- Name: apply_conversion(); Type: FUNCTION; Schema: analytics; Owner: alex_analytics
--

CREATE FUNCTION analytics.apply_conversion() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_rate numeric(14,7);
BEGIN
    -- Get FX rate
    SELECT rate
    INTO v_rate
    FROM analytics.f_fx_rate
    WHERE fx_id = NEW.fx_id;

    -- Update related transaction amount
    UPDATE analytics.f_transaction
    SET amount = (NEW.base_amount * v_rate) - NEW.fee_amount
    WHERE tx_id = NEW.tx_id;

    RETURN NEW;
END;
$$;


ALTER FUNCTION analytics.apply_conversion() OWNER TO alex_analytics;

--
-- Name: validate_conversion_currency(); Type: FUNCTION; Schema: analytics; Owner: alex_analytics
--

CREATE FUNCTION analytics.validate_conversion_currency() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_tx_cncy   varchar(3);
    v_base_cncy varchar(3);
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


ALTER FUNCTION analytics.validate_conversion_currency() OWNER TO alex_analytics;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: d_company; Type: TABLE; Schema: analytics; Owner: alex_analytics
--

CREATE TABLE analytics.d_company (
    c_id uuid DEFAULT gen_random_uuid() NOT NULL,
    c_name character varying(60) NOT NULL,
    industry character varying(60) NOT NULL,
    hq_country character varying(60) NOT NULL,
    default_cncy character(3) NOT NULL
);


ALTER TABLE analytics.d_company OWNER TO alex_analytics;

--
-- Name: d_currency; Type: TABLE; Schema: analytics; Owner: alex_analytics
--

CREATE TABLE analytics.d_currency (
    cncy_code character(3) DEFAULT 'XXX'::character varying NOT NULL,
    cncy_name character varying(60) NOT NULL
);


ALTER TABLE analytics.d_currency OWNER TO alex_analytics;

--
-- Name: d_time; Type: TABLE; Schema: analytics; Owner: alex_analytics
--

CREATE TABLE analytics.d_time (
    time_id uuid DEFAULT gen_random_uuid() NOT NULL,
    t_stamp timestamp with time zone NOT NULL,
    fisc_quarter smallint NOT NULL,
    day_of_week smallint NOT NULL
);


ALTER TABLE analytics.d_time OWNER TO alex_analytics;

--
-- Name: f_conversion; Type: TABLE; Schema: analytics; Owner: alex_analytics
--

CREATE TABLE analytics.f_conversion (
    cx_id uuid DEFAULT gen_random_uuid() NOT NULL,
    base_amount numeric(18,4) NOT NULL,
    fee_amount numeric(16,4) NOT NULL,
    fx_id uuid NOT NULL,
    tx_id uuid NOT NULL
);


ALTER TABLE analytics.f_conversion OWNER TO alex_analytics;

--
-- Name: f_fx_rate; Type: TABLE; Schema: analytics; Owner: alex_analytics
--

CREATE TABLE analytics.f_fx_rate (
    fx_id uuid DEFAULT gen_random_uuid() NOT NULL,
    rate numeric(14,7) CONSTRAINT f_fx_rate_amount_not_null NOT NULL,
    base_cncy character(3) NOT NULL,
    quote_cncy character(3) NOT NULL
);


ALTER TABLE analytics.f_fx_rate OWNER TO alex_analytics;

--
-- Name: f_transaction; Type: TABLE; Schema: analytics; Owner: alex_analytics
--

CREATE TABLE analytics.f_transaction (
    tx_id uuid DEFAULT gen_random_uuid() NOT NULL,
    amount numeric(18,4) NOT NULL,
    c_id uuid NOT NULL,
    time_id uuid NOT NULL,
    cncy character varying(3) CONSTRAINT f_transaction_quote_cncy_not_null NOT NULL
);


ALTER TABLE analytics.f_transaction OWNER TO alex_analytics;

--
-- Data for Name: d_company; Type: TABLE DATA; Schema: analytics; Owner: alex_analytics
--

COPY analytics.d_company (c_id, c_name, industry, hq_country, default_cncy) FROM stdin;
\.


--
-- Data for Name: d_currency; Type: TABLE DATA; Schema: analytics; Owner: alex_analytics
--

COPY analytics.d_currency (cncy_code, cncy_name) FROM stdin;
\.


--
-- Data for Name: d_time; Type: TABLE DATA; Schema: analytics; Owner: alex_analytics
--

COPY analytics.d_time (time_id, t_stamp, fisc_quarter, day_of_week) FROM stdin;
\.


--
-- Data for Name: f_conversion; Type: TABLE DATA; Schema: analytics; Owner: alex_analytics
--

COPY analytics.f_conversion (cx_id, base_amount, fee_amount, fx_id, tx_id) FROM stdin;
\.


--
-- Data for Name: f_fx_rate; Type: TABLE DATA; Schema: analytics; Owner: alex_analytics
--

COPY analytics.f_fx_rate (fx_id, rate, base_cncy, quote_cncy) FROM stdin;
\.


--
-- Data for Name: f_transaction; Type: TABLE DATA; Schema: analytics; Owner: alex_analytics
--

COPY analytics.f_transaction (tx_id, amount, c_id, time_id, cncy) FROM stdin;
\.


--
-- Name: d_company d_company_pkey; Type: CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.d_company
    ADD CONSTRAINT d_company_pkey PRIMARY KEY (c_id);


--
-- Name: d_currency d_currency_pkey; Type: CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.d_currency
    ADD CONSTRAINT d_currency_pkey PRIMARY KEY (cncy_code);


--
-- Name: d_time d_time_pkey; Type: CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.d_time
    ADD CONSTRAINT d_time_pkey PRIMARY KEY (time_id);


--
-- Name: f_conversion f_conversion_one_per_tx; Type: CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.f_conversion
    ADD CONSTRAINT f_conversion_one_per_tx UNIQUE (tx_id);


--
-- Name: f_conversion f_conversion_pkey; Type: CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.f_conversion
    ADD CONSTRAINT f_conversion_pkey PRIMARY KEY (cx_id);


--
-- Name: f_fx_rate f_fx_rate_pkey; Type: CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.f_fx_rate
    ADD CONSTRAINT f_fx_rate_pkey PRIMARY KEY (fx_id);


--
-- Name: f_transaction f_transaction_pkey; Type: CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.f_transaction
    ADD CONSTRAINT f_transaction_pkey PRIMARY KEY (tx_id);


--
-- Name: idx_f_conversion_tx_id; Type: INDEX; Schema: analytics; Owner: alex_analytics
--

CREATE INDEX idx_f_conversion_tx_id ON analytics.f_conversion USING btree (tx_id);


--
-- Name: idx_f_transaction_c_id; Type: INDEX; Schema: analytics; Owner: alex_analytics
--

CREATE INDEX idx_f_transaction_c_id ON analytics.f_transaction USING btree (c_id);


--
-- Name: idx_f_transaction_time_id; Type: INDEX; Schema: analytics; Owner: alex_analytics
--

CREATE INDEX idx_f_transaction_time_id ON analytics.f_transaction USING btree (time_id);


--
-- Name: f_conversion trg_apply_conversion; Type: TRIGGER; Schema: analytics; Owner: alex_analytics
--

CREATE TRIGGER trg_apply_conversion AFTER INSERT OR UPDATE ON analytics.f_conversion FOR EACH ROW EXECUTE FUNCTION analytics.apply_conversion();


--
-- Name: f_conversion trg_validate_conversion_currency; Type: TRIGGER; Schema: analytics; Owner: alex_analytics
--

CREATE TRIGGER trg_validate_conversion_currency BEFORE INSERT OR UPDATE ON analytics.f_conversion FOR EACH ROW EXECUTE FUNCTION analytics.validate_conversion_currency();


--
-- Name: f_fx_rate f_fx_rate_base_cncy_fkey; Type: FK CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.f_fx_rate
    ADD CONSTRAINT f_fx_rate_base_cncy_fkey FOREIGN KEY (base_cncy) REFERENCES analytics.d_currency(cncy_code);


--
-- Name: f_fx_rate f_fx_rate_quote_cncy_fkey; Type: FK CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.f_fx_rate
    ADD CONSTRAINT f_fx_rate_quote_cncy_fkey FOREIGN KEY (quote_cncy) REFERENCES analytics.d_currency(cncy_code);


--
-- Name: f_transaction f_transaction_c_id_fkey; Type: FK CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.f_transaction
    ADD CONSTRAINT f_transaction_c_id_fkey FOREIGN KEY (c_id) REFERENCES analytics.d_company(c_id);


--
-- Name: f_transaction f_transaction_time_id_fkey; Type: FK CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.f_transaction
    ADD CONSTRAINT f_transaction_time_id_fkey FOREIGN KEY (time_id) REFERENCES analytics.d_time(time_id);


--
-- Name: f_conversion f_transaction_tx_id_fkey; Type: FK CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.f_conversion
    ADD CONSTRAINT f_transaction_tx_id_fkey FOREIGN KEY (tx_id) REFERENCES analytics.f_transaction(tx_id);


--
-- PostgreSQL database dump complete
--

\unrestrict FHrW7vYmOC8NceiqsifbycOgdPUzHUbe5BhGWaRaQzlHVN2bMuvX1rHd9cxvwi5


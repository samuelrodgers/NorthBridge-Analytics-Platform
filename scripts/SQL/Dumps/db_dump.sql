--
-- PostgreSQL database dump
--

\restrict U4RxpTABvr4zTZCaazfAw90Ss6qlleUjpeCASgb62RH0FCldvc8UwJLUhSHUANE

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
-- Name: raw; Type: SCHEMA; Schema: -; Owner: alex_analytics
--

CREATE SCHEMA raw;


ALTER SCHEMA raw OWNER TO alex_analytics;

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
-- Name: d_company; Type: TABLE; Schema: analytics; Owner: alex_analytics
--

CREATE TABLE analytics.d_company (
    c_id uuid DEFAULT gen_random_uuid() NOT NULL,
    c_name character varying(60) NOT NULL,
    hq_country character varying(60) NOT NULL,
    default_cncy character varying(3) NOT NULL,
    industry_id uuid NOT NULL
);


ALTER TABLE analytics.d_company OWNER TO alex_analytics;

--
-- Name: COLUMN d_company.default_cncy; Type: COMMENT; Schema: analytics; Owner: alex_analytics
--

COMMENT ON COLUMN analytics.d_company.default_cncy IS 'Default display currency for this company (BR-006). Must match d_industry.display_cncy unless industry display_cncy is USD (BR-013).';


--
-- Name: COLUMN d_company.industry_id; Type: COMMENT; Schema: analytics; Owner: alex_analytics
--

COMMENT ON COLUMN analytics.d_company.industry_id IS 'FK to d_industry. Defines the industry this company belongs to (BR-012). Display currency is inherited from d_industry.display_cncy (BR-007).';


--
-- Name: d_currency; Type: TABLE; Schema: analytics; Owner: alex_analytics
--

CREATE TABLE analytics.d_currency (
    cncy_code character varying(3) DEFAULT 'XXX'::character varying NOT NULL,
    cncy_name character varying(60) NOT NULL
);


ALTER TABLE analytics.d_currency OWNER TO alex_analytics;

--
-- Name: d_expense_category; Type: TABLE; Schema: analytics; Owner: alex_analytics
--

CREATE TABLE analytics.d_expense_category (
    category_id uuid DEFAULT gen_random_uuid() NOT NULL,
    category_name character varying(60) NOT NULL
);


ALTER TABLE analytics.d_expense_category OWNER TO alex_analytics;

--
-- Name: TABLE d_expense_category; Type: COMMENT; Schema: analytics; Owner: alex_analytics
--

COMMENT ON TABLE analytics.d_expense_category IS 'Expense category dimension. One row per category. Managed as data to allow additions without schema migrations (BR-021).';


--
-- Name: d_industry; Type: TABLE; Schema: analytics; Owner: alex_analytics
--

CREATE TABLE analytics.d_industry (
    industry_id uuid DEFAULT gen_random_uuid() NOT NULL,
    name character varying(60) NOT NULL,
    display_cncy character varying(3) NOT NULL
);


ALTER TABLE analytics.d_industry OWNER TO alex_analytics;

--
-- Name: TABLE d_industry; Type: COMMENT; Schema: analytics; Owner: alex_analytics
--

COMMENT ON TABLE analytics.d_industry IS 'Industry dimension. One row per industry.';


--
-- Name: COLUMN d_industry.display_cncy; Type: COMMENT; Schema: analytics; Owner: alex_analytics
--

COMMENT ON COLUMN analytics.d_industry.display_cncy IS 'Display currency inherited by member companies in comparison views (BR-007, BR-008).';


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
-- Name: f_expense; Type: TABLE; Schema: analytics; Owner: alex_analytics
--

CREATE TABLE analytics.f_expense (
    expense_id uuid DEFAULT gen_random_uuid() NOT NULL,
    amount numeric(18,4) NOT NULL,
    cncy character varying(3) NOT NULL,
    c_id uuid NOT NULL,
    time_id uuid NOT NULL,
    category_id uuid NOT NULL
);


ALTER TABLE analytics.f_expense OWNER TO alex_analytics;

--
-- Name: TABLE f_expense; Type: COMMENT; Schema: analytics; Owner: alex_analytics
--

COMMENT ON TABLE analytics.f_expense IS 'Expense fact table. Grain: one expense event for one company at one point in time (BR-019). USD only until multi-currency support is implemented (BR-022).';


--
-- Name: COLUMN f_expense.amount; Type: COMMENT; Schema: analytics; Owner: alex_analytics
--

COMMENT ON COLUMN analytics.f_expense.amount IS 'Expense amount in the recorded currency. Currently expected to be USD (BR-022).';


--
-- Name: COLUMN f_expense.cncy; Type: COMMENT; Schema: analytics; Owner: alex_analytics
--

COMMENT ON COLUMN analytics.f_expense.cncy IS 'Currency of the expense amount. FK to d_currency (BR-005).';


--
-- Name: COLUMN f_expense.time_id; Type: COMMENT; Schema: analytics; Owner: alex_analytics
--

COMMENT ON COLUMN analytics.f_expense.time_id IS 'FK to d_time. Timestamp is the single source of truth for when the expense occurred, consistent with f_transaction (BR-018).';


--
-- Name: COLUMN f_expense.category_id; Type: COMMENT; Schema: analytics; Owner: alex_analytics
--

COMMENT ON COLUMN analytics.f_expense.category_id IS 'FK to d_expense_category. Required â€” every expense must be categorized (BR-020).';


--
-- Name: f_fx_rate; Type: TABLE; Schema: analytics; Owner: alex_analytics
--

CREATE TABLE analytics.f_fx_rate (
    fx_id uuid DEFAULT gen_random_uuid() NOT NULL,
    rate numeric(14,7) CONSTRAINT f_fx_rate_amount_not_null NOT NULL,
    base_cncy character varying(3) NOT NULL,
    quote_cncy character varying(3) NOT NULL
);


ALTER TABLE analytics.f_fx_rate OWNER TO alex_analytics;

--
-- Name: f_industry; Type: TABLE; Schema: analytics; Owner: alex_analytics
--

CREATE TABLE analytics.f_industry (
    industry_id uuid NOT NULL,
    time_id uuid NOT NULL,
    total_revenue numeric(18,4) NOT NULL,
    total_expenses numeric(18,4) NOT NULL,
    net_profit numeric(18,4) NOT NULL,
    transaction_count integer NOT NULL,
    avg_revenue_per_co numeric(18,4) NOT NULL,
    revenue_growth_rate numeric(7,4),
    company_count smallint NOT NULL
);


ALTER TABLE analytics.f_industry OWNER TO alex_analytics;

--
-- Name: TABLE f_industry; Type: COMMENT; Schema: analytics; Owner: alex_analytics
--

COMMENT ON TABLE analytics.f_industry IS 'Industry aggregate fact table. Grain: one row per industry per day (BR-023). Populated by scheduled daily refresh â€” never updated in place (BR-024).';


--
-- Name: COLUMN f_industry.total_revenue; Type: COMMENT; Schema: analytics; Owner: alex_analytics
--

COMMENT ON COLUMN analytics.f_industry.total_revenue IS 'Sum of f_transaction.amount across all member companies for the period (BR-025).';


--
-- Name: COLUMN f_industry.total_expenses; Type: COMMENT; Schema: analytics; Owner: alex_analytics
--

COMMENT ON COLUMN analytics.f_industry.total_expenses IS 'Sum of f_expense.amount across all member companies for the period (BR-025).';


--
-- Name: COLUMN f_industry.net_profit; Type: COMMENT; Schema: analytics; Owner: alex_analytics
--

COMMENT ON COLUMN analytics.f_industry.net_profit IS 'total_revenue minus total_expenses for the period (BR-025).';


--
-- Name: COLUMN f_industry.transaction_count; Type: COMMENT; Schema: analytics; Owner: alex_analytics
--

COMMENT ON COLUMN analytics.f_industry.transaction_count IS 'Count of f_transaction rows across all member companies for the period (BR-025).';


--
-- Name: COLUMN f_industry.avg_revenue_per_co; Type: COMMENT; Schema: analytics; Owner: alex_analytics
--

COMMENT ON COLUMN analytics.f_industry.avg_revenue_per_co IS 'total_revenue divided by company_count for the period (BR-025).';


--
-- Name: COLUMN f_industry.revenue_growth_rate; Type: COMMENT; Schema: analytics; Owner: alex_analytics
--

COMMENT ON COLUMN analytics.f_industry.revenue_growth_rate IS 'Period-over-period percentage change in total_revenue. Computed at refresh time and stored directly. NULL for the first recorded period where no prior period exists (BR-026).';


--
-- Name: COLUMN f_industry.company_count; Type: COMMENT; Schema: analytics; Owner: alex_analytics
--

COMMENT ON COLUMN analytics.f_industry.company_count IS 'Number of distinct companies contributing to this row. Makes avg_revenue_per_co interpretable and signals membership changes between periods (BR-027).';


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
-- Name: expense_event; Type: TABLE; Schema: raw; Owner: alex_analytics
--

CREATE TABLE raw.expense_event (
    expense_id uuid DEFAULT gen_random_uuid() NOT NULL,
    c_id uuid NOT NULL,
    cncy character varying(3) NOT NULL,
    expense_timestamp timestamp with time zone CONSTRAINT expense_event_timestamp_not_null NOT NULL,
    amount numeric(18,4) NOT NULL,
    category_id uuid NOT NULL,
    ingestion_timestamp timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE raw.expense_event OWNER TO alex_analytics;

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
    quote_cncy character varying(3),
    fee_amount numeric(16,4)
);


ALTER TABLE raw.transaction_event OWNER TO alex_analytics;

--
-- Data for Name: d_company; Type: TABLE DATA; Schema: analytics; Owner: alex_analytics
--

COPY analytics.d_company (c_id, c_name, hq_country, default_cncy, industry_id) FROM stdin;
\.


--
-- Data for Name: d_currency; Type: TABLE DATA; Schema: analytics; Owner: alex_analytics
--

COPY analytics.d_currency (cncy_code, cncy_name) FROM stdin;
\.


--
-- Data for Name: d_expense_category; Type: TABLE DATA; Schema: analytics; Owner: alex_analytics
--

COPY analytics.d_expense_category (category_id, category_name) FROM stdin;
\.


--
-- Data for Name: d_industry; Type: TABLE DATA; Schema: analytics; Owner: alex_analytics
--

COPY analytics.d_industry (industry_id, name, display_cncy) FROM stdin;
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
-- Data for Name: f_expense; Type: TABLE DATA; Schema: analytics; Owner: alex_analytics
--

COPY analytics.f_expense (expense_id, amount, cncy, c_id, time_id, category_id) FROM stdin;
\.


--
-- Data for Name: f_fx_rate; Type: TABLE DATA; Schema: analytics; Owner: alex_analytics
--

COPY analytics.f_fx_rate (fx_id, rate, base_cncy, quote_cncy) FROM stdin;
\.


--
-- Data for Name: f_industry; Type: TABLE DATA; Schema: analytics; Owner: alex_analytics
--

COPY analytics.f_industry (industry_id, time_id, total_revenue, total_expenses, net_profit, transaction_count, avg_revenue_per_co, revenue_growth_rate, company_count) FROM stdin;
\.


--
-- Data for Name: f_transaction; Type: TABLE DATA; Schema: analytics; Owner: alex_analytics
--

COPY analytics.f_transaction (tx_id, amount, c_id, time_id, cncy) FROM stdin;
\.


--
-- Data for Name: expense_event; Type: TABLE DATA; Schema: raw; Owner: alex_analytics
--

COPY raw.expense_event (expense_id, c_id, cncy, expense_timestamp, amount, category_id, ingestion_timestamp) FROM stdin;
\.


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
-- Name: d_expense_category d_expense_category_name_unique; Type: CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.d_expense_category
    ADD CONSTRAINT d_expense_category_name_unique UNIQUE (category_name);


--
-- Name: d_expense_category d_expense_category_pkey; Type: CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.d_expense_category
    ADD CONSTRAINT d_expense_category_pkey PRIMARY KEY (category_id);


--
-- Name: d_industry d_industry_pkey; Type: CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.d_industry
    ADD CONSTRAINT d_industry_pkey PRIMARY KEY (industry_id);


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
-- Name: f_expense f_expense_pkey; Type: CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.f_expense
    ADD CONSTRAINT f_expense_pkey PRIMARY KEY (expense_id);


--
-- Name: f_fx_rate f_fx_rate_pkey; Type: CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.f_fx_rate
    ADD CONSTRAINT f_fx_rate_pkey PRIMARY KEY (fx_id);


--
-- Name: f_industry f_industry_pkey; Type: CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.f_industry
    ADD CONSTRAINT f_industry_pkey PRIMARY KEY (industry_id, time_id);


--
-- Name: f_transaction f_transaction_pkey; Type: CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.f_transaction
    ADD CONSTRAINT f_transaction_pkey PRIMARY KEY (tx_id);


--
-- Name: expense_event expense_event_pkey; Type: CONSTRAINT; Schema: raw; Owner: alex_analytics
--

ALTER TABLE ONLY raw.expense_event
    ADD CONSTRAINT expense_event_pkey PRIMARY KEY (expense_id);


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
-- Name: idx_d_company_industry_id; Type: INDEX; Schema: analytics; Owner: alex_analytics
--

CREATE INDEX idx_d_company_industry_id ON analytics.d_company USING btree (industry_id);


--
-- Name: idx_f_conversion_tx_id; Type: INDEX; Schema: analytics; Owner: alex_analytics
--

CREATE INDEX idx_f_conversion_tx_id ON analytics.f_conversion USING btree (tx_id);


--
-- Name: idx_f_expense_c_id; Type: INDEX; Schema: analytics; Owner: alex_analytics
--

CREATE INDEX idx_f_expense_c_id ON analytics.f_expense USING btree (c_id);


--
-- Name: idx_f_expense_category_id; Type: INDEX; Schema: analytics; Owner: alex_analytics
--

CREATE INDEX idx_f_expense_category_id ON analytics.f_expense USING btree (category_id);


--
-- Name: idx_f_expense_time_id; Type: INDEX; Schema: analytics; Owner: alex_analytics
--

CREATE INDEX idx_f_expense_time_id ON analytics.f_expense USING btree (time_id);


--
-- Name: idx_f_industry_time_id; Type: INDEX; Schema: analytics; Owner: alex_analytics
--

CREATE INDEX idx_f_industry_time_id ON analytics.f_industry USING btree (time_id);


--
-- Name: idx_f_transaction_c_id; Type: INDEX; Schema: analytics; Owner: alex_analytics
--

CREATE INDEX idx_f_transaction_c_id ON analytics.f_transaction USING btree (c_id);


--
-- Name: idx_f_transaction_time_id; Type: INDEX; Schema: analytics; Owner: alex_analytics
--

CREATE INDEX idx_f_transaction_time_id ON analytics.f_transaction USING btree (time_id);


--
-- Name: idx_expense_event_c_id_timestamp; Type: INDEX; Schema: raw; Owner: alex_analytics
--

CREATE INDEX idx_expense_event_c_id_timestamp ON raw.expense_event USING btree (c_id, expense_timestamp);


--
-- Name: idx_expense_event_ts_brin; Type: INDEX; Schema: raw; Owner: alex_analytics
--

CREATE INDEX idx_expense_event_ts_brin ON raw.expense_event USING brin (expense_timestamp);


--
-- Name: idx_fx_rate_ts_brin; Type: INDEX; Schema: raw; Owner: alex_analytics
--

CREATE INDEX idx_fx_rate_ts_brin ON raw.fx_rate USING brin (fx_timestamp);


--
-- Name: idx_tx_event_cncy_timestamp; Type: INDEX; Schema: raw; Owner: alex_analytics
--

CREATE INDEX idx_tx_event_cncy_timestamp ON raw.transaction_event USING btree (base_cncy, quote_cncy, tx_timestamp);


--
-- Name: f_conversion trg_validate_conversion_currency; Type: TRIGGER; Schema: analytics; Owner: alex_analytics
--

CREATE TRIGGER trg_validate_conversion_currency BEFORE INSERT OR UPDATE ON analytics.f_conversion FOR EACH ROW EXECUTE FUNCTION analytics.validate_conversion_currency();


--
-- Name: expense_event trg_expense_event_prevent_modification; Type: TRIGGER; Schema: raw; Owner: alex_analytics
--

CREATE TRIGGER trg_expense_event_prevent_modification BEFORE DELETE OR UPDATE ON raw.expense_event FOR EACH ROW EXECUTE FUNCTION raw.prevent_modification();


--
-- Name: d_company d_company_default_cncy_fkey; Type: FK CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.d_company
    ADD CONSTRAINT d_company_default_cncy_fkey FOREIGN KEY (default_cncy) REFERENCES analytics.d_currency(cncy_code);


--
-- Name: d_company d_company_industry_id_fkey; Type: FK CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.d_company
    ADD CONSTRAINT d_company_industry_id_fkey FOREIGN KEY (industry_id) REFERENCES analytics.d_industry(industry_id);


--
-- Name: d_industry d_industry_display_cncy_fkey; Type: FK CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.d_industry
    ADD CONSTRAINT d_industry_display_cncy_fkey FOREIGN KEY (display_cncy) REFERENCES analytics.d_currency(cncy_code);


--
-- Name: f_expense f_expense_c_id_fkey; Type: FK CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.f_expense
    ADD CONSTRAINT f_expense_c_id_fkey FOREIGN KEY (c_id) REFERENCES analytics.d_company(c_id);


--
-- Name: f_expense f_expense_category_id_fkey; Type: FK CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.f_expense
    ADD CONSTRAINT f_expense_category_id_fkey FOREIGN KEY (category_id) REFERENCES analytics.d_expense_category(category_id);


--
-- Name: f_expense f_expense_cncy_fkey; Type: FK CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.f_expense
    ADD CONSTRAINT f_expense_cncy_fkey FOREIGN KEY (cncy) REFERENCES analytics.d_currency(cncy_code);


--
-- Name: f_expense f_expense_time_id_fkey; Type: FK CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.f_expense
    ADD CONSTRAINT f_expense_time_id_fkey FOREIGN KEY (time_id) REFERENCES analytics.d_time(time_id);


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
-- Name: f_industry f_industry_industry_id_fkey; Type: FK CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.f_industry
    ADD CONSTRAINT f_industry_industry_id_fkey FOREIGN KEY (industry_id) REFERENCES analytics.d_industry(industry_id);


--
-- Name: f_industry f_industry_time_id_fkey; Type: FK CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.f_industry
    ADD CONSTRAINT f_industry_time_id_fkey FOREIGN KEY (time_id) REFERENCES analytics.d_time(time_id);


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

\unrestrict U4RxpTABvr4zTZCaazfAw90Ss6qlleUjpeCASgb62RH0FCldvc8UwJLUhSHUANE


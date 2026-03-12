--
-- PostgreSQL database dump
--

\restrict nSR7gdU3AiiIkSTGAMhwUidFeD1tEiO8qNV5s7BFiVB5GKz7lwb9aoNj3ENsbaw

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

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: cncy_use; Type: TABLE; Schema: analytics; Owner: alex_analytics
--

CREATE TABLE analytics.cncy_use (
    tx_id uuid NOT NULL,
    cncy_code character varying(3) NOT NULL
);


ALTER TABLE analytics.cncy_use OWNER TO alex_analytics;

--
-- Name: d_company; Type: TABLE; Schema: analytics; Owner: alex_analytics
--

CREATE TABLE analytics.d_company (
    c_id uuid NOT NULL,
    c_name character varying(60) NOT NULL,
    industry character varying(60) NOT NULL,
    hq_country character varying(60) NOT NULL
);


ALTER TABLE analytics.d_company OWNER TO alex_analytics;

--
-- Name: d_currency; Type: TABLE; Schema: analytics; Owner: alex_analytics
--

CREATE TABLE analytics.d_currency (
    cncy_code character varying(3) NOT NULL,
    cncy_name character varying(60) NOT NULL
);


ALTER TABLE analytics.d_currency OWNER TO alex_analytics;

--
-- Name: d_time; Type: TABLE; Schema: analytics; Owner: alex_analytics
--

CREATE TABLE analytics.d_time (
    time_id uuid NOT NULL,
    t_stamp timestamp without time zone NOT NULL,
    fisc_quarter smallint NOT NULL,
    day_of_week smallint NOT NULL
);


ALTER TABLE analytics.d_time OWNER TO alex_analytics;

--
-- Name: f_fx_rate; Type: TABLE; Schema: analytics; Owner: alex_analytics
--

CREATE TABLE analytics.f_fx_rate (
    fx_id uuid NOT NULL,
    amount numeric(18,4) NOT NULL
);


ALTER TABLE analytics.f_fx_rate OWNER TO alex_analytics;

--
-- Name: f_transaction; Type: TABLE; Schema: analytics; Owner: alex_analytics
--

CREATE TABLE analytics.f_transaction (
    tx_id uuid NOT NULL,
    amount numeric(18,4) NOT NULL
);


ALTER TABLE analytics.f_transaction OWNER TO alex_analytics;

--
-- Name: reciept; Type: TABLE; Schema: analytics; Owner: alex_analytics
--

CREATE TABLE analytics.reciept (
    tx_id uuid NOT NULL,
    c_id uuid NOT NULL
);


ALTER TABLE analytics.reciept OWNER TO alex_analytics;

--
-- Name: tx_base; Type: TABLE; Schema: analytics; Owner: alex_analytics
--

CREATE TABLE analytics.tx_base (
    tx_id uuid NOT NULL,
    fx_id uuid NOT NULL
);


ALTER TABLE analytics.tx_base OWNER TO alex_analytics;

--
-- Name: tx_instance; Type: TABLE; Schema: analytics; Owner: alex_analytics
--

CREATE TABLE analytics.tx_instance (
    tx_id uuid NOT NULL,
    time_id uuid NOT NULL
);


ALTER TABLE analytics.tx_instance OWNER TO alex_analytics;

--
-- Name: tx_quote; Type: TABLE; Schema: analytics; Owner: alex_analytics
--

CREATE TABLE analytics.tx_quote (
    tx_id uuid NOT NULL,
    fx_id uuid NOT NULL
);


ALTER TABLE analytics.tx_quote OWNER TO alex_analytics;

--
-- Data for Name: cncy_use; Type: TABLE DATA; Schema: analytics; Owner: alex_analytics
--

COPY analytics.cncy_use (tx_id, cncy_code) FROM stdin;
\.


--
-- Data for Name: d_company; Type: TABLE DATA; Schema: analytics; Owner: alex_analytics
--

COPY analytics.d_company (c_id, c_name, industry, hq_country) FROM stdin;
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
-- Data for Name: f_fx_rate; Type: TABLE DATA; Schema: analytics; Owner: alex_analytics
--

COPY analytics.f_fx_rate (fx_id, amount) FROM stdin;
\.


--
-- Data for Name: f_transaction; Type: TABLE DATA; Schema: analytics; Owner: alex_analytics
--

COPY analytics.f_transaction (tx_id, amount) FROM stdin;
\.


--
-- Data for Name: reciept; Type: TABLE DATA; Schema: analytics; Owner: alex_analytics
--

COPY analytics.reciept (tx_id, c_id) FROM stdin;
\.


--
-- Data for Name: tx_base; Type: TABLE DATA; Schema: analytics; Owner: alex_analytics
--

COPY analytics.tx_base (tx_id, fx_id) FROM stdin;
\.


--
-- Data for Name: tx_instance; Type: TABLE DATA; Schema: analytics; Owner: alex_analytics
--

COPY analytics.tx_instance (tx_id, time_id) FROM stdin;
\.


--
-- Data for Name: tx_quote; Type: TABLE DATA; Schema: analytics; Owner: alex_analytics
--

COPY analytics.tx_quote (tx_id, fx_id) FROM stdin;
\.


--
-- Name: cncy_use cncy_use_pkey; Type: CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.cncy_use
    ADD CONSTRAINT cncy_use_pkey PRIMARY KEY (tx_id, cncy_code);


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
-- Name: reciept reciept_pkey; Type: CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.reciept
    ADD CONSTRAINT reciept_pkey PRIMARY KEY (tx_id, c_id);


--
-- Name: tx_base tx_base_pkey; Type: CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.tx_base
    ADD CONSTRAINT tx_base_pkey PRIMARY KEY (tx_id, fx_id);


--
-- Name: tx_instance tx_instance_pkey; Type: CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.tx_instance
    ADD CONSTRAINT tx_instance_pkey PRIMARY KEY (tx_id, time_id);


--
-- Name: tx_quote tx_quote_pkey; Type: CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.tx_quote
    ADD CONSTRAINT tx_quote_pkey PRIMARY KEY (tx_id, fx_id);


--
-- Name: cncy_use cncy_use_cncy_code_fkey; Type: FK CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.cncy_use
    ADD CONSTRAINT cncy_use_cncy_code_fkey FOREIGN KEY (cncy_code) REFERENCES analytics.d_currency(cncy_code);


--
-- Name: cncy_use cncy_use_tx_id_fkey; Type: FK CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.cncy_use
    ADD CONSTRAINT cncy_use_tx_id_fkey FOREIGN KEY (tx_id) REFERENCES analytics.f_transaction(tx_id);


--
-- Name: reciept reciept_c_id_fkey; Type: FK CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.reciept
    ADD CONSTRAINT reciept_c_id_fkey FOREIGN KEY (c_id) REFERENCES analytics.d_company(c_id);


--
-- Name: reciept reciept_tx_id_fkey; Type: FK CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.reciept
    ADD CONSTRAINT reciept_tx_id_fkey FOREIGN KEY (tx_id) REFERENCES analytics.f_transaction(tx_id);


--
-- Name: tx_base tx_base_fx_id_fkey; Type: FK CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.tx_base
    ADD CONSTRAINT tx_base_fx_id_fkey FOREIGN KEY (fx_id) REFERENCES analytics.f_fx_rate(fx_id);


--
-- Name: tx_base tx_base_tx_id_fkey; Type: FK CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.tx_base
    ADD CONSTRAINT tx_base_tx_id_fkey FOREIGN KEY (tx_id) REFERENCES analytics.f_transaction(tx_id);


--
-- Name: tx_instance tx_instance_time_id_fkey; Type: FK CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.tx_instance
    ADD CONSTRAINT tx_instance_time_id_fkey FOREIGN KEY (time_id) REFERENCES analytics.d_time(time_id);


--
-- Name: tx_instance tx_instance_tx_id_fkey; Type: FK CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.tx_instance
    ADD CONSTRAINT tx_instance_tx_id_fkey FOREIGN KEY (tx_id) REFERENCES analytics.f_transaction(tx_id);


--
-- Name: tx_quote tx_quote_fx_id_fkey; Type: FK CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.tx_quote
    ADD CONSTRAINT tx_quote_fx_id_fkey FOREIGN KEY (fx_id) REFERENCES analytics.f_fx_rate(fx_id);


--
-- Name: tx_quote tx_quote_tx_id_fkey; Type: FK CONSTRAINT; Schema: analytics; Owner: alex_analytics
--

ALTER TABLE ONLY analytics.tx_quote
    ADD CONSTRAINT tx_quote_tx_id_fkey FOREIGN KEY (tx_id) REFERENCES analytics.f_transaction(tx_id);


--
-- PostgreSQL database dump complete
--

\unrestrict nSR7gdU3AiiIkSTGAMhwUidFeD1tEiO8qNV5s7BFiVB5GKz7lwb9aoNj3ENsbaw


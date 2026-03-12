CREATE TABLE analytics.f_transaction (
    tx_id UUID PRIMARY KEY,
    amount NUMERIC(18, 4) NOT NULL
);

CREATE TABLE analytics.f_fx_rate (
    fx_id UUID PRIMARY KEY,
    amount NUMERIC(18, 4) NOT NULL
);

CREATE TABLE analytics.d_time (
    time_id UUID PRIMARY KEY,
    t_stamp TIMESTAMP NOT NULL,
    fisc_quarter SMALLINT NOT NULL,
    day_of_week SMALLINT NOT NULL
);

CREATE TABLE analytics.d_company (
    c_id UUID PRIMARY KEY,
    c_name VARCHAR(60) NOT NULL,
    industry VARCHAR(60) NOT NULL,
    hq_country VARCHAR(60) NOT NULL
);

CREATE TABLE analytics.d_currency (
    cncy_code VARCHAR(3) PRIMARY KEY,
    cncy_name VARCHAR(60) NOT NULL
);

CREATE TABLE analytics.reciept (
    tx_id UUID NOT NULL,
    c_id UUID NOT NULL,
    PRIMARY KEY (tx_id, c_id),
    FOREIGN KEY (tx_id) REFERENCES analytics.f_transaction(tx_id),
    FOREIGN KEY (c_id) REFERENCES analytics.d_company(c_id)
);

CREATE TABLE analytics.cncy_use (
    tx_id UUID NOT NULL,
    cncy_code VARCHAR(3) NOT NULL,
    PRIMARY KEY (tx_id, cncy_code),
    FOREIGN KEY (tx_id) REFERENCES analytics.f_transaction(tx_id),
    FOREIGN KEY (cncy_code) REFERENCES analytics.d_currency(cncy_code)
);

CREATE TABLE analytics.tx_instance (
    tx_id UUID NOT NULL,
    time_id UUID NOT NULL,
    PRIMARY KEY (tx_id, time_id),
    FOREIGN KEY (tx_id) REFERENCES analytics.f_transaction(tx_id),
    FOREIGN KEY (time_id) REFERENCES analytics.d_time(time_id)
);

CREATE TABLE analytics.tx_base (
    tx_id UUID NOT NULL,
    fx_id UUID NOT NULL,
    PRIMARY KEY (tx_id, fx_id),
    FOREIGN KEY (tx_id) REFERENCES analytics.f_transaction(tx_id),
    FOREIGN KEY (fx_id) REFERENCES analytics.f_fx_rate(fx_id)
);

CREATE TABLE analytics.tx_quote (
    tx_id UUID NOT NULL,
    fx_id UUID NOT NULL,
    PRIMARY KEY (tx_id, fx_id),
    FOREIGN KEY (tx_id) REFERENCES analytics.f_transaction(tx_id),
    FOREIGN KEY (fx_id) REFERENCES analytics.f_fx_rate(fx_id)
);
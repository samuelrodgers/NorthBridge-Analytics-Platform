-- Currency conversion validation trigger

CREATE OR REPLACE FUNCTION analytics.validate_conversion_currency()
RETURNS trigger AS $$
DECLARE
    v_tx_cncy varchar(3);
    v_quote_cncy varchar(3);
BEGIN
    -- Get transaction currency
    SELECT cncy
    INTO v_tx_cncy
    FROM analytics.f_transaction
    WHERE tx_id = NEW.tx_id;

    -- Get FX quote currency
    SELECT quote_cncy
    INTO v_quote_cncy
    FROM analytics.f_fx_rate
    WHERE fx_id = NEW.fx_id;

    -- Validate
    IF v_tx_cncy IS DISTINCT FROM v_quote_cncy THEN
        RAISE EXCEPTION
        'Transaction currency (%) does not match FX quote currency (%)',
        v_tx_cncy, v_quote_cncy;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Attach to f_conversion

CREATE TRIGGER trg_validate_conversion_currency
BEFORE INSERT OR UPDATE ON analytics.f_conversion
FOR EACH ROW
EXECUTE FUNCTION analytics.validate_conversion_currency();

-- CX Trigger

CREATE OR REPLACE FUNCTION analytics.apply_conversion()
RETURNS trigger AS $$
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
$$ LANGUAGE plpgsql;


-- Apply to f_conversion

CREATE TRIGGER trg_apply_conversion
AFTER INSERT OR UPDATE ON analytics.f_conversion
FOR EACH ROW
EXECUTE FUNCTION analytics.apply_conversion();

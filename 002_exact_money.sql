ALTER TABLE products ALTER COLUMN price TYPE NUMERIC(12,2) USING round(price::numeric,2);
ALTER TABLE products ALTER COLUMN promo_percent TYPE NUMERIC(5,2) USING round(promo_percent::numeric,2);
ALTER TABLE orders ALTER COLUMN subtotal TYPE NUMERIC(14,2) USING round(subtotal::numeric,2);
ALTER TABLE orders ALTER COLUMN total TYPE NUMERIC(14,2) USING round(total::numeric,2);

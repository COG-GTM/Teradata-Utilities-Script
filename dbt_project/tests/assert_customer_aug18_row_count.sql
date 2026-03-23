-- Fails if the row count of stg_customer_aug18 does not match the source customer table.
-- This verifies the migration of Condbteq.bteq which does: INSERT INTO customer_aug18 SELECT * FROM customer
SELECT
    src.src_count,
    tgt.tgt_count
FROM
    (SELECT COUNT(*) AS src_count FROM {{ source('financial', 'customer') }}) src,
    (SELECT COUNT(*) AS tgt_count FROM {{ ref('stg_customer_aug18') }}) tgt
WHERE src.src_count != tgt.tgt_count

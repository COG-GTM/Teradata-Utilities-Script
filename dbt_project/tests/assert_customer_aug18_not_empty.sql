-- Fails if stg_customer_aug18 has zero rows
SELECT 1
WHERE (SELECT COUNT(*) FROM {{ ref('stg_customer_aug18') }}) = 0

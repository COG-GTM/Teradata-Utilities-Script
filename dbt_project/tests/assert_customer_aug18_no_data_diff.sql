-- Fails if any rows exist in the source that are not in the target, or vice versa.
-- This is the definitive verification that the BTEQ migration is correct.
(SELECT * FROM {{ source('financial', 'customer') }}
EXCEPT
SELECT * FROM {{ ref('stg_customer_aug18') }})
UNION ALL
(SELECT * FROM {{ ref('stg_customer_aug18') }}
EXCEPT
SELECT * FROM {{ source('financial', 'customer') }})

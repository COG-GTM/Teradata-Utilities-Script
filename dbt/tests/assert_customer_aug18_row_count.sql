WITH source_count AS (
    SELECT COUNT(*) AS cnt FROM {{ source('financial', 'customer') }}
),
target_count AS (
    SELECT COUNT(*) AS cnt FROM {{ ref('customer_aug18') }}
)
SELECT
    source_count.cnt AS source_rows,
    target_count.cnt AS target_rows
FROM source_count
CROSS JOIN target_count
WHERE source_count.cnt != target_count.cnt

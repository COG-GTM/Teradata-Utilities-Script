{{ config(materialized='table') }}

SELECT
    cust_id,
    income,
    age,
    years_with_bank,
    nbr_children,
    gender,
    marital_status
FROM {{ source('financial', 'customer') }}

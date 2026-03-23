{{ config(materialized='table') }}

SELECT * FROM {{ source('financial', 'customer') }}

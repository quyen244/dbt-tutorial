{{ config(materialized='table') }}
{% set pattern  = 'Dunkirk' %}

SELECT * 
FROM {{ ref('films') }}
WHERE title = '{{ pattern }}'
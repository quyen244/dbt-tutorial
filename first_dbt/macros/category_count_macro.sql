{% macro generate_category_count() %}
with film_with_category as (
    SELECT f. * , fc.category_name
    FROM {{ ref('films') }} as f 
        JOIN {{ ref('film_category') }} as fc
            ON f.film_id = fc.film_id 
)
SELECT category_name, 
        count(*) as number_of_films
FROM film_with_category
GROUP BY category_name
ORDER BY number_of_films DESC
{% endmacro %}
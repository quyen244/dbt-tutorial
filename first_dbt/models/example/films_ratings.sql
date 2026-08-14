with films_with_ratings as (
    select film_id , title , release_date , price , rating , user_rating,
        CASE
            WHEN user_rating >= 4.5 THEN 'Excellent'
            WHEN user_rating >= 4.0 THEN 'Good'
            WHEN user_rating >= 3 THEN 'Average'
            ELSE 'Poor'
        END as film_rating
    FROM {{ ref('films') }}
),
films_with_actors as (
    SELECT 
        f.film_id, f.title, STRING_AGG(a.actor_name , ',') as actors
    FROM {{ ref('films') }} as f 
        LEFT JOIN {{ ref('film_actors') }} as fa
            ON f.film_id = fa.film_id
        LEFT JOIN {{ ref('actors') }} as a
            ON fa.actor_id = a.actor_id
    GROUP BY f.film_id, f.title 
)
SELECT fwr. * , fwa.actors 
FROM films_with_ratings as fwr 
    LEFT JOIN films_with_actors as fwa
        ON fwr.film_id = fwa.film_id
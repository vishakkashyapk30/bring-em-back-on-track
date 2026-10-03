-- TODO(WS-A): type casts and standardisation for model_scores.
select * from {{ source('bronze', 'model_scores') }}

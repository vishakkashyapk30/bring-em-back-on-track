-- TODO(WS-A): type casts and standardisation for collections_cases.
select * from {{ source('bronze', 'collections_cases') }}

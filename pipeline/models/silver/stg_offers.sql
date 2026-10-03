-- TODO(WS-A): type casts and standardisation for offers.
select * from {{ source('bronze', 'offers') }}

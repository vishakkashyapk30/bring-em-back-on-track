-- TODO(WS-A): type casts and standardisation for geo_reference.
select * from {{ source('bronze', 'geo_reference') }}

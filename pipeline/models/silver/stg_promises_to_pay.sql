-- TODO(WS-A): type casts and standardisation for promises_to_pay.
select * from {{ source('bronze', 'promises_to_pay') }}

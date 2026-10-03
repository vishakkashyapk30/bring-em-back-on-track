-- TODO(WS-A): type casts and standardisation for ops_events.
select * from {{ source('bronze', 'ops_events') }}

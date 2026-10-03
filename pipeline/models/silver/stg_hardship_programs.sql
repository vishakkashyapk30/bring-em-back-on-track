-- TODO(WS-A): type casts and standardisation for hardship_programs.
select * from {{ source('bronze', 'hardship_programs') }}

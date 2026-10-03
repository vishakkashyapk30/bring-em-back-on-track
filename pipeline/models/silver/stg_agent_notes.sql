-- TODO(WS-A): type casts and standardisation for agent_notes.
select * from {{ source('bronze', 'agent_notes') }}

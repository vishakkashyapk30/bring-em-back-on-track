-- TODO(WS-A): type casts and standardisation for reference_documents.
select * from {{ source('bronze', 'reference_documents') }}

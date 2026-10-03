-- Contract rule 9: _refreshed_at within 26 hours.
select * from {{ ref('c360_customer') }} where _refreshed_at < now() - interval 26 hour

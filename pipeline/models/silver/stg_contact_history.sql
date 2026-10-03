-- channel was renamed channel_v2 upstream on 26 Sep (REL-0926): one standard column.
select *, coalesce(nullif(channel_v2, ''), nullif(channel, '')) as channel_std
from {{ source('bronze', 'contact_history') }}

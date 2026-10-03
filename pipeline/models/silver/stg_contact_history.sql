-- channel was replaced by channel_v2 on 26 Sep (upstream release). Coalesce into one column (S3).
-- TODO(WS-A): confirm value mapping between channel and channel_v2.
select *, coalesce(channel_v2, channel) as channel_std
from {{ source('bronze', 'contact_history') }}

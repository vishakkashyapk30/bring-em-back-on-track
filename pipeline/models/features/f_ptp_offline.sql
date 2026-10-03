-- Offline store (training): every resolved promise, features as of the moment it was made (point in time).
-- Label: broken or partly kept after due date + grace = 1, kept = 0. Open/cancelled promises are not labelled.
-- Promises due during the INC-0914 payment-posting outage (14 Sep 2026) are excluded from labels.
with f as ({{ ptp_features('p.ptp_created_ts') }})
select f.*,
       case when f.ptp_status in ('broken', 'partially_kept') then 1 when f.ptp_status = 'kept' then 0 end as label_broken,
       f.ptp_due_date = date '2026-09-14' as excluded_outage
from f

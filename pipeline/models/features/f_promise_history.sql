-- Feature group "promise history" per promise, as of ptp creation (PIT). TODO(WS-C).
select ptp_id, crm_customer_id, ptp_status from {{ ref('stg_promises_to_pay') }}

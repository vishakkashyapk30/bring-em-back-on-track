-- Online customer vector for the C360 screen and the NBA rules (structured + text), latest values per golden ID.
with notes as (
    select x.golden_id,
           arg_max(n.hardship_signal, n.available_ts) as last_note_hardship_signal,
           arg_max(n.stated_delay_reason, n.available_ts) as last_stated_delay_reason,
           count(*) filter (where n.hardship_signal <> 'none' and n.available_ts >= timestamp '2026-09-28' - interval 90 day) as text_hardship_mentions_90d
    from {{ source('features', 'note_features') }} n
    join {{ source('identity', 'case_xref') }} x on x.case_id = n.case_id
    group by 1
),
calls as (
    select x.golden_id, arg_max(t.hardship_signal, t.available_ts) as last_call_hardship_signal,
           arg_max(t.next_step, t.available_ts) as last_call_next_step
    from {{ source('features', 'transcript_features') }} t
    join {{ source('identity', 'case_xref') }} x on x.case_id = t.case_id
    group by 1
),
ptp as (
    select x.golden_id,
           count(*) filter (where p.ptp_status in ('broken', 'partially_kept') and p.status_ts >= timestamp '2026-09-28' - interval 90 day) as ptp_broken_count_90d,
           count(*) filter (where p.ptp_status = 'open') as open_promises
    from {{ ref('promises_to_pay') }} p join {{ source('identity', 'case_xref') }} x on x.case_id = p.case_id
    group by 1
),
dep as (
    select a.golden_id, max(d.nsf_count_mtd) as nsf_count_mtd, max(d.days_negative_mtd) as days_negative_mtd,
           bool_or(d.high_cost_lender_txn_flag) as high_cost_lender_txn_flag, bool_or(d.ei_deposit_flag) as ei_deposit_flag,
           max(d.payroll_amount_change_pct) as payroll_amount_change_pct
    from {{ ref('stg_deposit_accounts') }} d join {{ source('identity', 'account_xref') }} a
      on a.source_system = 'core_banking' and a.account_id = d.account_id
    group by 1
),
bureau as (
    select k.golden_id, max(e.risk_score) as bureau_risk_score, max(e.risk_score_delta_90d) as bureau_score_delta_90d,
           max(e.bnpl_trades_count) as bnpl_trades_count, max(e.off_us_delinquent_trades) as off_us_delinquent_trades
    from {{ ref('stg_external') }} e join {{ source('identity', 'source_key_xref') }} k
      on k.source_system = 'bureau' and k.source_ref = e.bank_subject_ref
    group by 1
)
select c.golden_id, c.max_dpd as dpd_max_current, c.total_past_due_cad, c.payroll_delay_days, c.hardship_flag,
       c.vulnerability_flag, c.open_case_id,
       coalesce(p.ptp_broken_count_90d, 0) as ptp_broken_count_90d, coalesce(p.open_promises, 0) as open_promises,
       d.nsf_count_mtd, d.days_negative_mtd, d.high_cost_lender_txn_flag, d.ei_deposit_flag, d.payroll_amount_change_pct,
       b.bureau_risk_score, b.bureau_score_delta_90d, b.bnpl_trades_count, b.off_us_delinquent_trades,
       n.last_note_hardship_signal, n.last_stated_delay_reason, coalesce(n.text_hardship_mentions_90d, 0) as text_hardship_mentions_90d,
       ca.last_call_hardship_signal, ca.last_call_next_step,
       timestamp '2026-09-28 06:00:00' as as_of_ts
from {{ ref('c360_customer') }} c
left join ptp p using (golden_id)
left join dep d using (golden_id)
left join bureau b using (golden_id)
left join notes n using (golden_id)
left join calls ca using (golden_id)
where c.open_case_id is not null

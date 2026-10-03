{{ config(severity='warn') }}
-- Contract rule 3: max_dpd > 0 implies total_past_due_cad > 0 (warn: some products report DPD before an amount).
select golden_id, max_dpd, total_past_due_cad from {{ ref('c360_customer') }}
where max_dpd > 0 and total_past_due_cad <= 0

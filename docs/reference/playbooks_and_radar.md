# Employer radar, playbooks, outage shield and schema drift

Four capabilities that were first left as design only (design_changes.md #20) and are now built. All of them are rules
and arithmetic, need no language model, and work with `LLM_PROVIDER=offline`.

## S1 employer shock radar (`decisioning/radar.py`)

Weekly, per employer (the name is shown only as a hashed `EMP-xxxxxxxx` key), for employers with at least 10 customers.
Smaller groups are dropped inside the function, so they never reach a screen or the API.

| Measure | Definition |
|---|---|
| Payroll gap | `deposit_accounts.payroll_delay_days` above 7 |
| New EI | `ei_deposit_flag` with `ei_first_deposit_date` in the last 30 days |
| Pay change | average `payroll_amount_change_pct`, beside the employer's own earlier weeks and its industry peers (`industry_naics2`) |
| Open cases and exposure | open `collections_cases` and their `total_exposure` |

A pattern needs at least 5 late payrolls, at least 25% of the employer's customers, and (when peers exist) at least twice the
peers' rate and a surprise test (binomial tail, Bonferroni corrected over all employers that week, alpha 0.01) so that
thousands of employers do not produce false alarms. The baseline is built from quiet employers so one cluster cannot hide
another. A gap with new EI for at least 30% of the late customers is `layoff_like`; a gap without it is `payroll_delay`.
`ops_events` that touch `deposit_accounts` and overlap the week are shown first (`explained_by_incident`).
Every label says it is a radar, not a layoff detector, because no field says a person lost a job.

On the real release the radar finds no cluster (profiling: 7.3% late payroll in Windsor-Essex manufacturing against 7.8%
elsewhere). `GET /api/radar` says so: "No cluster". The known `ECO-0715` external event is listed as context. Own-history
comparison shows n/a because the release holds one full weekly snapshot.

## Playbook proposals (`decisioning/playbooks.py`)

Proposals are created `pending_approval` and wait for a team lead. Nothing runs by itself.

| Source | Proposals |
|---|---|
| Employer radar, `layoff_like` | `hold` for customers already behind, `contact` for customers not yet behind |
| Employer radar, `payroll_delay` or a known incident | `hold` only |
| Weather map areas with at least 10 customers and a high broken-promise rate | regional `hold` and `contact` |
| Outage shield | `fee_reversal` and `pressure_hold` |

A `contact` proposal for customers not yet behind has `requires_policy_office_signoff` true. Approving (team lead only)
is audited with `governance.audit.record` and creates one row in `batches` (kinds `radar_playbook` or `outage_playbook`)
with the 2% sample. A sign-off batch starts as `awaiting_policy_office` and is not offered for sending. Approving never
contacts anyone.

## H5 outage-victim shield (`decisioning/outage_shield.py`)

Takes payment outage windows from `silver.ops_events` (INC-0914, 14 Sep, payments not posted until the next day) and finds
due items in the window that were paid the next day, from `card_statements`, `loan_instalments` and `promises_to_pay`.
It is a candidate list: payment attempt times exist only for a sample, so the count (69 on the real release) is shown
beside the bank's estimate (1,900) and never presented as final. Contacts already tagged with the incident are counted.

## S3 schema drift (`governance/drift.py`)

Per load: row count, null rate, new or missing columns, type changes. Renames are paired by name and type
(`channel` to `channel_v2`, release `REL-0926`, 26 Sep). A fix is drafted as a diff for the silver model by the offline
handler of prompt `drift_fix`; a language model may only reword the explanation, never the diff. The fix is
`pending_engineer_approval`, never applied by the app. Only the data steward may approve it, and the approval is audited.
On the real warehouse the draft notes that `stg_contact_history.sql` already reads `channel_v2`.

## API

| Route | Roles |
|---|---|
| `GET /api/radar` | team lead, analyst |
| `GET /api/playbooks`, `POST /api/playbooks/{id}/approve` | team lead |
| `GET /api/drift` | steward, analyst |
| `POST /api/drift/{id}/approve` | steward |

Proposals and fixes are stored in `data/ops.db` (`playbook_proposals`, `drift_fixes`, created on first use).
`decisioning.playbooks.generate_from_warehouse()` is the nightly entry point for the radar and the shield.

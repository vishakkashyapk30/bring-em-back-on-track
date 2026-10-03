-- Online store (live scoring): open promises, the SAME feature definition evaluated as of the scoring time.
{{ ptp_features("timestamp '" ~ var('as_of_ts', '2026-09-28 23:59:59') ~ "'", "p.ptp_status = 'open'") }}

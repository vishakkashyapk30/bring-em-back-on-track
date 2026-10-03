-- Hardship specialist view: customers with hardship possible/confirmed or vulnerability.
select * from {{ ref('c360_customer') }}
where hardship_flag <> 'none' or vulnerability_flag

-- Contract rule 8: no protected-attribute column exists in gold.c360_customer.
select column_name
from information_schema.columns
where table_schema = 'gold' and table_name = 'c360_customer'
  and lower(column_name) in ('gender_code','marital_status','citizenship_status','household_size',
      'dependants_count','newcomer_program_flag','newcomer_arrival_date','accessibility_needs_flag',
      'accessibility_type','vulnerability_type','ccb_deposit_flag','customer_accent_region','age','age_band')

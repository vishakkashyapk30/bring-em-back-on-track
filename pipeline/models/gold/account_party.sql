-- Roles per account: primary / joint (joint_holder_ref) / co_borrower (co_borrower_ref). TODO(WS-A).
select account_id, src_customer_ref as party_ref, 'primary' as role from {{ ref('c360_account') }}

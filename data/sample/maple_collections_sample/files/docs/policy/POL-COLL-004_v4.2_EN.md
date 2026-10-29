> Synthetic document created for the Maple Bank collections hackathon. Not legal advice; not a real policy.

# Collections Hardship and Vulnerable Customers Policy (POL-COLL-004, v4.2)

Effective 2026-03-01. Replaces v4.1 (2025-03-01).

## §4.1 Purpose and scope
This policy sets how Maple Bank identifies and supports customers in financial hardship or in vulnerable
circumstances while an account is in collections. It applies to credit cards, personal loans, auto loans,
lines of credit, mortgages and overdraft facilities, in all provinces.

## §4.2 Recognising hardship and offering options
Financial hardship is a temporary or lasting inability to meet payments because of a change in
circumstances: reduced hours or pay, job loss, waiting for Employment Insurance (EI), illness or disability,
bereavement, separation, a strike or lockout, a natural disaster or evacuation, or a payment increase after a
rate reset.

When a customer states a hardship the agent must:
1. Acknowledge it and record `hardship_flag` with the stated reason.
2. Offer at least one eligible option from the hardship programmes **before** asking for payment.
3. Not request a payment the customer has said they cannot afford.

Eligible options include:
- **3-month reduced payment (HP-LOAN-RED3)**: pay 50% of the regular payment for **3 months**; interest keeps
  accruing; the missed amount is added to the end of the term. Maximum days past due 90.
- **Reduced minimum payment (HP-CARD-MIN)** on cards for 3 months.
- **Reduced interest rate (HP-CARD-RATE)** for 6 months.
- **Payment deferral / skip a payment** (HP-CARD-SKIP, HP-LOAN-SKIP), once in 12 months.
- **Term extension (HP-LOAN-EXT)** up to 12 months, approved by a hardship specialist.
- **Debt management plan (HP-DMP)** when a non-profit credit counsellor represents the customer.

Customers in a bankruptcy or consumer proposal are not eligible (see §7.3 of POL-COLL-001).

## §4.3 Evidence
Income evidence is not required for programmes of 3 months or less. Term extensions and debt management
plans require evidence of income and expenses.

## §4.4 Hardship specialists
Cases with an accepted plan move to the `hardship_specialist` queue. Specialists review the plan monthly
and contact the customer 10 days before the plan ends.

## §4.5 Vulnerable customers
A customer may be vulnerable because of serious illness, mental health, cognitive decline, bereavement,
financial abuse, a difficult domestic situation, or a natural disaster. Vulnerability is a **safeguard,
never a risk factor**: it must not lower a customer's priority for help or be used to predict repayment.
Vulnerable customers are assigned to an agent who has completed vulnerable-customer certification
(`vulnerable_customer_certified`). Agents use script SCR-VUL-EN / SCR-VUL-FR, allow extra time, and may
pause contact for up to 30 days. Re-review the flag every 90 days.

## §4.6 Protected grounds
Decisions must never use protected grounds (for example gender, marital or family status, citizenship,
national or ethnic origin, religion, disability or age as a protected ground). Information a customer shares
about these grounds during a call must not be used in any decision and should not be written in notes.

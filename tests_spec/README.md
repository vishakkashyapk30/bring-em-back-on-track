# Specification-based test suite: "Bring em back on track" (CIBC Collections)

This is a black-box pytest suite written **only** from the requirements: the organisers' brief, the V1 and v2 system designs, the novel ideas register and the architecture diagram. It has never seen the implementation. Every test function's docstring cites the document and section it comes from.

Written by a separate agent that was given only the brief and the design docs (decision D18 in
[`docs/design_changes.md`](../docs/design_changes.md)). Its open questions were settled in
[`docs/profiling/profiling_decisions.md`](../docs/profiling/profiling_decisions.md) §3.

```
tests_spec/
    ├── README.md        this file
    ├── traceability.md  requirement -> tests, plus requirements that could not be tested
    ├── open_questions.md  ambiguities and V1/v2 contradictions to resolve
    ├── examples/null_adapter.py  a binding skeleton (binds nothing, so every test skips)
    ├── adapter.py       THE INTERFACE: Protocols, the SpecAdapterBase base class, data shapes
    ├── conftest.py      binding loader, NotImplementedError -> SKIP, markers
    ├── factories.py     synthetic builders (Ryan Mitchell and others)
    ├── helpers.py       small behaviour-level assertion helpers
    ├── spec_constants.py  named thresholds and values; TBC values marked
    ├── unit/            single rules and calculations      (213 functions, 427 cases)
    ├── integration/     behaviour across layers            ( 57 functions, 135 cases)
    └── system/          persona journeys via SystemClient  ( 45 functions,  88 cases)
```

## Running

From the repo root:

```bash
uv run pytest tests_spec -q                                   # no binding: all 650 SKIPPED
SPEC_ADAPTER=tests_spec.adapter_impl:make_adapter uv run pytest tests_spec -q   # against our system
uv run pytest tests_spec -m unit -q                           # one level
uv run pytest tests_spec -m "h1 or h2" -q                     # one capability
uv run pytest tests_spec -rs -q                               # show skip reasons
```

- With no binding, every test is **skipped**: zero errors and zero failures. This was checked: `650 skipped`.
- The time-zone tests use the standard-library `zoneinfo`. On systems without an IANA database (for example Windows), add `--with tzdata`.

## Writing the binding (`adapter_impl.py`)

1. Create `adapter_impl.py`, either next to `tests_spec/` (that directory is put on `sys.path`) or anywhere importable.
2. Subclass `tests_spec.adapter.SpecAdapterBase`. Every method raises `NotImplementedError`, so the tests that use it **skip** with the message `Binding does not implement this yet: adapter operation '<name>' is not bound`.
3. Override operations one at a time, mapping the spec's data shapes (dataclasses in `adapter.py`) to your code. Don't change the tests. If an operation is impossible to express, raise `NotImplementedError` and record why.
4. Provide a factory, for example `def make_adapter(): return MyAdapter()`, and set `SPEC_ADAPTER=adapter_impl:make_adapter`.
5. `reset()` must leave an empty, isolated system. It is called before every test.
6. `system_client()` returns a `SystemClient` for the persona journeys. `seed()` and `run_nightly()` are test-harness operations. `login(user_id, role, team_id)` returns a `Session`, and every Session call must enforce role-based access.

Interface conventions (also documented in `adapter.py`):

| Convention | Meaning |
|---|---|
| Enumerations | Lower-case strings from the docs: treatments `reminder, payment_link, plan_offer, specialist_referral, no_contact`; channels `call, sms, email, push, letter`; windows `morning, afternoon, evening, any`; hardship `none, possible, clear`; roles `agent, hardship_specialist, team_lead, analyst, data_steward` |
| Forbidden actions | Either raise `PermissionError` or return `ActionResult(allowed=False)` |
| Non-person approving a summary | Must raise `PermissionError` (or `ValueError`) |
| Time | Timezone-aware `datetime`; customer zones are IANA names (`America/Toronto`) |
| Fractions and money | Fractions are 0..1 (so `payment_reduction_pct=0.5` means 50%); money is CAD `float` |
| Source tables | `load_sources` / `seed` receive data-dictionary table and column names as quoted in the docs (`customers.consent_sms`, `deposit_accounts.payroll_delay_days`, ...). The binding maps them to its own loaders. |
| Labels | Matched case-insensitively as substrings: "model estimate, not cause and effect" (or "model-implied"), and "observed, not causal" |
| Observability | `audit_log()` returns append-only records. `llm_request_log()` returns prompts sent to an LLM (used to check that no raw PII is sent). `outbound_messages()` returns what actually left for customers. |

If one call raises `NotImplementedError`, only that test skips, so a partial binding gives partial, honest results.

## Markers

| Marker | Meaning |
|---|---|
| `unit`, `integration`, `system` | Level. Applied automatically from the folder. |
| `h1` ... `h5`, `s1` ... `s7`, `a1` ... `a3` | Novel capability IDs (V1 §7, `novel_ideas.md`) |
| `policy_gate`, `hardship`, `identity`, `contract`, `sql_guard`, `features`, `nba`, `summary`, `assist` | Functional area |
| `explanation`, `fairness`, `hitl`, `rbac`, `audit`, `governance` | Cross-cutting guarantees (Brief ground rules, V1 §10) |
| `demo` | The NI §8 Ryan Mitchell storyline |

## Test data

`factories.py` builds small synthetic records from the examples in the docs. No real or organiser dataset is used.

- **Ryan Mitchell** (Brief C360 mock-up and NI §8): Windsor ON, `America/Toronto`, Visa `C-88213` 38 DPD, loan `L-5538921`, chequing `CHQ-7730`, CRM `RYM-1142`. His payroll is 29 days late; his employer is "Lakeshore Auto Parts Ltd." and his pay deposit reads "LAKESHORE AUTO PTS PAY". Consent: call 08:00-20:00, SMS and email, no push. He has one broken promise (`PTP-0090311`) and an open one due 9 Oct, with stated payday 15 Oct. His names and birth dates appear in each source's own format.
- **Lakeshore cohort**: 12 colleagues with late pay, most with new Employment Insurance (EI) deposits, so the cohort (13 with Ryan) passes the 10-customer suppression rule.
- **Contrasting protected-attribute variants** (`PROTECTED_VARIANT_A` / `B`) for invariance tests, and a seeded **random population** of edge-case customers for guardrail property tests.
- **Incident INC-0914** (14 Sep app outage, about 1,900 affected) from NI H5, plus policy documents including a superseded version and a prompt-injection note.

## Assumptions

V1 is treated as the primary spec. Where V1 is silent and v2 is explicit, v2 is used and the docstring says "v2". Values the docs mark TBC are named constants in `spec_constants.py`. Tests that depend on an unresolved (`None`) constant skip. The main assumptions:

1. **Sundays:** V1 "never Sundays" wins over v2's `sunday_contact_permitted` exception (OPEN_QUESTIONS Q1).
2. **"Pressure actions"** = `reminder` and `payment_link`. Plan offers, specialist referrals and no contact are non-pressure (Q3).
3. **Hardship `clear`** is the highest, confirmed level, not "cleared" (Q2).
4. The **permitted-hours rule** is tested for calls only; the cap is tested per customer `contact_cap_7d` (Q7, Q8).
5. The **2% batch sample** is rounded up, with at least one item (Q9).
6. **Policy gate disposition:** blocks give `no_contact`, representatives give `route_to_person`, disputes give `paused`.
7. **Cards** only accept the payment-cut lever. Other levers come back in `rejected_levers`, which also makes the demo's term-extension step refused for Ryan's card (Q6).
8. **Overrides need a reason.** A forbidden action may raise or return `allowed=False`.
9. **Ladder thresholds are unknown**, so only clearly low (0.02) and clearly high (0.97) risks are used.
10. **Analysts** may be shown individual rows only with identity masked, or denied entirely (Q17).
11. Tests assert **behaviour and guarantees** (outputs, refusals, audit records, what reaches a customer), never internal structure.

See `traceability.md` for coverage and the list of 27 requirements that are not testable black-box, and `open_questions.md` for the decisions the team needs to make.

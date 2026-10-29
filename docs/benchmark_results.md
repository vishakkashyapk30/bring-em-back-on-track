# Benchmark results

The submission file is [`deliverables/benchmark_answers.csv`](../deliverables/benchmark_answers.csv): 50 answers, the 35 questions from the release and the 15 extra questions (BQ-101 to BQ-115) released on 4 Oct. Every answer was produced by the system as it is, with no hand edits. Each row has the answer, the SQL that produced it or the documents and sections it quotes, and whether the question was refused.

## How the answers were produced

The submission run uses Ask with the language model switched on (`LLM_PROVIDER=openai`, model `gpt-6-luna`, run on 4 Oct at about 18:55 IST):

```bash
LLM_PROVIDER=openai uv run python -m eval.run_benchmark --questions <extra_questions.csv>
```

The model never writes the numbers. Refusal rules, access checks and the SQL guard run before any model is called. Metric questions compile to SQL from the certified metric definitions in `semantic/registry.py`, so the numbers are the same with or without the model. The model is used in three places: it words policy answers from the quoted sections (each quote is checked against the document), it picks a certified metric for questions the rules do not recognise, and it writes guarded, read-only SQL for data questions no certified metric covers. In the final run, 12 of the 50 answers differ from the rules-only run. All 12 are policy answers worded by the model, and every number and refusal is identical.

Without a key the same command runs on rules only (`LLM_PROVIDER=offline`), which is what a judge gets from `docker compose up --build`. Both runs are kept in `reports/bench_runs/` (not in git).

## Score on the dev split

The release has gold answers for 21 of the 35 original questions (the dev split). We score them with our own approximation of the scorer in `eval/run_benchmark.py`: numbers within the question's tolerance, word overlap and the cited document for text answers, and refused or not for questions that must be refused.

| Run | Dev mean score (21 questions) |
|---|---:|
| Rules only (offline) | 0.994 |
| With gpt-6-luna (submitted) | 0.986 |

The small drop is in wording only. Two policy answers lose overlap with the gold text: BQ-019 (the model writes the same duties as full sentences) and BQ-026 (the model leaves out "interest keeps accruing"). The score is optimistic because we built against the dev split; the test split and the extra questions are the real check.

## The 15 extra questions

There are no gold answers for these, so we checked each one against the policy documents and the data by hand. The first run (18:30, rules only) got 4 of 15 right. Six problems in the system showed up; we fixed them in the system, not in the CSV, and reran.

| Question | What it asks | Final answer | Source | First run (18:30) |
|---|---|---|---|---|
| BQ-101 | Date of birth, phone and address of customers in bucket 151-180 | Refused: personal details are not available through Ask | refusal rules | Right |
| BQ-102 | Income evidence for the 3-month reduced payment programme | No, not needed for programmes of 3 months or less | POL-COLL-004 §4.3 | Right |
| BQ-103 | Customer says card charges are fraudulent | Open a dispute, pause payment requests on the disputed amount, transfer the fraud claim to the fraud team | PRC-COLL-012 §6.1 | Wrongly refused |
| BQ-104 | Last recorded call on CS-2026-453815 | Waiting for EI; promised $50 on 17 Oct; wants to complain; escalate to a supervisor | transcript 7510825 | Right |
| BQ-105 | When a contact-frequency complaint is recorded, and who it goes to | The same day, escalated to a team lead | POL-COLL-007 §8.1 | Wrong section (protected grounds) |
| BQ-106 | Prioritise calls by whether customers mention church | Refused: religion is a protected ground | refusal rules | Refused, but as a "forecast" |
| BQ-107 | Total overdue on open cases by primary product | Six rows, for example card 14,743,219.80 CAD on 38,320 cases | SQL | Wrongly refused |
| BQ-108 | Share of SMS payment links clicked in September 2026 | 12.1% of 40,665 links sent | SQL | Wrongly refused |
| BQ-109 | Move vulnerable customers to the bottom of the queue | No: vulnerability must not lower a customer's priority | POL-COLL-004 §4.5 | Wrong section (hardship queue) |
| BQ-110 | Open cases with a hardship flag, by queue | Five rows, for example hardship_specialist 12,171 | SQL | Wrongly refused |
| BQ-111 | Average days to cure by product, cures from 1 Jul to 28 Sep 2026 | 30.7 to 31.1 days by product | SQL | Wrong measure (cure rate) |
| BQ-112 | Promise-kept rate by channel the promise was taken on, due 1 to 20 Sep 2026 | Five rows, for example call 34.9% on 18,406 promises | SQL | Not split by channel |
| BQ-113 | Last recorded call on CS-2026-123126 | Reduced hours; promised $23 on 10 Oct; hardship plan review | transcript 3010363 | Right |
| BQ-114 | Permitted calling hours, and Sundays | 07:00 to 21:00 local time; Sundays 13:00 to 17:00 where Sunday contact is permitted | POL-COLL-001 §5.1 | Partial (Sundays only) |
| BQ-115 | Open cases on insolvency hold and their overdue amount | 6,581 cases, 9,305,609.24 CAD overdue | SQL | Wrong (all 96,000 open cases) |

## What we changed in the system

| Problem | Fix | Where |
|---|---|---|
| No measure for a total overdue amount (BQ-107, BQ-115) | New `total_overdue` metric: sum of `collections_cases.total_overdue` on open cases | `semantic/registry.py` |
| "Days to cure" was read as the cure rate (BQ-111) | New `days_to_cure` metric: average `days_to_cure` over cured cases, dated by `cure_date` | `semantic/registry.py` |
| No measure for payment-link clicks (BQ-108) | New `link_click_rate` metric: clicked links over links sent (`payment_link_id` present); the existing SMS filter applies | `semantic/registry.py` |
| Promises could not be split by channel (BQ-112) | The channel breakdown now covers promises (`promises_to_pay.ptp_channel`) | `semantic/registry.py` |
| No filters for a hardship flag or an insolvency hold (BQ-110, BQ-115) | Two filters added; "how many open collections cases" now maps to the open-case count | `semantic/registry.py` |
| "Going to church" was refused as a forecast (BQ-106) | Places of worship count as religion, and protected grounds are checked before the forecast rule, so the refusal gives the real reason | `nlq/refusal.py` |
| "Fraudulent" did not find the fraud paragraph (BQ-103) | "fraudulent" and "unauthorised" now also search for "fraud" | `rag/retrieve.py` |
| An unrelated second source was cited (the card fixed payment plan on BQ-103) | A second source is only cited if it covers the question too | `rag/answer.py` |

Each fix is general, not tied to the question's wording. Without the model, BQ-105, BQ-109 and BQ-114 are still weaker: the rules pick the wrong sentences or section. The model fixes those three from the same retrieved documents.

## Checks after the changes

- The 35 original questions: on the rules-only run, the only changes are three policy answers that dropped an unrelated second source (BQ-002, BQ-020, BQ-103) and the refusal reason for BQ-029, which is still refused. The dev score stays 0.994.
- Unit and constraint tests pass, and the independent spec suite passes 650 of 650 in offline mode. One constraint test was failing before these changes: the SQL prompt (`llm/prompts/nl_to_sql/v1.md`) named protected attributes in its list of things to decline. We reworded it without naming them.
- Lint (`ruff`) is clean.

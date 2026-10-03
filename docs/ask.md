# Layer 2: Collections Ask

Plain-English questions over the C360 and the policy documents, with the SQL or the sources shown on every answer, and refusals for anything out of scope. It runs fully offline (no LLM), so every answer is reproducible.

## How a question is answered

1. **Refusal rules** ([`nlq/refusal.py`](../nlq/refusal.py)). Refused before anything runs:
   - protected attributes (gender, marital status, citizenship and similar) are always refused; soft ones (disability, age and similar) are refused only when used to segment, list or rank customers
   - proxy decisions, such as treating customers differently by postal area
   - direct personal details (exporting names or phone numbers)
   - off-topic questions
2. **Call summaries** ([`decisioning/post_call.py`](../decisioning/post_call.py)). "Summarise the most recent call on case CS-…" finds the latest transcript and fills the gold summary template from rule-extracted fields. Sources: `transcript <id>`.
3. **Policy questions** ([`rag/`](../rag/)). BM25 retrieval over the current versions of the reference documents (superseded versions excluded) plus the QA checklist, one section per `§`, FAQ question or programme row.
   - **Precedence:** policy > regulatory summary > programme terms > procedure > call script > FAQ. This defuses the release's traps, for example the FAQ's outdated "6 months" programme length and the superseded call script's "5 calls a week".
   - **Coverage check:** an answer must contain the question's key terms, otherwise the next source is tried, then refused. No citation, no answer.
4. **Metric questions** ([`semantic/registry.py`](../semantic/registry.py), [`semantic/compiler.py`](../semantic/compiler.py)). The question is mapped onto a certified metric, dimensions, filters and a time range. Examples:
   - **metric:** broken-promise rate, average DPD, right-party contact rate
   - **dimensions:** queue, agent site, province, local hour, product, bucket, test cell
   - **filters:** randomised cases, outbound calls, hardship cases
   - **time range:** "in September 2026", "July-September", "the 12 months to…", "between 15 and 22 September… compared with the 8 days before"

   It then compiles to one SELECT over the typed release tables. Certified definitions carry their default filters, for example "open case" means `outcome IS NULL`, and promise rates exclude open and cancelled promises. Special templates cover roll rates between quarter-ends, period comparisons and a risk-ranked list of open promises.
5. **Guarded execution** ([`nlq/executor.py`](../nlq/executor.py)): read-only connection, table allowlist (no CRM customer table), SQL guard (single SELECT, no file functions, row limit), personal-detail columns blocked, groups under 10 suppressed.
6. **Answer with its working:** result table, the SQL, caveats (causal warnings outside randomised cells, incidents overlapping the period such as INC-0914), and a yes/no verdict for comparison questions.

## Benchmark

`make benchmark` answers all released questions as the system is and writes [`deliverables/benchmark_answers.csv`](../deliverables/benchmark_answers.csv). It also scores the dev split against the release's gold answers (numbers within each question's tolerance; key facts plus cited document for text answers; refusals must be refused).

| Released questions | Metric (SQL) | Policy (documents) | Call summaries | Refused | Dev split score (our scorer) | Slowest answer |
|---|---|---|---|---|---|---|
| 35 | 18 | 9 | 3 | 5 | 0.994 on 21 dev questions | about 0.3 s |

The dev split was used to develop the compiler, so the dev score is optimistic. The test split and the judges' live questions are the real check. Unseen phrasings tried during development are answered (for example "Which strategy worked best for unsecured loans in the last 90 days?", "What percentage of promises were kept in July 2026 by product?").

## Optional LLM

Every step has an offline implementation. An LLM provider (D13) can be added for question parsing and answer wording through `llm/client.py`. It would only widen coverage; certified metric SQL and refusals stay rule-based.

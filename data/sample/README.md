# The committed sample

`maple_collections_sample/` is a small, self-consistent slice of the Maple Bank collections release, in the release's own
layout and file formats, so the whole pipeline runs on it unchanged. It exists so that nobody needs the 13 GB dataset to
run this project.

**It is synthetic.** Every person, account, call, note and document comes from the public synthetic release (Maple Bank,
snapshot 2026-09-28). Names, phone numbers and emails are generated; none belongs to a real person.

## Size

| | |
|---|---|
| CRM records | 5,560 (about 5,150 distinct people after identity resolution) |
| Files | 1,703 |
| On disk | about 107 MB |
| Compressed (zip -9, a fair proxy for git) | about 25 MB |
| Budget | 60 MB compressed (checked by `tests/unit/test_sample.py`) |

| Table | Rows | Table | Rows |
|---|---:|---|---:|
| customers | 5,560 | contact_history | 66,391 |
| card_accounts | 3,917 | promises_to_pay | 6,556 |
| loan_accounts | 3,204 | agent_notes | 22,131 |
| deposit_accounts | 3,533 | call_transcripts (+ JSON files) | 1,597 |
| collections_cases | 5,873 | model_scores | 43,034 |
| external (bureau pulls) | 2,215 | offers | 1,237 |
| transactions | 173,824 | loan_instalments | 122,363 |
| card_statements | 46,424 | account_monthly_snapshot | 81,002 |
| bureau_history | 11,324 | salary_credit_history | 27,636 |

Small reference tables (agents, agent_shifts, channel_capacity, geo_reference, code_lookups, metric_definitions,
benchmark_questions, hardship_programs, qa_checklist, reference_documents, ops_events) and the 19 policy documents in
`files/docs` are copied whole.

## How it was drawn

`tools/make_sample.py` (run it with `make sample`; it needs the full release in `data/raw`). It is deterministic: seed
`20260928`, sorted output, so the same release gives byte-identical files (see `MANIFEST.csv`).

1. **Seeded stratified draw** over `customers.crm_customer_id` (4,800 records before the closure): customers with an open
   case (600), a hardship flag (350), broken promises (500), kept promises (400), a duplicate CRM record (300), a call
   transcript (350), an agent note (350), cases on the demo persona agents' queues (150), the owners of the public gold
   labels (about 970), and a plain uniform draw for the rest.
2. **Closure over the five customer keys** so identity resolution sees what it sees on the full data: CRM id to accounts
   (snapshots, salary credits, cases, promises), to card and loan `src_customer_ref` and the deposit CIF, to every
   account of those keys, to the CRM records that share a national-id hash or a `duplicate_of` link. That grows 4,800
   records to 5,560.
3. **Every row that belongs to them**: accounts, cases, contacts, promises, offers, notes, transcripts and their JSON
   files, model scores, assignment history, and the Parquet history (statements, instalments, transactions, snapshots,
   bureau, salary credits) by account id or CIF. Bureau and external rows follow the CIF.
4. **Quirks are kept on purpose**: mixed date formats, masked card phones, CIFs that lost their leading zeros, duplicate
   CRM records, mistyped CRM ids on a few cases, promises without an account id. The cleaning code has to meet them.
   Rows are byte-identical to the release (checked line by line against it).

## What is not in it

- Voice recordings (`files/voice`, about 2 MB per call). `voice_samples.csv` keeps the 126 rows of sampled calls, the WAVs
  are absent, and the app reports "no recording" for them.
- Anything outside the drawn customers. Totals, rates and model metrics therefore differ from the full release (see
  `docs/quickstart_sample.md`). The sample over-represents open, hardship and broken-promise customers, so base rates
  (for example the share of broken promises) are higher than in the full data.

Run the project on it with `make demo-data` (see `docs/quickstart_sample.md`).

## Source and licence

This sample is a subset of the Maple Bank Collections Hackathon dataset (`nuxsh/maple-collections-hackathon` on Hugging Face), which is licensed under CC BY 4.0. The rows are unchanged copies of rows in that release, selected by `tools/make_sample.py`. All data is synthetic. Credit for the dataset belongs to its authors; this repository's code is under the MIT licence, and the sample keeps the dataset's CC BY 4.0 licence.

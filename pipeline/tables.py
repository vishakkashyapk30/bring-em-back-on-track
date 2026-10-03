"""The 31 source tables from the data dictionary, with expected format."""

TABLES: dict[str, str] = {
    # Core
    "customers": "csv", "card_accounts": "csv", "loan_accounts": "csv", "deposit_accounts": "csv",
    "collections_cases": "csv", "contact_history": "csv", "promises_to_pay": "csv",
    # Unstructured
    # call_transcripts.csv is call level; turns live in files/transcripts/YYYY/MM/<transcript_id>.json
    "agent_notes": "csv", "call_transcripts": "csv", "voice_samples": "csv",
    # External
    "external": "csv",
    # History (Parquet by year)
    "loan_instalments": "parquet", "transactions": "parquet", "card_statements": "parquet",
    "account_monthly_snapshot": "parquet", "bureau_history": "parquet", "salary_credit_history": "parquet",
    # Decisioning
    "model_scores": "csv", "offers": "csv",
    # Semantic
    "metric_definitions": "csv", "benchmark_questions": "csv",
    # Policy
    "reference_documents": "csv", "hardship_programs": "csv", "qa_checklist": "csv",
    # Operations
    "agents": "csv", "case_assignment_history": "csv", "agent_shifts": "csv", "channel_capacity": "csv",
    "ops_events": "csv",
    # Reference
    "geo_reference": "csv", "code_lookups": "csv",
}

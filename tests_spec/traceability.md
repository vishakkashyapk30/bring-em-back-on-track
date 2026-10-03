# Traceability matrix

How requirements in the inputs map to the tests in `tests_spec/`. Paths are relative to `tests_spec/`. `u/` = `unit/`, `i/` = `integration/`, `s/` = `system/`. Each test's docstring repeats the exact source citation.

**Sources:** Brief = `brief/problem_statement.md`; V1 = `design/collections_system_design_V1.md` (primary); v2 = `design/collections_system_design_v2.md`; NI = `design/novel_ideas.md`; Arch = `design/architecture_v1.png`.

## 1. Brief ground rules and must-deliver items

| Requirement | Source | Tests |
|---|---|---|
| Publish a data contract (owner, schema, 3+ quality rules, allowed uses, refresh) | Brief Part 1 item 3; ground rules | `u/test_data_contract.py::test_contract_declares_owner_schema_rules_uses_and_refresh`, `::test_contract_owner_roles_match_the_design`, `::test_contract_prohibits_the_listed_uses` |
| Explain every decision to the agent | Brief Part 1 Rules; ground rules | `u/test_nba_rules.py::test_every_decision_has_a_three_part_explanation`, `::test_no_contact_decisions_are_explained_too`, `u/test_policy_gate.py::test_every_block_names_its_rule`, `u/test_eligibility.py::test_every_rule_is_shown_with_pass_or_fail`, `s/test_persona_journeys.py::test_agent_queue_items_are_explained_and_reviewable` |
| A human can review anything that affects a customer (human in the loop) | Brief Part 1 Rules; ground rules | `s/test_human_in_the_loop.py` (all), `u/test_review_batches.py`, `u/test_post_call_summary.py::test_draft_is_not_saved_until_an_agent_approves`, `::test_only_a_person_can_approve_a_summary`, `u/test_nba_rules.py::test_promise_what_if_saves_nothing` |
| No protected attributes in decisions | Brief Part 1 Rules; ground rules | `u/test_policy_gate.py::test_gate_outcome_ignores_each_protected_attribute`, `u/test_nba_rules.py::test_protected_attributes_never_change_the_decision`, `::test_risk_score_ignores_protected_features_passed_in`, `u/test_eligibility.py::test_protected_attributes_never_change_eligibility`, `u/test_plan_simulator.py::test_household_size_and_dependants_never_used`, `i/test_guardrails_population.py::test_swapping_all_protected_attributes_changes_nothing`, `s/test_persona_journeys.py::test_twins_differing_only_in_protected_attributes_get_the_same_treatment` |
| Flag financial hardship or vulnerability | Brief Part 1 Rules; ground rules | `u/test_hardship_latch.py` (all), `u/test_post_call_summary.py::test_hardship_cue_is_flagged_as_a_signal`, `i/test_summary_to_hardship.py` (all), `i/test_identity_to_nba.py::test_hardship_mention_on_the_case_raises_the_golden_hardship_flag` |
| L1 must deliver: C360 schema; customer ID matching across sources; one data contract with quality rules; a data quality report | Brief Layer 1 | `u/test_identity_rules.py`, `i/test_identity_to_nba.py::test_all_four_source_ids_resolve_to_one_golden_id`, `::test_golden_record_carries_the_c360_fields`, `::test_pipeline_quality_report_is_produced_and_clean`, `u/test_data_contract.py::test_report_lists_at_least_the_ten_contract_rules`, `s/test_persona_journeys.py::test_steward_sees_the_data_quality_report` |
| L1 "One customer, one ID" with match confidence; "Trusted, not just joined" (lineage, refresh time) | Brief Layer 1 example takeaways | `u/test_identity_rules.py::test_ryan_four_source_ids_resolve_to_one_golden_id`, `::test_match_confidence_is_shown_and_bounded`, `i/test_identity_to_nba.py::test_every_field_carries_lineage_and_a_refresh_time`, `s/test_demo_storyline.py::test_step2_one_view_links_his_records_and_shows_the_late_pay` |
| L2 must deliver: SQL or source shown for every answer; refusal outside allowed data | Brief Layer 2 | `u/test_ask_refusals.py` (all), `i/test_ask_pipeline.py::test_answer_sql_passes_the_guard_for_the_same_user`, `::test_refusal_returns_no_sql_and_no_rows`, `s/test_persona_journeys.py::test_analyst_asks_the_three_brief_questions` |
| L2 takeaways: show what it understood (editable tokens), show the working, follow-ups | Brief Layer 2 example | `u/test_ask_refusals.py::test_question_is_shown_as_editable_tokens`, `::test_corrected_tokens_change_the_answer`, `::test_answers_carry_follow_up_suggestions`, `::test_allowed_question_shows_its_working` |
| L3: SQL + LLM features; LLM features tested (prompt, version, accuracy); same values offline and online | Brief Layer 3 example takeaways | `u/test_fairness_and_registry.py::test_registry_records_owner_source_refresh_version_and_builder`, `::test_ai_features_carry_prompt_version_and_accuracy`, `i/test_feature_parity.py` (all) |
| L4 must deliver: working model or agent; feature store; explanation of each decision; where a human reviews or overrides | Brief Layer 3 (old numbering) / Part 1 Layer 4 | `u/test_nba_rules.py`, `i/test_identity_to_nba.py::test_nba_for_ryan_is_explained_with_his_own_facts`, `s/test_human_in_the_loop.py::test_override_is_logged_with_reason_and_replaces_the_proposal` |
| Governance through every layer: access control, monitoring, human review | Brief Part 1; Part 2 ecosystem | `s/test_rbac.py`, `s/test_human_in_the_loop.py::test_override_rate_is_monitored_with_a_25_percent_trigger`, `::test_guardrail_counters_are_zero_after_a_normal_day` |

## 2. Design sections (V1 primary; v2 where V1 is silent)

| Requirement | Source | Tests |
|---|---|---|
| 30-day cure rate definition; insolvency and deceased holds excluded | V1 §2; v2 §2 | `u/test_metrics_and_labels.py::test_thirty_day_cure_rate`, `::test_cure_rate_with_only_held_cases_is_undefined` |
| Guardrails stay at zero (pressure on hardship, cap breaches, out-of-hours) | V1 §2 | `i/test_guardrails_population.py::test_no_guardrail_is_breached`, `s/test_human_in_the_loop.py::test_guardrail_counters_are_zero_after_a_normal_day` |
| Override rate reviewed above 25% | V1 §2; v2 §2 | `s/test_human_in_the_loop.py::test_override_rate_is_monitored_with_a_25_percent_trigger` |
| Keep the incumbent ptp_break v2.1 unless beaten on the same later set | V1 §2, §6 step 2 | `u/test_nba_rules.py::test_keep_the_incumbent_unless_the_challenger_beats_it`, `::test_models_compared_on_different_sets_are_not_compared` |
| Current CRM rows only; no wide `_m01`-`_m12` columns in training | V1 §3 data flow | `u/test_identity_rules.py::test_name_and_birth_date_come_from_the_current_crm_record`, `i/test_feature_parity.py::test_wide_monthly_columns_are_not_training_inputs` |
| Matching passes: exact keys -> auto link; fuzzy; masked AI pair -> steward decides | V1 §3 table | `u/test_identity_rules.py::test_exact_key_duplicate_of_crm_id_links_deterministically`, `::test_shared_national_id_hash_links_crm_records`, `::test_messy_name_and_dob_formats_still_match`, `::test_review_items_show_masked_data_only`, `s/test_human_in_the_loop.py::test_identity_review_waits_for_the_steward`, `s/test_persona_journeys.py::test_steward_decides_an_identity_review_and_it_is_logged` |
| Safety: cannot-link on different national ID hashes; clusters over 5 CRM records to a person | V1 §3 Safety rules; v2 Guards | `u/test_identity_rules.py::test_cannot_link_two_different_national_id_hashes`, `::test_cannot_link_survives_transitive_chains`, `::test_large_cluster_goes_to_human_review`, `::test_cluster_of_five_crm_records_may_auto_link`, `i/test_identity_to_nba.py::test_conflicting_national_ids_block_a_merge_end_to_end` |
| Stable IDs across reruns; merges keep the older ID | V1 §3; v2 Stable IDs | `u/test_identity_rules.py::test_golden_ids_are_stable_across_reruns`, `::test_golden_ids_stay_stable_when_new_records_arrive`, `::test_merge_keeps_the_older_id`, `i/test_identity_to_nba.py::test_rerunning_the_pipeline_keeps_golden_ids` |
| Survivorship: name and DOB from current CRM; strictest consent and do-not-contact; hardship and vulnerability from any record; verified email | V1 §3; v2 Survivorship; contract | `u/test_identity_rules.py::test_consent_takes_the_most_restrictive_value`, `::test_cease_on_any_linked_record_applies_to_customer`, `::test_hardship_or_vulnerability_on_any_linked_record_applies`, `::test_name_and_birth_date_come_from_the_current_crm_record`, `::test_email_used_only_if_verified_and_not_bounced`, `i/test_identity_to_nba.py::test_most_restrictive_consent_survives_through_the_pipeline` |
| Semantic layer -> refuse by part -> SQL checker (read-only, allowlist, row filter, limit) | V1 §4 steps 1-3; v2 §4 | `u/test_sql_guard.py` (all), `u/test_ask_refusals.py::test_refusal_says_which_part_was_not_allowed`, `::test_prompt_injection_in_the_question_does_not_bypass_refusal` |
| Answer with rows, SQL, freshness, caveats; summary uses only those rows | V1 §4 step 5 | `i/test_ask_pipeline.py::test_answer_names_gold_data_products_and_is_fresh`, `::test_insight_uses_only_returned_rows` |
| Document search: current versions, right product, province and language; no source -> no answer; retrieved text is data | V1 §4; v2 §4 RAG; V1 §6 UC3 | `i/test_policy_answers.py` (all), `s/test_persona_journeys.py::test_agent_asks_a_policy_question_mid_call` |
| Row access: agents their own cases; analysts aggregates, groups under 10 suppressed | v2 §4; V1 §10 | `u/test_sql_guard.py::test_role_row_filter_is_applied_for_agents`, `::test_agent_cannot_remove_their_row_filter`, `i/test_ask_pipeline.py::test_agent_answers_only_cover_their_own_cases`, `::test_analyst_rows_are_aggregates_with_small_groups_suppressed`, `s/test_rbac.py::test_agent_sees_only_own_cases` |
| Feature registry: owner, source, refresh, version, built-by | V1 §5 | `u/test_fairness_and_registry.py::test_registry_records_owner_source_refresh_version_and_builder`, `::test_registry_contains_the_designed_text_features` |
| Offline and online from the same code; time-known on every value; nightly parity of 1,000 values | V1 §5; v2 §5 | `i/test_feature_parity.py::test_online_equals_offline_at_the_same_time`, `::test_nightly_parity_check_finds_no_mismatch`, `::test_every_value_carries_when_it_was_known`, `::test_point_in_time_excludes_a_break_not_yet_known`, `::test_offline_as_of_never_returns_values_from_the_future`, `::test_bureau_features_keep_their_pull_date` |
| Only agent-approved AI values reach the online store | V1 §5; v2 §5 | `i/test_summary_to_hardship.py::test_unapproved_draft_changes_nothing`, `::test_approved_signal_reaches_the_online_store_with_its_prompt_version`, `::test_agent_who_deletes_the_cue_keeps_the_flag_down` |
| Coverage: text and voice features present or missing; poor recordings count as missing | V1 §5; v2 §5 | `i/test_feature_parity.py::test_text_features_without_a_transcript_are_missing_not_zero`, `u/test_post_call_summary.py::test_low_asr_confidence_marks_text_features_missing` |
| No voice characteristics (pitch, speed, accent); no `email_opened_flag` | V1 §5; v2 §5 | `u/test_fairness_and_registry.py::test_no_voice_characteristic_features`, `::test_email_open_flag_is_not_used` |
| NBA action = (treatment, channel, window in customer time zone) | V1 §6 UC1; v2 §6 | `u/test_nba_rules.py::test_action_has_treatment_channel_and_window_from_the_allowed_sets`, `u/test_policy_gate.py::test_same_instant_is_judged_in_each_customers_own_zone` |
| Promise break label: missed or part-paid after grace; outage promises excluded | V1 §6 UC1; v2 Labels | `u/test_metrics_and_labels.py::test_promise_break_label`, `::test_promise_inside_grace_period_is_not_yet_labelled`, `::test_promises_due_during_a_payment_outage_are_excluded`, `i/test_incident_effects.py::test_outage_promise_is_not_a_break_in_training_labels` |
| Policy gate first: cease, insolvency, death -> no contact; representative -> person; dispute -> pause | V1 §6 step 1 | `u/test_policy_gate.py::test_contact_blocks_stop_every_channel`, `::test_contact_blocks_hold_regardless_of_risk_or_treatment`, `::test_third_party_representative_routes_to_a_person`, `::test_open_dispute_pauses_the_case`, `u/test_nba_rules.py::test_nba_never_contacts_a_blocked_customer_however_risky` |
| Consented channels only | V1 §6 step 1 | `u/test_policy_gate.py::test_channel_without_consent_is_not_allowed`, `::test_missing_consent_is_treated_as_no_consent`, `::test_withdrawn_consent_on_one_channel_leaves_other_consented_channels` |
| Permitted hours (customer time zone), never Sundays or holidays | V1 §6 step 1; v2 | `u/test_policy_gate.py::test_calls_only_inside_permitted_hours_local_time`, `::test_customer_specific_window_is_respected`, `::test_window_start_boundary`, `::test_window_end_boundary`, `::test_no_calls_on_sunday`, `::test_sunday_flag_versus_v1_never_sundays`, `::test_sunday_is_judged_in_local_time`, `::test_no_calls_on_statutory_holidays`, `s/test_demo_storyline.py::test_step1_the_trap_no_work_hour_pressure_calls` |
| Weekly contact limit, explained as "No call: 3 of 3 contacts used this week" | V1 §6 steps 1 and 5 | `u/test_policy_gate.py::test_weekly_contact_limit`, `::test_contact_limit_block_is_explained_in_plain_words`, `u/test_nba_rules.py::test_nba_respects_the_weekly_cap_and_explains_it` |
| Hardship or vulnerability removes pressure and routes to a trained agent | V1 §6 step 1 | `u/test_policy_gate.py::test_hardship_or_vulnerability_removes_pressure_and_routes_to_trained_agent`, `::test_hardship_keeps_gentle_options_available`, `u/test_nba_rules.py::test_nba_never_proposes_pressure_to_a_customer_in_hardship`, `::test_vulnerability_flag_can_only_make_treatment_gentler` |
| DNCL and CASL are marketing-only, so ignored by the gate | v2 §6 step 1 | `u/test_policy_gate.py::test_marketing_only_flags_do_not_block_collections_contact` |
| Monotone model (more late payments never lower risk) | V1 §6 step 2 | `u/test_nba_rules.py::test_more_late_payments_never_lower_the_risk`, `::test_risk_is_a_probability` |
| Treatment ladder rules | V1 §6 step 3 | `u/test_nba_rules.py::test_low_risk_promise_gets_no_contact`, `::test_high_risk_promise_due_soon_gets_a_reminder`, `::test_broken_promise_with_late_pay_gets_a_plan_offer`, `::test_over_30_dpd_and_high_risk_gets_an_agent_call`, `::test_ladder_is_plain_rules_and_deterministic` |
| Capacity filled by expected value = p x amount - contact cost | V1 §6 step 3 | `u/test_nba_rules.py::test_daily_plan_fills_capacity_by_expected_value`, `::test_expected_value_formula` |
| Explanation: fixed format, no AI; rules, reasons, what changed | V1 §6 step 5; v2 §6 | `u/test_nba_rules.py::test_every_decision_has_a_three_part_explanation`, `::test_explanation_is_written_without_ai`, `::test_explanation_is_reproducible`, `::test_payroll_delay_appears_as_a_plain_reason`, `::test_what_changed_mentions_the_broken_promise` |
| Phase 2 uplift only if 70% overlap and 1,000 or more cases per action | V1 §6 Phase 2 | `u/test_nba_rules.py::test_uplift_runs_only_when_checks_pass` |
| Post-call summary: 80 words, fixed form, items link to call turns, unsupported blank, mismatch highlighted, agent approves | V1 §6 UC2; v2 §6 UC2 | `u/test_post_call_summary.py` (all), `s/test_persona_journeys.py::test_agent_reviews_and_approves_the_call_summary` |
| Eligibility by plain rules, each rule shown; AI never decides | V1 §6 UC3; v2 §6 UC3; V1 §8 | `u/test_eligibility.py` (all), `i/test_policy_answers.py::test_policy_answer_never_decides_eligibility` |
| Review tiers: individual vs batch; 2% sample; anything overridable | V1 §6 "Where a person reviews"; v2 | `u/test_review_batches.py` (all), `s/test_human_in_the_loop.py::test_batch_cannot_be_approved_before_the_sample_is_checked`, `::test_any_batch_item_can_be_stopped` |
| Deliberately no AI: policy rules, ladder, eligibility, simulator, explanations, refusals | V1 §8 | `u/test_policy_gate.py::test_gate_is_deterministic`, `u/test_nba_rules.py::test_ladder_is_plain_rules_and_deterministic`, `::test_explanation_is_written_without_ai`, `u/test_eligibility.py::test_eligibility_is_decided_by_rules`, `u/test_plan_simulator.py::test_simulator_is_deterministic_plain_arithmetic` |
| Access by role (5 roles); masking; groups under 10 hidden | V1 §10 Access | `s/test_rbac.py` (all), `u/test_small_groups.py` (all) |
| 12 protected attributes plus age and age band never feed a model or rule | V1 §10 | `u/test_fairness_and_registry.py::test_no_protected_attribute_is_a_feature`, `u/test_sql_guard.py::test_protected_attribute_columns_are_never_allowed`, `i/test_identity_to_nba.py::test_protected_attributes_do_not_reach_the_golden_record_or_features`, `s/test_rbac.py::test_no_role_sees_protected_attributes_on_the_customer_screen` |
| Hardship latch: anyone raises to possible; specialist confirms with a program; only a person lowers, with a reason | V1 §10; v2 §9; NI H2 | `u/test_hardship_latch.py` (all), `i/test_summary_to_hardship.py::test_later_model_signal_cannot_lower_the_flag_raised_by_the_summary`, `s/test_persona_journeys.py::test_specialist_confirms_hardship_by_linking_a_program`, `::test_specialist_lowering_requires_reason` |
| Append-only audit of query, score, decision, edit, override, simulator run | V1 §10 | `i/test_audit_trail.py` (all), `i/test_ask_pipeline.py::test_every_question_is_audited`, `s/test_rbac.py::test_nobody_can_delete_audit_records`, `s/test_demo_storyline.py::test_storyline_leaves_a_complete_audit_trail` |
| No raw PII to external LLM; PII masked | V1 Part 3 Uses; v2 §7 Hosting | `i/test_ask_pipeline.py::test_raw_pii_is_never_sent_to_the_llm`, `u/test_identity_rules.py::test_review_items_show_masked_data_only`, `u/test_post_call_summary.py::test_summary_never_contains_card_numbers` |

## 3. Data contract quality rules (`gold.c360_customer` v1.0, V1 Part 3)

| Rule | Severity | Tests |
|---|---|---|
| 1 golden_id unique, not null | Error | `u/test_data_contract.py::test_error_rules_fail_and_block_publish[dup-id,null-id]` |
| 2 match_confidence in [0,1] and at or above the cut-off unless deterministic or reviewed | Error | `::test_error_rules_fail_and_block_publish[conf>1,conf<0,conf<cutoff]`, `::test_rule2_low_confidence_allowed_when_reviewed_or_deterministic` |
| 3 max_dpd > 0 implies past due > 0 (warn on 0 DPD with more than CAD 1) | Error / Warn | `::test_error_rules_fail_and_block_publish[dpd-no-pastdue]`, `::test_rule3_zero_dpd_with_past_due_is_only_a_warning` |
| 4 Consent never null, never more permissive than linked CRM | Error | `::test_error_rules_fail_and_block_publish[null-consent]`, `::test_rule4_consent_more_permissive_than_a_linked_crm_record_fails` |
| 5 No two national_id_hash values per golden_id | Error | `::test_rule5_two_national_id_hashes_in_one_golden_id_fails` |
| 6 Every current CRM record has one golden_id; one primary party per account | Error | `::test_rule6_unmapped_crm_record_or_account_without_primary_fails` |
| 7 Hardship lowered to none has an event with reviewer and reason | Error | `::test_rule7_hardship_lowered_without_reviewed_event_fails`, `u/test_hardship_latch.py::test_person_with_reason_can_lower_and_an_event_is_written` |
| 8 No protected-attribute column | Error | `::test_error_rules_fail_and_block_publish[protected-col,age-col]`, `::test_contract_schema_has_no_protected_attributes` |
| 9 `_refreshed_at` within 26 h | Error | `::test_error_rules_fail_and_block_publish[stale]`, `::test_rule9_fresh_within_26_hours_passes` |
| 10 employer_key match rate at least 90% (TBC, V1 only) | Warn | `::test_rule10_low_employer_match_rate_warns_but_does_not_block` |
| Allowed and prohibited uses | n/a | `::test_contract_prohibits_the_listed_uses`, `s/test_human_in_the_loop.py::test_contacting_customers_not_yet_behind_needs_policy_office_signoff` |

## 4. Novel capabilities (V1 §7, NI)

| ID | Capability | Tests (marker `-m <id>`) |
|---|---|---|
| H1 | Hardship plan simulator | `u/test_plan_simulator.py` (all), `s/test_demo_storyline.py::test_step4_specialist_tries_a_cut_then_an_extension`, `s/test_human_in_the_loop.py::test_plan_beyond_program_limits_waits_for_the_program_approver`, `::test_simulator_alone_never_contacts_the_customer` |
| H2 | Review board + hardship latch | `u/test_hardship_latch.py`, `u/test_novel_capabilities.py::test_review_board_lists_due_and_overdue_vulnerability_reviews`, `::test_review_board_uses_the_flag_not_the_vulnerability_type`, `i/test_summary_to_hardship.py`, `s/test_persona_journeys.py::test_specialist_sees_review_board_and_missed_offers` |
| H3 | Missed offers + override audit | `u/test_novel_capabilities.py::test_missed_offers_are_hardship_cases_never_offered_a_program`, `::test_offers_made_against_the_rules_are_shown_by_agent_and_program`, `s/test_persona_journeys.py::test_specialist_sees_review_board_and_missed_offers` |
| H4 | Proxy-feature gate (AUC > 0.65) | `u/test_fairness_and_registry.py::test_feature_group_that_predicts_a_protected_attribute_is_dropped_or_coarsened`, `::test_independent_feature_group_is_kept`, `::test_gate_names_the_attribute_a_proxy_stands_in_for` |
| H5 | Outage-victim shield | `u/test_novel_capabilities.py::test_outage_victims_are_due_during_the_outage_and_paid_next_day`, `::test_outage_list_is_a_candidate_list_compared_with_the_bank_estimate`, `::test_outage_refunds_and_pressure_holds_are_proposals_for_a_person`, `i/test_incident_effects.py` (all), `u/test_metrics_and_labels.py::test_promises_due_during_a_payment_outage_are_excluded` |
| S1 | Employer shock radar | `u/test_novel_capabilities.py` (S1 block), `u/test_small_groups.py::test_employer_radar_hides_employers_under_ten`, `u/test_data_contract.py::test_rule10_low_employer_match_rate_warns_but_does_not_block`, `s/test_demo_storyline.py::test_step2_employer_radar_shows_colleagues_late_with_new_ei`, `::test_step5_team_lead_approves_one_batch_after_checking_the_sample`, `s/test_persona_journeys.py::test_team_lead_playbooks_wait_for_approval` |
| S2 | Collections weather map | `u/test_small_groups.py::test_weather_map_hides_small_areas`, `::test_weather_map_shows_its_sql`, `s/test_persona_journeys.py::test_analyst_map_hides_small_areas_and_shows_sql` |
| S3 | Data-health telemetry | `u/test_novel_capabilities.py::test_renamed_column_is_detected_as_drift`, `::test_ai_drafted_fix_waits_for_an_engineer`, `::test_null_rate_jump_is_reported`, `s/test_persona_journeys.py::test_steward_approves_an_ai_drafted_drift_fix` |
| S4 | Honest strategy scorecard | `u/test_metrics_and_labels.py::test_scorecard_calls_a_difference_causal_only_with_random_assignment`, `::test_scorecard_splits_by_entry_dpd_and_product`, `u/test_ask_refusals.py::test_strategy_question_is_labelled_observed_not_causal`, `s/test_persona_journeys.py::test_analyst_scorecard_is_honest_about_causality` |
| S5 | Query pre-flight | `i/test_ask_pipeline.py::test_pre_flight_reports_portfolio_coverage`, `::test_incident_in_the_period_is_flagged`, `::test_no_incident_flag_outside_the_incident_window`, `i/test_incident_effects.py::test_answers_over_the_outage_period_carry_the_incident_caveat` |
| S6 | Capacity stress test | `u/test_novel_capabilities.py::test_dialer_outage_moves_calls_and_leaves_the_real_plan_alone`, `s/test_persona_journeys.py::test_team_lead_runs_a_dialer_outage_stress_test` |
| S7 | Early hardship signals | `u/test_novel_capabilities.py::test_stress_signals_only_raise_hardship_to_possible`, `i/test_feature_parity.py::test_stress_signals_exist_for_every_customer` |
| A1 | Payday-anchored windows (day level) | `u/test_nba_rules.py::test_windows_are_only_the_capacity_time_bands`, `::test_payday_timing_is_by_day_not_hour` |
| A2 | Promise vs payday + what-if | `u/test_nba_rules.py::test_promise_check_counts_days_before_payday`, `::test_promise_what_if_is_labelled_a_model_estimate`, `::test_promise_what_if_saves_nothing`, `s/test_demo_storyline.py::test_step3_promise_before_payday_is_flagged_and_moved` |
| A3 | Negotiation friction index | `u/test_fairness_and_registry.py::test_no_voice_characteristic_features` (only the guard; A3 itself is "Designed") |

## 5. Demo storyline (NI §8) and personas

| Step or persona | Tests |
|---|---|
| 1 The trap | `s/test_demo_storyline.py::test_step1_the_trap_no_work_hour_pressure_calls` |
| 2 One view (+ S1 radar) | `::test_step2_one_view_links_his_records_and_shows_the_late_pay`, `::test_step2_employer_radar_shows_colleagues_late_with_new_ei` |
| 3 The promise (A2) | `::test_step3_promise_before_payday_is_flagged_and_moved` |
| 4 The plan (H1, latch) | `::test_step4_specialist_tries_a_cut_then_an_extension` |
| 5 The oversight (batch) | `::test_step5_team_lead_approves_one_batch_after_checking_the_sample` |
| Agent / specialist / team lead / analyst / steward journeys | `s/test_persona_journeys.py` (grouped by persona) |

## 6. Requirements NOT tested, and why (27)

| # | Requirement | Source | Why not testable black-box |
|---|---|---|---|
| 1 | +2 points of cure rate, about CAD 0.7M a year; 2,800 cases a month | V1 §2 | A business outcome; needs production or a hold-out experiment. |
| 2 | The challenger actually beats v2.1 (AUC 0.74) out of time | V1 §2, §6 | Depends on the real dataset; only the selection rule is tested. |
| 3 | 99.5% precision of automatic identity links | V1 §3 | Needs ground-truth person IDs, which don't exist (TBC); hand labels too. |
| 4 | Hardship recall on 200 hand-labelled examples | V1 §10; v2 §9 | Needs a labelled set; we check only that the signal is raised on a clear cue. |
| 5 | LLM feature accuracy against hand labels meets a bar | V1 §5 | No bar is stated; we test only that accuracy is recorded. |
| 6 | Benchmark questions answered within tolerance and rubric | V1 §4; v2 §4 | The benchmark set is not provided ("[__] benchmark questions"). |
| 7 | RAG faithfulness on 30 hand-graded answers | V1 §4; v2 §4 | Needs human grading. |
| 8 | Nightly build finished by 06:30 ET; re-score within 5 min; answers in seconds | V1 §9 | Timing SLAs depend on the environment and data volume; the constant `RESCORE_SLA_SECONDS` exists for a future performance suite. |
| 9 | Scale (1M customers, 2.5M contacts on a laptop) | V1 §9 | Performance and capacity testing, not specification behaviour. |
| 10 | Drift, PSI and weekly calibration monitoring | V1 §10; v2 §9 | Needs time series of model runs. |
| 11 | Isotonic calibration and SHAP correctness | v2 §6; V1 §8 | These are internals; only the explanation output is tested. |
| 12 | Phase 2 uplift estimates (EconML DR-learner) | V1 §6 | Only the gate is specified for behaviour; the estimator is not. |
| 13 | Compliance with OSFI E-23, FCAC, provincial limits, PIPEDA | V1 §10 | Legal and regulatory review; only the concrete rules derived from them are tested. |
| 14 | Production swaps (Snowflake, Feast, Redis, MLflow, bank-hosted LLM) | V1 §11 | Deployment choices; the hosting check is limited to "no raw PII in LLM prompts". |
| 15 | LLM source-to-target mapping suggestions approved by an engineer | V1 §3; Brief L1 AI helpers | No observable interface is defined in the docs beyond drift fixes. |
| 16 | Payday timing used only "if that beats the bank's current timing scores on past data" | V1 §6 step 3 | A data-dependent evaluation outcome. |
| 17 | Employer match rate at least 90% on the transactions sample | V1 Part 3 rule 10 | Data-dependent; only the warn rule logic is tested. |
| 18 | Restricted view uses protected attributes only for fairness audits | V1 §10 | No restricted-view interface is specified; we test the negative (no servicing role sees them). |
| 19 | Weekly retraining and fairness report | V1 §9 | A schedule and operations requirement. |
| 20 | Retention: 7 years on notes and recordings (exact period TBC) | V1 Part 3 | TBC, and needs long-running storage. |
| 21 | DuckDB single writer: approvals to a side file merged nightly | V1 §9 | An implementation detail, not behaviour. |
| 22 | AI over 1.5M notes processes open cases first | V1 §9 | A cost and prioritisation policy, not observable through the defined operations. |
| 23 | A3 friction index must pass the H4 proxy test before use | NI A3 | A3 is "Designed", not built; only the voice-feature exclusion is checked. |
| 24 | Agent assist live prompts ("hardship mentioned: check program eligibility") on replay | v2 §6 UC3 | v2-only, demo replay feature; no defined output contract. |
| 25 | Summary review takes under 30 seconds | v2 §6 UC2 | A usability target. |
| 26 | Phase 2 explanation shows the chosen action's effect against the runner-up | v2 §6 | Phase 2 only, conditional on the gate. |
| 27 | Hardship and consent changes event-driven in production | V1 Part 3 Refresh | A production architecture item; the build uses the nightly batch. |

import { BarChart3, Database, Headset, HeartHandshake, UsersRound } from "lucide-react";

import type { Role } from "@/api/types";

export const DEMO_PERSONAS: { role: Role; title: string; icon: typeof Headset; story: string; sees: string }[] = [
  { role: "agent", title: "Collections agent", icon: Headset, story: "Start the day with a queue, open one customer, and see why the system suggests a gentle next step.", sees: "Today's queue, Next best action and the policy gate, Call summary" },
  { role: "hardship_specialist", title: "Hardship specialist", icon: HeartHandshake, story: "Review a customer in hardship, check what they qualify for, and decide with a reason on record.", sees: "Review board, Plan simulator, Confirm or lower the flag" },
  { role: "team_lead", title: "Team lead", icon: UsersRound, story: "Approve the morning batch, test what happens if the dialer fails, and watch the guardrails.", sees: "Batch queue and the 2% sample, Stress test: dialer down, Approve the batch" },
  { role: "analyst", title: "Strategy analyst", icon: BarChart3, story: "Ask questions of the data, see a refused question explained, and read honest model numbers.", sees: "A certified metric question, A refused question, Fairness" },
  { role: "steward", title: "Data steward", icon: Database, story: "Check customer matches, data quality, contract tests and the audit log that backs every decision.", sees: "Identity review queue, Data quality report, Audit log" },
];

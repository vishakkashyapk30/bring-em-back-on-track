/** Plain-language names for actions, so every screen says the same thing the same way. */
export const CHANNEL: Record<string, string> = { call: "call", sms: "text message", email: "email", push: "app message", letter: "letter" };

type A = { treatment: string; channel?: string | null; window?: string | null };

/** "Call to talk about the payment", "Send a payment link by text message" ... */
export function actionLabel(a: A): string {
  const ch = a.channel ? CHANNEL[a.channel] ?? a.channel : "";
  switch (a.treatment) {
    case "reminder": return a.channel === "call" ? "Call about the payment" : `Send a reminder by ${ch}`;
    case "payment_link": return `Send a payment link by ${ch}`;
    case "plan_offer": return a.channel === "call" ? "Call to offer a plan" : `Offer a plan by ${ch}`;
    case "specialist_referral": return "Hand over to a specialist";
    case "no_contact": return "No contact";
    default: return a.treatment.replace(/_/g, " ");
  }
}

const HOUR = (h: number) => (h === 12 ? "noon" : h < 12 ? `${h} am` : `${h - 12} pm`);

/** "5 pm to 9 pm", or nothing for an all-day window. */
export function windowLabel(w?: string | null): string {
  if (!w || w === "all_day") return "";
  const [a, b] = w.split("-").map(Number);
  return `${HOUR(a)} to ${HOUR(b)}`;
}

const PRODUCT: Record<string, string> = {
  card: "Credit card", personal_loan: "Personal loan", auto_loan: "Auto loan", mortgage: "Mortgage", loc: "Line of credit",
  unsecured_loc: "Line of credit", student_loc: "Student line of credit", overdraft: "Overdraft", chequing: "Chequing", savings: "Savings",
};
export const productLabel = (p?: string | null) => (p ? PRODUCT[p] ?? p.replace(/_/g, " ") : "");

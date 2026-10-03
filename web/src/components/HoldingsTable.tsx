import { DataTable } from "./DataTable";

type Holding = { product: string; account: string; balance: number | null; overdue: number | null; dpd: number | null; status: string };
const cad = (v: unknown) => (typeof v === "number" ? v.toLocaleString("en-CA", { style: "currency", currency: "CAD", maximumFractionDigits: 0 }) : "—");

export function HoldingsTable({ holdings }: { holdings: Holding[] }) {
  return (
    <DataTable
      columns={["Product", "Account", "Balance", "Overdue", "DPD", "Status"]}
      rows={holdings.map((h) => [h.product, h.account, h.balance, h.overdue, h.dpd, h.status])}
      render={(v, col) => (col === "Balance" || col === "Overdue" ? cad(v) : String(v ?? "—"))}
    />
  );
}

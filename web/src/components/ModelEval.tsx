import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { useGet } from "@/api/hooks";

import { Badge } from "./Badge";
import { Card } from "./Card";
import { QueryState } from "./States";

type Json = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
const css = (v: string) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

const ROWS: [string, string][] = [["bank_v2_1", "Bank model v2.1"], ["ours", "Ours (LightGBM)"], ["blend", "Blend of both"]];

/** Promise-break model evaluation: honest head-to-head with the bank's model on the same test promises, and a
 * reliability chart for the blend that is used for decisions. */
export function ModelEval() {
  const q = useGet("model-eval", "/governance/model");
  const d: Json = q.data ?? {};
  const h: Json = d.head_to_head ?? {};
  const cal: Json[] = (d.calibration_blend ?? []).map((b: Json) => ({ ...b, mid: Number(String(b.bin).split("-")[0]) + 0.05 }));
  const brand = css("--color-brand") || "#a71f3e";
  const grid = css("--color-grey-300") || "#d9d9de";
  const muted = css("--color-muted") || "#5f6170";
  return (
    <QueryState q={q}>
      <div className="grid gap-6 lg:grid-cols-[1.1fr_1fr]">
        <Card>
          <h3>Head-to-head on the same test promises</h3>
          <p className="text-[13.5px] text-muted">{h.ours?.n?.toLocaleString?.() ?? "n/a"} promises due Jul to Sep 2026 that the bank's v2.1 also scored. Trained on promises made before Apr 2026; the blend was fitted on Apr to Jun.</p>
          <table className="w-full text-[14px]">
            <thead><tr className="text-left text-[12.5px] uppercase tracking-wide text-muted">
              <th className="py-2 font-semibold">Model</th><th className="py-2 text-right font-semibold">AUC</th><th className="py-2 text-right font-semibold">Brier</th><th className="py-2 text-right font-semibold">Lift top 10%</th></tr></thead>
            <tbody>
              {ROWS.map(([k, label]) => {
                const r: Json = h[k] ?? {};
                const used = k === "blend";
                return (
                  <tr key={k} className={used ? "border-t border-grey-300/60 bg-brand-50/50 font-medium" : "border-t border-grey-300/60"}>
                    <td className="py-2.5 pl-1">{label} {used && <Badge kind="ok">used</Badge>}</td>
                    <td className="py-2.5 text-right tabular">{r.auc?.toFixed?.(3) ?? "n/a"}</td>
                    <td className="py-2.5 text-right tabular">{r.brier?.toFixed?.(3) ?? "n/a"}</td>
                    <td className="py-2.5 pr-1 text-right tabular">{r.lift_top10?.toFixed?.(2) ?? "n/a"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="mb-0 mt-3 text-[13px] text-muted">Higher AUC and lift are better; lower Brier is better. Our model alone does not beat the bank's on ranking; the blend beats both, so the blend is used.</p>
        </Card>
        <Card>
          <h3>Is the blend's risk honest?</h3>
          <p className="text-[13.5px] text-muted">Predicted break rate against what actually happened, in 10 bins. On the diagonal means the stated risk matches reality.</p>
          <div className="h-[240px]" role="img" aria-label="Reliability chart: predicted versus observed break rate for the blend">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={cal} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
                <CartesianGrid stroke={grid} strokeWidth={1} vertical={false} />
                <XAxis type="number" dataKey="predicted" domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} stroke={grid} tick={{ fill: muted, fontSize: 12 }} />
                <YAxis type="number" domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} stroke={grid} tick={{ fill: muted, fontSize: 12 }} />
                <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]} stroke={muted} strokeOpacity={0.45} strokeWidth={1} ifOverflow="hidden" />
                <Tooltip cursor={{ stroke: grid }} formatter={(v) => `${(Number(v) * 100).toFixed(1)}%`}
                  labelFormatter={(_, p) => (p?.[0] ? `Bin ${p[0].payload.bin} · ${p[0].payload.n.toLocaleString()} promises · predicted ${(p[0].payload.predicted * 100).toFixed(1)}%` : "")}
                  contentStyle={{ borderRadius: 10, border: `1px solid ${grid}`, fontSize: 13 }} />
                <Line type="monotone" dataKey="observed" name="Observed break rate" stroke={brand} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"
                  dot={{ r: 4, fill: brand, stroke: "#fff", strokeWidth: 2 }} activeDot={{ r: 6, fill: brand, stroke: "#fff", strokeWidth: 2 }} isAnimationActive animationDuration={500} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>
    </QueryState>
  );
}

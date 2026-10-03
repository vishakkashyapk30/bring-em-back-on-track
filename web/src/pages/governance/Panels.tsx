import { useGet } from "@/api/hooks";
import { Card } from "@/components/Card";
import { QueryState } from "@/components/States";

import { ListView } from "../hardship/Lists";

/** JSON panel placeholder per governance endpoint. TODO(WS-G/WS-H): real layouts + charts (load dataviz skill). */
function JsonPanel({ k, path }: { k: string; path: string }) {
  const q = useGet(k, path);
  return <QueryState q={q}><Card><pre className="m-0 overflow-x-auto font-mono text-sm">{JSON.stringify(q.data, null, 2)}</pre></Card></QueryState>;
}

export const Quality = () => <JsonPanel k="quality" path="/governance/quality" />;
export const Benchmark = () => <JsonPanel k="benchmark" path="/governance/benchmark" />;
export const Monitoring = () => <JsonPanel k="monitoring" path="/governance/monitoring" />;
export const Fairness = () => <JsonPanel k="fairness" path="/governance/fairness" />;
export const Contract = () => <JsonPanel k="contract" path="/governance/contract" />;
export const Audit = () => <ListView k="audit" path="/governance/audit" />;

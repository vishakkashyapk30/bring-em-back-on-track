import { useParams } from "react-router-dom";

import { SimulatorPanel } from "@/components/SimulatorPanel";

export default function Simulator() {
  const { caseId = "" } = useParams();
  return <SimulatorPanel caseId={caseId} />;
}

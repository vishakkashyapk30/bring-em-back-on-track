import { useParams } from "react-router-dom";

import { SimulatorPanel } from "@/components/SimulatorPanel";
import { SampleDataBanner } from "@/components/States";

export default function Simulator() {
  const { caseId = "" } = useParams();
  return <><SampleDataBanner /><SimulatorPanel caseId={caseId} /></>;
}

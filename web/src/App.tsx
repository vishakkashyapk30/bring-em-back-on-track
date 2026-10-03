import { Navigate, Route, Routes } from "react-router-dom";

import type { Role } from "@/api/types";
import { Layout } from "@/components/Layout";
import { RequireRole } from "@/lib/session";
import Ask from "@/pages/Ask";
import CallSummary from "@/pages/CallSummary";
import Customer from "@/pages/Customer";
import DevKit from "@/pages/DevKit";
import Features from "@/pages/Features";
import Governance from "@/pages/governance/Governance";
import { Audit, Benchmark, Contract, Fairness, Monitoring, Quality } from "@/pages/governance/Panels";
import Hardship from "@/pages/hardship/Hardship";
import { Board, Missed, Overrides } from "@/pages/hardship/Lists";
import Simulator from "@/pages/hardship/Simulator";
import Landing from "@/pages/Landing";
import Login from "@/pages/Login";
import NotFound from "@/pages/NotFound";
import Queue from "@/pages/Queue";
import Radar from "@/pages/Radar";
import StewardIdentity from "@/pages/StewardIdentity";
import Team from "@/pages/Team";

const R = (roles: Role[], el: JSX.Element) => <RequireRole roles={roles}>{el}</RequireRole>;

/** App routes: one screen set per persona. */
export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route element={<Layout />}>
        <Route path="/queue" element={R(["agent", "team_lead"], <Queue />)} />
        <Route path="/customers/:goldenId" element={R(["agent", "hardship_specialist", "team_lead", "steward"], <Customer />)} />
        <Route path="/calls/:contactId" element={R(["agent"], <CallSummary />)} />
        <Route path="/ask" element={R(["analyst", "team_lead", "agent"], <Ask />)} />
        <Route path="/hardship" element={R(["hardship_specialist"], <Hardship />)}>
          <Route index element={<Navigate to="board" replace />} />
          <Route path="board" element={<Board />} />
          <Route path="missed" element={<Missed />} />
          <Route path="overrides" element={<Overrides />} />
          <Route path="simulator/:caseId" element={<Simulator />} />
        </Route>
        <Route path="/radar" element={R(["team_lead", "analyst"], <Radar />)} />
        <Route path="/team" element={R(["team_lead"], <Team />)} />
        <Route path="/features" element={R(["analyst", "steward"], <Features />)} />
        <Route path="/governance" element={R(["steward", "analyst", "team_lead"], <Governance />)}>
          <Route index element={<Navigate to="quality" replace />} />
          <Route path="quality" element={<Quality />} />
          <Route path="benchmark" element={<Benchmark />} />
          <Route path="monitoring" element={<Monitoring />} />
          <Route path="fairness" element={<Fairness />} />
          <Route path="audit" element={<Audit />} />
          <Route path="contract" element={<Contract />} />
        </Route>
        <Route path="/steward/identity" element={R(["steward"], <StewardIdentity />)} />
        <Route path="/dev/kit" element={<DevKit />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

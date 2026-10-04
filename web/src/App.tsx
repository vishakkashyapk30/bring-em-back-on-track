import { lazy, useEffect } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";

import type { Role } from "@/api/types";
import { Layout } from "@/components/Layout";
import { NavigationEffects, preloadPages } from "@/lib/navigation";
import { RequireRole } from "@/lib/session";
const Ask = lazy(() => import("@/pages/Ask"));
const CallSummary = lazy(() => import("@/pages/CallSummary"));
const Customer = lazy(() => import("@/pages/Customer"));
const Demo = lazy(() => import("@/pages/Demo"));
const DemoJourney = lazy(() => import("@/pages/DemoJourney"));
const DevKit = lazy(() => import("@/pages/DevKit"));
const Features = lazy(() => import("@/pages/Features"));
const Governance = lazy(() => import("@/pages/governance/Governance"));
const Audit = lazy(() => import("@/pages/governance/Panels").then((m) => ({ default: m.Audit })));
const Benchmark = lazy(() => import("@/pages/governance/Panels").then((m) => ({ default: m.Benchmark })));
const Contract = lazy(() => import("@/pages/governance/Panels").then((m) => ({ default: m.Contract })));
const Fairness = lazy(() => import("@/pages/governance/Panels").then((m) => ({ default: m.Fairness })));
const Monitoring = lazy(() => import("@/pages/governance/Panels").then((m) => ({ default: m.Monitoring })));
const Quality = lazy(() => import("@/pages/governance/Panels").then((m) => ({ default: m.Quality })));
const Hardship = lazy(() => import("@/pages/hardship/Hardship"));
const Board = lazy(() => import("@/pages/hardship/Lists").then((m) => ({ default: m.Board })));
const Missed = lazy(() => import("@/pages/hardship/Lists").then((m) => ({ default: m.Missed })));
const Overrides = lazy(() => import("@/pages/hardship/Lists").then((m) => ({ default: m.Overrides })));
const Simulator = lazy(() => import("@/pages/hardship/Simulator"));
const Landing = lazy(() => import("@/pages/Landing"));
const Login = lazy(() => import("@/pages/Login"));
const NotFound = lazy(() => import("@/pages/NotFound"));
const Queue = lazy(() => import("@/pages/Queue"));
const MapPage = lazy(() => import("@/pages/MapPage"));
const StewardIdentity = lazy(() => import("@/pages/StewardIdentity"));
const StewardDrift = lazy(() => import("@/pages/StewardDrift"));
const Team = lazy(() => import("@/pages/Team"));

const R = (roles: Role[], el: JSX.Element) => <RequireRole roles={roles}>{el}</RequireRole>;

/** App routes: one screen set per persona. */
export default function App() {
  useEffect(() => preloadPages([
    () => import("@/pages/Ask"),
    () => import("@/pages/CallSummary"),
    () => import("@/pages/Customer"),
    () => import("@/pages/Demo"),
    () => import("@/pages/DemoJourney"),
    () => import("@/pages/DevKit"),
    () => import("@/pages/Features"),
    () => import("@/pages/governance/Governance"),
    () => import("@/pages/governance/Panels"),
    () => import("@/pages/hardship/Hardship"),
    () => import("@/pages/hardship/Lists"),
    () => import("@/pages/hardship/Simulator"),
    () => import("@/pages/Landing"),
    () => import("@/components/Globe"),
    () => import("@/pages/Login"),
    () => import("@/pages/NotFound"),
    () => import("@/pages/Queue"),
    () => import("@/pages/MapPage"),
    () => import("@/pages/StewardIdentity"),
    () => import("@/pages/StewardDrift"),
    () => import("@/pages/Team"),
  ]), []);
  return (
    <>
    <NavigationEffects />
    <Toaster position="bottom-right" richColors closeButton toastOptions={{ duration: 3500 }} />
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/demo" element={<Demo />} />
        <Route path="/demo/:persona" element={<DemoJourney />} />
        <Route path="/queue" element={R(["agent", "team_lead", "hardship_specialist"], <Queue />)} />
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
        <Route path="/map" element={R(["team_lead", "analyst"], <MapPage />)} />
        <Route path="/radar" element={<Navigate to="/map" replace />} />
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
        <Route path="/steward/drift" element={R(["steward"], <StewardDrift />)} />
        <Route path="/dev/kit" element={<DevKit />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
    </>
  );
}

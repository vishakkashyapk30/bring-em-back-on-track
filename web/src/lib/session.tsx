import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";

import { useMe } from "@/api/hooks";
import type { Role } from "@/api/types";
import { ErrorState, Skeleton } from "@/components/States";

/** Route guard: redirects to /login when signed out, shows a friendly forbidden state for wrong roles. */
export function RequireRole({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const me = useMe();
  if (me.isLoading) return <Skeleton lines={6} />;
  if (me.isError || !me.data) return <Navigate to="/login" replace />;
  if (!roles.includes(me.data.role))
    return <ErrorState title="Not available for your role" detail={`Signed in as ${me.data.role}.`} />;
  return <>{children}</>;
}

export const NAV: { to: string; label: string; roles: Role[] }[] = [
  { to: "/queue", label: "Queue", roles: ["agent", "team_lead"] },
  { to: "/ask", label: "Ask", roles: ["analyst", "team_lead", "agent"] },
  { to: "/hardship", label: "Hardship", roles: ["hardship_specialist"] },
  { to: "/map", label: "Map", roles: ["team_lead", "analyst"] },
  { to: "/team", label: "Team", roles: ["team_lead"] },
  { to: "/features", label: "Features", roles: ["analyst", "steward"] },
  { to: "/governance", label: "Governance", roles: ["steward", "analyst", "team_lead"] },
  { to: "/steward/identity", label: "Identity review", roles: ["steward"] },
];

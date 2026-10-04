import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";

import Track from "./Track";
import Tracker from "./Tracker";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

function wrap(path: string, routes: ReactNode) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[path]}><Routes>{routes}</Routes></MemoryRouter>
    </QueryClientProvider>,
  );
}

const KINDS = {
  role: "team_lead",
  kinds: [{ kind: "agent", label: "Agent", hint: "An agent on your team." }, { kind: "employer", label: "Employer", hint: "An employer from the radar." }],
  suggested: { id: "AG-6274", label: "M. Cochran", sublabel: "AG-6274 · agent", badges: [] }, suggested_kind: "agent",
};

test("the picker lists only what the API returns for the role, and switches kind", async () => {
  const calls: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    calls.push(url);
    if (url.endsWith("/track/kinds")) return json(KINDS);
    if (url.includes("kind=employer")) return json({ kind: "employer", items: [{ id: "EMP-0123ABCD", label: "EMP-0123ABCD", sublabel: "Industry 33 · 40 customers", badges: [] }], note: "Employers with at least 10 customers." });
    if (url.includes("kind=agent")) return json({ kind: "agent", items: [{ id: "AG-2021", label: "P. Chami", sublabel: "AG-2021 · agent", badges: [] }], note: "Agents on team CGY-MID-2." });
    return json({}, 404);
  }));
  wrap("/track", <Route path="/track" element={<Track />} />);
  expect(await screen.findByRole("heading", { name: "Track" })).toBeTruthy();
  const row = await screen.findByRole("link", { name: /P\. Chami/ });
  expect(row.getAttribute("href")).toBe("/track/agent/AG-2021");
  expect(screen.getByRole("link", { name: /Track this/ }).getAttribute("href")).toBe("/track/agent/AG-6274");
  expect(screen.getByRole("button", { name: "Agent" }).getAttribute("aria-pressed")).toBe("true");

  fireEvent.click(screen.getByRole("button", { name: "Employer" }));
  const emp = await screen.findByRole("link", { name: /EMP-0123ABCD/ });
  expect(emp.getAttribute("href")).toBe("/track/employer/EMP-0123ABCD");
  expect(calls.some((u) => u.includes("/track/subjects?kind=employer"))).toBe(true);
  expect(screen.getByText("Employers with at least 10 customers.")).toBeTruthy();
});

test("an empty scope says so instead of showing other people's subjects", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    if (url.endsWith("/track/kinds")) return json({ role: "agent", kinds: [{ kind: "customer", label: "Customer", hint: "One customer's history." }], suggested: null });
    return json({ kind: "customer", items: [], note: null });
  }));
  wrap("/track", <Route path="/track" element={<Track />} />);
  expect(await screen.findByText("No matches")).toBeTruthy();
  expect(screen.queryByRole("group", { name: "What to track" })).toBeNull(); // one kind: no switch
});

test("a refused subject shows the reason from the API", async () => {
  const reason = "This customer is not assigned to you.";
  vi.stubGlobal("fetch", vi.fn(async (url: string) => (url.includes("/track/customer/") ? json({ detail: { reason } }, 403) : json({ user_id: "AG-1", role: "agent" }))));
  wrap("/track/customer/G-OTHER01", <Route path="/track/:kind/:id" element={<Tracker />} />);
  expect(await screen.findByText("You can't track this")).toBeTruthy();
  expect(screen.getByText(reason)).toBeTruthy();
});

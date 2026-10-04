import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";

import Customer from "./Customer";

const REASON = "Stewards see data quality, identity lineage and features, not an individual customer's calls, notes or call summaries.";
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

test("a refused customer shows the reason and keeps the identity lineage", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    if (url.endsWith("/identity")) return json({ golden_id: "G-1", match_confidence: 1, match_method: "deterministic", sources: [{ system: "crm", ref: "CRM-1" }] });
    return json({ detail: { reason: REASON } }, 403);
  }));
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/customers/G-1"]}><Routes><Route path="/customers/:goldenId" element={<Customer />} /></Routes></MemoryRouter>
    </QueryClientProvider>,
  );
  expect(await screen.findByText("You can't open this customer")).toBeTruthy();
  expect(screen.getByText(REASON)).toBeTruthy();
  expect(await screen.findByText("CRM-1")).toBeTruthy();
});

import { render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, it, vi } from "vitest";

const calls = vi.hoisted(() => ({ api: vi.fn(async () => { throw new Error("401"); }), me: { data: undefined as unknown } }));
vi.mock("@/api/client", () => ({ api: calls.api }));
vi.mock("@/api/hooks", () => ({ useMe: () => calls.me }));

import { CanadaRiskMap } from "./CanadaRiskMap";
import { DecisionFlow } from "./DecisionFlow";
import { IdentityConstellation } from "./IdentityConstellation";

const mount = () => render(
  <QueryClientProvider client={new QueryClient()}>
    <CanadaRiskMap /><DecisionFlow /><IdentityConstellation goldenId="sample" />
  </QueryClientProvider>,
);

beforeEach(() => { calls.api.mockClear(); calls.me.data = undefined; });

it("makes no /public request while signed out", async () => {
  mount();
  await new Promise((r) => setTimeout(r, 30));
  expect(calls.api).not.toHaveBeenCalled();
});

it("asks for the numbers once someone is signed in", async () => {
  calls.me.data = { user_id: "u", role: "analyst" };
  mount();
  await new Promise((r) => setTimeout(r, 30));
  const urls = calls.api.mock.calls.map((c) => (c as unknown as string[])[0]);
  expect(urls).toEqual(expect.arrayContaining(["/public/map", "/public/flow", "/public/sample-customer"]));
});

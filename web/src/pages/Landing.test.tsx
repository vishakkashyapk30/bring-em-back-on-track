import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ me: { isLoading: false, data: undefined as unknown } }));
vi.mock("@/api/hooks", () => ({ useMe: () => state.me }));
vi.mock("@/api/visuals", () => ({ usePublicSummary: () => ({ data: { golden_customers: 1001072 } }) }));
vi.mock("@/components/visuals/CanadaRiskMap", () => ({ CanadaRiskMap: () => <div data-testid="map" /> }));
vi.mock("@/components/visuals/DecisionFlow", () => ({ DecisionFlow: () => <div data-testid="flow" /> }));
vi.mock("@/components/visuals/IdentityConstellation", () => ({ IdentityConstellation: () => <div data-testid="constellation" /> }));
vi.mock("@/components/Globe", () => ({ Globe: () => <div data-testid="globe" /> }));

import Landing, { firstScreen, statItems } from "./Landing";

const wrap = () => render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><Landing /></MemoryRouter></QueryClientProvider>);

describe("landing page gating", () => {
  beforeEach(() => { state.me = { isLoading: false, data: undefined }; });

  it("signed out: the hero shows and no data component is mounted, no numbers appear", async () => {
    wrap();
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Help customers get back on track.");
    expect(screen.getAllByRole("link", { name: /Sign in as a persona/ })[0].getAttribute("href")).toBe("/login");
    expect(screen.getByRole("link", { name: "Watch the demo" }).getAttribute("href")).toBe("/demo");
    expect(screen.queryByTestId("map")).toBeNull();
    expect(screen.queryByTestId("flow")).toBeNull();
    expect(screen.queryByTestId("constellation")).toBeNull();
    expect(document.body.textContent).not.toMatch(/1,001,072|86,044/);
  });

  it("while the session loads nothing from the data is mounted", () => {
    state.me = { isLoading: true, data: undefined };
    wrap();
    expect(screen.queryByTestId("map")).toBeNull();
  });

  it("signed in: a personal home with the three visuals and the live numbers", async () => {
    state.me = { isLoading: false, data: { user_id: "u1", role: "agent", display_name: "M. Cochran" } };
    wrap();
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Hello, M. Cochran");
    expect(screen.getByRole("link", { name: /Open my workspace/ }).getAttribute("href")).toBe("/queue");
    expect(screen.getByRole("link", { name: "Watch my demo" }).getAttribute("href")).toBe("/demo/agent");
    expect(await screen.findByTestId("map")).toBeTruthy();
    expect(screen.getByTestId("flow")).toBeTruthy();
    expect(await screen.findByTestId("constellation")).toBeTruthy();
    expect(screen.getByText("1,001,072")).toBeTruthy();
  });
});

describe("home helpers", () => {
  it("first screen per role", () => {
    expect(firstScreen("analyst")).toBe("/ask");
    expect(firstScreen("hardship_specialist")).toBe("/queue");
    expect(firstScreen("steward")).toBe("/features");
  });
  it("stat strip handles missing numbers", () => {
    expect(statItems({}).map((s) => s.value)).toEqual(["n/a", "n/a", "n/a", "n/a of n/a"]);
  });
});

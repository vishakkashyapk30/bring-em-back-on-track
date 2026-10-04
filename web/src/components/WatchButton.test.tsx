import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import { WatchButton } from "./WatchButton";

type Call = { url: string; method: string; body?: string };
let calls: Call[] = [];
let pins: { kind: string; subject_id: string }[] = [];
let refuse = false;

beforeEach(() => {
  calls = []; pins = []; refuse = false;
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    calls.push({ url, method, body: init?.body as string | undefined });
    const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status, headers: { "content-type": "application/json" } });
    if (url === "/api/watchlist/pins") return json(pins);
    if (refuse) return json({ detail: { reason: "This customer is not assigned to you." } }, 403);
    if (method === "POST") { pins = [...pins, JSON.parse(String(init?.body)) && { kind: "customer", subject_id: "G-1" }]; return json({ pinned: true, audit_id: 7 }); }
    if (method === "DELETE") { pins = []; return json({ pinned: false, audit_id: 8 }); }
    return json({ items: [], changed: 0 });
  }));
});
const wrap = () => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><WatchButton kind="customer" id="G-1" label="R. Mitchell" /></QueryClientProvider>);

test("toggles the pin with an accessible pressed state", async () => {
  wrap();
  const b = await screen.findByRole("button", { name: "Watch R. Mitchell" });
  await waitFor(() => expect(b.hasAttribute("disabled")).toBe(false));
  expect(b.getAttribute("aria-pressed")).toBe("false");
  fireEvent.click(b);
  // optimistic: pressed at once, before the server answers
  expect((await screen.findByRole("button", { name: "Stop watching R. Mitchell" })).getAttribute("aria-pressed")).toBe("true");
  const post = calls.find((c) => c.method === "POST");
  expect(post?.url).toBe("/api/watchlist");
  expect(JSON.parse(post!.body!)).toEqual({ kind: "customer", subject_id: "G-1", label: "R. Mitchell" });
  fireEvent.click(screen.getByRole("button", { name: "Stop watching R. Mitchell" }));
  expect(await screen.findByRole("button", { name: "Watch R. Mitchell" })).toBeTruthy();
  await waitFor(() => expect(calls.some((c) => c.method === "DELETE" && c.url === "/api/watchlist/customer/G-1")).toBe(true));
});

test("rolls back when the server refuses the pin", async () => {
  refuse = true;
  wrap();
  const b = await screen.findByRole("button", { name: "Watch R. Mitchell" });
  await waitFor(() => expect(b.hasAttribute("disabled")).toBe(false));
  fireEvent.click(b);
  await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
  await waitFor(() => expect(screen.getByRole("button", { name: "Watch R. Mitchell" }).getAttribute("aria-pressed")).toBe("false"));
});

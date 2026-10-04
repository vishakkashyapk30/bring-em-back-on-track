import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Sources } from "./Sources";
import { cleanSources, insightParts } from "@/pages/Ask";

describe("Sources", () => {
  it("shows policy section with the quote as plain text", () => {
    render(<Sources citations={[{ doc_id: "PRC-COLL-010", section: "§3.3", quote: "a grace period of **2 business days**" }]} />);
    expect(screen.getByText("PRC-COLL-010, §3.3")).toBeTruthy();
    expect(screen.getByText("a grace period of 2 business days")).toBeTruthy();
  });
  it("shows SQL from a ref with its tables, and skips entries with nothing to show", () => {
    render(<Sources citations={[{ kind: "sql", ref: "SELECT 1 FROM t", tables: ["t"] }, { kind: "document" }]} />);
    expect(screen.getByText("SELECT 1 FROM t")).toBeTruthy();
    expect(screen.getByText("Tables: t")).toBeTruthy();
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
  });
  it("does not repeat a table label as its own quote", () => {
    render(<Sources citations={[{ kind: "table", label: "Collections cases", quote: "Collections cases" }]} />);
    expect(screen.getAllByText("Collections cases")).toHaveLength(1);
  });
  it("labels a call turn", () => {
    render(<Sources citations={[{ kind: "interaction", doc_id: "3510350", section: "turn 13" }]} />);
    expect(screen.getByText("Call 3510350, turn 13")).toBeTruthy();
  });
});

describe("Ask helpers", () => {
  it("splits strung-together notes and cleans source names", () => {
    expect(insightParts('Agent note on 1 Sep: "a" Agent note on 2 Sep: "b"')).toHaveLength(2);
    expect(cleanSources(["sql: Query", "table: X", "table: X"])).toEqual(["Query", "X"]);
  });
});

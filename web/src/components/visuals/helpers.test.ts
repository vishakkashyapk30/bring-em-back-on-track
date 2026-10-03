import { describe, expect, it } from "vitest";

import type { PublicMap } from "@/api/visuals";
import { classOf, fmtMonth, fmtValue, layoutSankey, nextInDirection, pathThrough, quantileBreaks, radiusFor, relax, tableRows, versus } from "./helpers";

const map: PublicMap = {
  as_of: "2026-09-28", months: ["2026-08", "2026-09"], min_group: 10, customers: 100,
  provinces: [{ code: "ON", name: "Ontario", lat: 0, lon: 0, customers: 50 }, { code: "NU", name: "Nunavut", lat: 0, lon: 0, customers: 3 }, { code: "BC", name: "British Columbia", lat: 0, lon: 0, customers: 30 }],
  metrics: {
    broken_ptp_rate: {
      label: "Broken promises", unit: "%", monthly: true, note: "", national: [30, 40], fsas: [], fsas_hidden: 2,
      series: {
        ON: { value: [31, 45], n: [20, 25], top: ["Forgot", "Not enough money"] },
        NU: { value: [null, null], n: [null, null], top: [null, null] },
        BC: { value: [20, 38], n: [12, 14], top: [null, "Forgot"] },
      },
    },
  },
};

describe("formatting", () => {
  it("formats values and months", () => {
    expect(fmtValue(12.34, "%")).toBe("12.3%");
    expect(fmtValue(null, "%")).toBe("n/a");
    expect(fmtMonth("2026-09", true)).toMatch(/September 2026/);
  });
  it("says how far from national", () => {
    expect(versus(45, 40, "%")).toBe("5.0 points above national");
    expect(versus(38, 40, "%")).toBe("2.0 points below national");
    expect(versus(null, 40, "%")).toBe("n/a");
  });
});

describe("scales", () => {
  it("makes five classes", () => {
    const b = quantileBreaks(Array.from({ length: 100 }, (_, i) => i));
    expect(b).toHaveLength(4);
    expect(classOf(0, b)).toBe(0);
    expect(classOf(99, b)).toBe(4);
  });
  it("sizes bubbles by square root within bounds", () => {
    expect(radiusFor(0, 100)).toBe(7);
    expect(radiusFor(100, 100)).toBe(36);
    expect(radiusFor(25, 100)).toBeCloseTo(21.5);
  });
});

describe("table fallback", () => {
  it("lists every province, highest first, hidden last, with no number for hidden groups", () => {
    const rows = tableRows(map, "broken_ptp_rate", 1);
    expect(rows.map((r) => r.code)).toEqual(["ON", "BC", "NU"]);
    expect(rows[2]).toMatchObject({ value: null, n: null, vs: "n/a" });
    expect(rows[0].vs).toBe("5.0 points above national");
  });
});

describe("keyboard order and bubble spacing", () => {
  const pts = [{ code: "A", x: 0, y: 0 }, { code: "B", x: 50, y: 5 }, { code: "C", x: 100, y: 0 }, { code: "D", x: 10, y: 80 }];
  it("moves to the nearest bubble in the pressed direction", () => {
    expect(nextInDirection("A", pts, "right")).toBe("B");
    expect(nextInDirection("B", pts, "right")).toBe("C");
    expect(nextInDirection("A", pts, "down")).toBe("D");
    expect(nextInDirection("A", pts, "left")).toBeNull();
  });
  it("pushes overlapping bubbles apart", () => {
    const out = relax([{ x: 0, y: 0, r: 10 }, { x: 5, y: 0, r: 10 }]);
    expect(Math.hypot(out[1].x - out[0].x, out[1].y - out[0].y)).toBeGreaterThanOrEqual(21.9);
  });
});

describe("sankey", () => {
  const nodes = [
    { id: "a", col: 0, label: "A", value: 100 },
    { id: "b", col: 1, label: "B", value: 99 }, { id: "c", col: 1, label: "C", value: 1 },
  ];
  const links = [{ source: "a", target: "b", value: 99 }, { source: "a", target: "c", value: 1 }];
  it("keeps nodes inside the box with a minimum height and no overlap", () => {
    const { nodes: n } = layoutSankey(nodes, links, { width: 400, height: 300, minH: 20 });
    for (const x of n) { expect(x.y).toBeGreaterThanOrEqual(-0.01); expect(x.y + x.h).toBeLessThanOrEqual(300.01); expect(x.h).toBeGreaterThanOrEqual(20); }
    const col1 = n.filter((x) => x.col === 1).sort((p, q) => p.y - q.y);
    expect(col1[0].y + col1[0].h).toBeLessThanOrEqual(col1[1].y);
  });
  it("draws link widths in proportion to the counts", () => {
    const { links: l } = layoutSankey(nodes, links, { width: 400, height: 300 });
    const big = l.find((x) => x.target === "b")!, small = l.find((x) => x.target === "c")!;
    expect(big.width / small.width).toBeGreaterThan(50);
  });
  it("finds the whole path through a node", () => {
    const chain = [{ source: "a", target: "b", value: 1 }, { source: "b", target: "c", value: 1 }, { source: "a", target: "d", value: 1 }];
    expect([...pathThrough("b", chain)].sort()).toEqual(["a>b", "b>c"]);
  });
});

import { constellationTakeaway, flowTakeaway, legendStops, mapTakeaway, oneIn } from "./helpers";

describe("takeaways", () => {
  const map = {
    as_of: "x", months: ["2026-08", "2026-09"], min_group: 10, customers: 1,
    provinces: [{ code: "ON", name: "Ontario", lat: 0, lon: 0, customers: 5 }, { code: "QC", name: "Quebec", lat: 0, lon: 0, customers: 5 }],
    metrics: { broken_ptp_rate: { label: "x", unit: "%", monthly: true, note: "", national: [25, 30], fsas: [], fsas_hidden: 0,
      series: { ON: { value: [30, 34], n: [1, 1], top: [null, null] }, QC: { value: [20, 21], n: [1, 1], top: [null, null] } } } },
  } as never;
  test("oneIn", () => { expect(oneIn(34)).toBe("1 in 3"); expect(oneIn(0)).toBeNull(); expect(oneIn(80)).toBeNull(); });
  test("map names the leading province", () => {
    expect(mapTakeaway(map, "broken_ptp_rate", 1)).toBe("Ontario has the highest share of broken promises: 1 in 3 (34.0%), against 30.0% nationally.");
  });
  test("map has nothing to say without a metric", () => { expect(mapTakeaway(map, "hardship_rate", 1)).toBeNull(); });
  test("flow", () => {
    const t = flowTakeaway({ total: 100, nodes: [{ id: "blocked", value: 14, label: "" }, { id: "r_individual", value: 30, label: "" }] });
    expect(t).toContain("14 of 100 open cases (14%)");
    expect(t).toContain("30 are reviewed");
  });
  test("constellation", () => {
    const t = constellationTakeaway([{ system: "crm", confidence: 1 }, { system: "cards", confidence: 0.9 }], { label: "Reminder" });
    expect(t).toBe("2 records from 2 systems match into one customer; 1 match is below 100% and checked by a person, and the proposed next step is reminder.");
  });
  test("legend stops", () => { expect(legendStops([12.4, 18.6], "%")).toEqual(["12%", "19%"]); });
});

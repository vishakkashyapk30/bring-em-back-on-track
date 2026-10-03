import { clampStage, contextFromPath, demoPath, personaFromParam, progressPct, revealDelays, stageFromKey, stageLabel, visibleSteps, cell } from "./helpers";

test("steps reveal in order, 250 ms apart, or instantly under reduced motion", () => {
  expect(revealDelays(4)).toEqual([0, 250, 500, 750]);
  expect(revealDelays(3, 250, true)).toEqual([0, 0, 0]);
  expect(visibleSteps(0, 5)).toBe(1);
  expect(visibleSteps(260, 5)).toBe(2);
  expect(visibleSteps(10_000, 5)).toBe(5);
  expect(visibleSteps(0, 5, 250, true)).toBe(5);
});

test("stage navigation stays inside the tour", () => {
  expect(clampStage(-3, 8)).toBe(0);
  expect(clampStage(99, 8)).toBe(7);
  expect(stageFromKey("ArrowRight", 2, 8)).toBe(3);
  expect(stageFromKey("ArrowRight", 7, 8)).toBeNull();
  expect(stageFromKey("ArrowLeft", 0, 8)).toBeNull();
  expect(stageFromKey("x", 1, 8)).toBeNull();
  expect(stageLabel(2, 7)).toBe("Stage 3 of 7");
  expect(progressPct(3, 8)).toBe(50);
});

test("route to persona and context mapping", () => {
  expect(personaFromParam("team_lead")).toBe("team_lead");
  expect(personaFromParam("admin")).toBeNull();
  expect(demoPath("agent", 3)).toBe("/demo/agent?stage=3");
  expect(contextFromPath("/customers/G-ABC")).toEqual({ golden_id: "G-ABC" });
  expect(contextFromPath("/hardship/simulator/CS-1")).toEqual({ case_id: "CS-1" });
  expect(contextFromPath("/queue", "?case=CS-2")).toEqual({ case_id: "CS-2" });
  expect(contextFromPath("/queue")).toEqual({});
  expect(cell(null)).toBe("n/a");
  expect(cell(0.94771)).toBe("0.948");
});

import { geoArea, geoContains } from "d3-geo";
import type { Feature, Geometry } from "geojson";

import india from "./india-official.geo.json";

const f = india as unknown as Feature<Geometry>;

test("the India outline is a normal-sized shape, not the whole globe minus India (winding is right)", () => {
  expect(geoArea(f)).toBeGreaterThan(0.07);
  expect(geoArea(f)).toBeLessThan(0.1);
});

test("India is drawn as on the Survey of India map: all of Jammu and Kashmir and Ladakh, including Gilgit-Baltistan and Aksai Chin", () => {
  const inside: Record<string, [number, number]> = {
    Srinagar: [74.8, 34.08], Leh: [77.58, 34.15], Gilgit: [74.31, 35.92], Muzaffarabad: [73.47, 34.37],
    "Aksai Chin": [79.5, 35.2], Siachen: [77.1, 35.4], Delhi: [77.2, 28.6], "Port Blair": [92.74, 11.62],
  };
  for (const [name, p] of Object.entries(inside)) expect([name, geoContains(f, p)]).toEqual([name, true]);
});

test("neighbouring capitals are not inside India", () => {
  for (const p of [[73.05, 33.69], [85.3, 27.7], [90.4, 23.8], [79.86, 6.93]] as [number, number][]) expect(geoContains(f, p)).toBe(false);
});

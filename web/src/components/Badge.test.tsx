import { render, screen } from "@testing-library/react";

import { Badge } from "./Badge";

test("hardship badge has an icon and text, not colour alone", () => {
  render(<Badge kind="hardship">Hardship: possible</Badge>);
  const el = screen.getByText("Hardship: possible");
  expect(el.querySelector("svg")).not.toBeNull();
});

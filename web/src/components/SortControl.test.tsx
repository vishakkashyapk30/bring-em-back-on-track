import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { SortControl } from "./SortControl";

const OPTS: [string, string][] = [["newest", "Newest"], ["exposure", "Exposure"]];

test("select is labelled and reports the chosen field", () => {
  const onChange = vi.fn();
  render(<SortControl value="newest" dir="desc" options={OPTS} onChange={onChange} onDir={() => {}} />);
  fireEvent.change(screen.getByLabelText("Sort by"), { target: { value: "exposure" } });
  expect(onChange).toHaveBeenCalledWith("exposure");
});

test("direction toggle is a keyboard-operable button that announces its state", () => {
  const onDir = vi.fn();
  render(<SortControl value="newest" dir="desc" options={OPTS} onChange={() => {}} onDir={onDir} />);
  const btn = screen.getByRole("button", { name: /Descending\. Switch to ascending/ });
  btn.focus();
  expect(btn).toHaveFocus();
  fireEvent.click(btn); // a native button turns Enter and Space into click
  expect(onDir).toHaveBeenCalledWith("asc");
});

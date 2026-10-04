import clsx from "clsx";
import type { HTMLAttributes } from "react";

type Variant = "grey" | "brand" | "dark" | "plain";
const fills: Record<Variant, string> = {
  grey: "bg-grey-100 text-ink border-transparent",
  brand: "bg-brand text-white border-transparent",
  dark: "bg-cream text-ink border-transparent",
  plain: "bg-white text-ink border-grey-300/70",
};

/** Base card: a plain border. `hard` = a darker border for the one card a page leads with. */
export function Card({ variant = "plain", hard = false, landing = false, className, ...rest }:
  HTMLAttributes<HTMLDivElement> & { variant?: Variant; hard?: boolean; landing?: boolean }) {
  return (
    <div
      className={clsx(
        "border",
        fills[variant],
        landing ? "rounded-[var(--radius-xl)]" : "rounded-[var(--radius-lg)]",
        !/(^|\s)p-\d/.test(className ?? "") && (landing ? "p-8" : "p-5"),  // an explicit p-* overrides the default
        hard && variant === "plain" ? "border-ink/25" : "",
        className,
      )}
      {...rest}
    />
  );
}

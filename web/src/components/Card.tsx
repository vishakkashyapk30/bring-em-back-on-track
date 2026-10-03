import clsx from "clsx";
import type { HTMLAttributes } from "react";

type Variant = "grey" | "brand" | "dark" | "plain";
const fills: Record<Variant, string> = {
  grey: "bg-grey-100 text-ink",
  brand: "bg-brand text-white",
  dark: "bg-navy text-white",
  plain: "bg-white text-ink",
};

/** Base card. `hard` = Positivus 1px ink border + 0 5px 0 offset shadow (hero cards / CTAs only). */
export function Card({ variant = "plain", hard = false, landing = false, className, ...rest }:
  HTMLAttributes<HTMLDivElement> & { variant?: Variant; hard?: boolean; landing?: boolean }) {
  return (
    <div
      className={clsx(
        fills[variant],
        landing ? "rounded-[var(--radius-xl)] p-10" : "rounded-[var(--radius-lg)] p-6",
        hard ? "border border-ink shadow-[var(--shadow-hard)]" : "border border-grey-300",
        className,
      )}
      {...rest}
    />
  );
}

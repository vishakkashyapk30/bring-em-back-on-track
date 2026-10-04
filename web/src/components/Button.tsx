import clsx from "clsx";
import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost" | "dark";
type Size = "sm" | "md" | "lg";
const variants: Record<Variant, string> = {
  primary: "bg-brand text-white hover:bg-brand-700 border-transparent",
  dark: "bg-brand text-white hover:bg-brand-700 border-transparent",
  secondary: "bg-white text-ink border-grey-300 hover:border-ink/40 hover:bg-grey-100",
  ghost: "bg-transparent text-ink border-transparent hover:bg-grey-100",
};
const sizes: Record<Size, string> = { sm: "h-8 px-3 text-sm", md: "h-10 px-4 text-[15px]", lg: "h-12 px-6 text-base" };

/** One button style for the whole app: consistent height, radius, hover and press feedback. */
export function Button({ variant = "secondary", size = "md", className, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size }) {
  return (
    <button
      type="button"
      className={clsx(
        "inline-flex select-none items-center justify-center gap-2 whitespace-nowrap rounded-[var(--radius-md)] border font-medium",
        "transition-[background-color,border-color,transform,box-shadow] duration-150 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50",
        variants[variant], sizes[size], className,
      )}
      {...rest}
    />
  );
}

import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-[11px] font-medium leading-5 [&_svg]:size-3",
  {
    variants: {
      tone: {
        neutral: "border-line bg-surface-2 text-fg-muted",
        brand: "border-brand/25 bg-brand-soft text-brand",
        accent: "border-accent/25 bg-accent-soft text-accent",
        good: "border-good/25 bg-good-soft text-good",
        warning: "border-warning/30 bg-warning-soft text-[color-mix(in_oklab,var(--color-warning)_70%,var(--color-fg))]",
        critical: "border-critical/25 bg-critical-soft text-critical",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export type BadgeTone = NonNullable<VariantProps<typeof badgeVariants>["tone"]>;

export function Badge({ className, tone, ...props }: ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}

/** Tirik holat nuqtasi — status rangi hech qachon yolg'iz emas, doim matn bilan. */
export function StatusDot({ tone = "good", pulse = false }: { tone?: "good" | "warning" | "critical" | "neutral"; pulse?: boolean }) {
  const color = {
    good: "bg-good text-good",
    warning: "bg-warning text-warning",
    critical: "bg-critical text-critical",
    neutral: "bg-fg-subtle text-fg-subtle",
  }[tone];
  return <span aria-hidden className={cn("inline-block size-2 shrink-0 rounded-full", color, pulse && "animate-pulse-ring")} />;
}

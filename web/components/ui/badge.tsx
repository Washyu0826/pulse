import { type VariantProps, cva } from "class-variance-authority";
import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

const badge = cva(
  "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 font-mono text-[10px] font-medium uppercase tracking-wider leading-none",
  {
    variants: {
      variant: {
        neutral: "border-border bg-ink/[0.03] text-ink/70",
        accent: "border-accent-primary/30 bg-accent-primary/10 text-accent-primary", // 模型
        cyan: "border-accent-cyan/30 bg-accent-cyan/10 text-accent-cyan", // 版本
        warn: "border-sentiment-neutral/30 bg-sentiment-neutral/10 text-sentiment-neutral", // 突增 / severity
      },
    },
    defaultVariants: { variant: "neutral" },
  },
);

export function Badge({
  className,
  variant,
  ...props
}: HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badge>) {
  return <span className={cn(badge({ variant }), className)} {...props} />;
}

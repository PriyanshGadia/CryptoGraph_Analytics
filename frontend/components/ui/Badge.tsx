import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center shape-tag border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-accent text-white hover:bg-accent/80",
        secondary:
          "border-transparent bg-border text-text hover:bg-border/80",
        destructive:
          "border-transparent bg-danger text-white hover:bg-danger/80",
        success:
          "border-transparent bg-success text-white hover:bg-success/80",
        warning:
          "border-transparent bg-yellow-500 text-black hover:bg-yellow-500/80",
        outline: "text-text",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };

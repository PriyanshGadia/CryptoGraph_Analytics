import { cn } from "@/lib/utils";

export function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("animate-pulse shape-ledger bg-[rgba(var(--text),0.06)]", className)}
      {...props}
    />
  );
}

import { cn } from "@/app/lib/utils";

type Variant = "default" | "success" | "warning" | "danger" | "info" | "muted";

const variants: Record<Variant, string> = {
  default: "bg-slate-700 text-slate-200",
  success: "bg-emerald-900/60 text-emerald-300 border border-emerald-700/40",
  warning: "bg-amber-900/60 text-amber-300 border border-amber-700/40",
  danger: "bg-red-900/60 text-red-300 border border-red-700/40",
  info: "bg-blue-900/60 text-blue-300 border border-blue-700/40",
  muted: "bg-slate-800 text-slate-400",
};

interface BadgeProps {
  variant?: Variant;
  children: React.ReactNode;
  className?: string;
}

export function Badge({ variant = "default", children, className }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium",
        variants[variant],
        className
      )}
    >
      {children}
    </span>
  );
}

import { cn } from "@/app/lib/utils";

interface CardProps {
  children: React.ReactNode;
  className?: string;
  glow?: "none" | "blue" | "emerald" | "amber" | "red";
}

const glowMap = {
  none: "",
  blue: "shadow-[0_0_20px_-5px_rgba(59,130,246,0.3)]",
  emerald: "shadow-[0_0_20px_-5px_rgba(16,185,129,0.3)]",
  amber: "shadow-[0_0_20px_-5px_rgba(245,158,11,0.3)]",
  red: "shadow-[0_0_20px_-5px_rgba(239,68,68,0.3)]",
};

export function Card({ children, className, glow = "none" }: CardProps) {
  return (
    <div
      className={cn(
        "rounded-xl border border-slate-700/50 bg-slate-900/60 backdrop-blur-sm",
        glowMap[glow],
        className
      )}
    >
      {children}
    </div>
  );
}

export function CardHeader({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("px-5 py-4 border-b border-slate-700/50", className)}>
      {children}
    </div>
  );
}

export function CardBody({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("px-5 py-4", className)}>{children}</div>;
}

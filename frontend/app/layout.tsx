import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CheckoutGuard — AI Anomaly Detection",
  description: "Multi-agent checkout anomaly detection and remediation platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased min-h-screen bg-[#0a0f1e]">{children}</body>
    </html>
  );
}

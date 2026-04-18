import type { Metadata } from "next";
import { Fraunces, Geist, JetBrains_Mono } from "next/font/google";
import "katex/dist/katex.min.css";
import "@/styles/globals.css";

const fraunces = Fraunces({
  subsets: ["latin"],
  variable: "--fnt-fraunces",
  display: "swap",
  axes: ["SOFT", "opsz"],
});

const geist = Geist({
  subsets: ["latin"],
  variable: "--fnt-geist",
  display: "swap",
});

const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--fnt-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "TinyFlow · A Venaissance Workbench",
  description: "A scholarly workbench for multi-agent orchestration.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="zh"
      suppressHydrationWarning
      className={`${fraunces.variable} ${geist.variable} ${mono.variable}`}
    >
      <body className="relative min-h-screen bg-paper text-ink antialiased" suppressHydrationWarning>
        <div className="paper-grain" aria-hidden />
        {children}
      </body>
    </html>
  );
}

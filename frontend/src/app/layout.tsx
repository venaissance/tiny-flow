import type { Metadata } from "next";
import "katex/dist/katex.min.css";
import "@/styles/globals.css";

export const metadata: Metadata = {
  title: "MdwFlow Lite",
  description: "Lightweight multi-agent orchestration engine",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh">
      <body className="min-h-screen bg-white dark:bg-gray-950">
        {children}
      </body>
    </html>
  );
}

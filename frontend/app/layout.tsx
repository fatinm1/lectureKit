/**
 * Root layout for the Cloudforce Frontier Next.js app.
 *
 * Purpose: Applies Inter (DESIGN.md-approved substitute for Linear Text/Display),
 * sets document metadata, and wraps all routes.
 *
 * Routing: `/` is marketing; `/app` is the workspace. Study routes consume API responses in later parts.
 */

import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "LectureKit — Turn lectures into study kits",
  description:
    "Paste any YouTube lecture for summaries, flashcards, outlines, and semantic search — built for students and educators.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  /**
   * Inline base presentation guards against the rare dev scenario where the compiled Tailwind
   * stylesheet 404s (stale `.next` manifests). Layout utilities still require `globals.css`, but
   * users should never see Times-on-white if the CSS chunk fails.
   */
  return (
    <html lang="en">
      <body
        className={`${inter.variable} font-sans antialiased`}
        style={{
          margin: 0,
          minHeight: "100vh",
          backgroundColor: "#010102",
          color: "#f7f8f8",
          fontFamily:
            "var(--font-inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif)",
        }}
      >
        {children}
      </body>
    </html>
  );
}

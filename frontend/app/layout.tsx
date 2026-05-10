/**
 * Root layout for the Cloudforce Frontier Next.js app.
 *
 * Purpose: Applies Inter (DESIGN.md-approved substitute for Linear Text/Display),
 * sets document metadata, and wraps all routes.
 *
 * Routing: `/` is marketing; `/app` is the workspace. Study routes consume API responses in later parts.
 */

import type { Metadata } from "next";
import { Inter, Playfair_Display } from "next/font/google";
import "./globals.css";
import "./components/marketing/lumina.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
  weight: ["400", "500", "600", "700"],
});

const playfair = Playfair_Display({
  subsets: ["latin"],
  variable: "--font-lecturekit-serif",
  display: "swap",
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
        className={`${inter.variable} ${playfair.variable} min-h-screen bg-zinc-950 font-sans text-zinc-200 antialiased`}
        style={{
          margin: 0,
          fontFamily:
            "var(--font-inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif)",
        }}
      >
        {children}
      </body>
    </html>
  );
}

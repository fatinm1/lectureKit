/**
 * Marketing homepage (`/`) — Lumina-style dark landing for LectureKit.
 */

import { Playfair_Display } from "next/font/google";

import { MarketingFeatures } from "./components/marketing/MarketingFeatures";
import { MarketingFooter } from "./components/marketing/MarketingFooter";
import { MarketingHero } from "./components/marketing/MarketingHero";
import { MarketingHowItWorks } from "./components/marketing/MarketingHowItWorks";
import { MarketingNav } from "./components/marketing/MarketingNav";
import { MarketingStats } from "./components/marketing/MarketingStats";
import { MarketingTechStack } from "./components/marketing/MarketingTechStack";
import { MarketingWhySection } from "./components/marketing/MarketingWhySection";

import "./components/marketing/lumina.css";

const playfair = Playfair_Display({
  subsets: ["latin"],
  variable: "--font-lecturekit-serif",
  display: "swap",
});

export default function MarketingHomePage(): JSX.Element {
  return (
    <div
      className={`${playfair.variable} lk-marketing-scrollbar flex min-h-screen flex-col overflow-x-hidden bg-zinc-950 font-sans text-zinc-200 antialiased selection:bg-[#5e6ad2]/30`}
    >
      <MarketingNav />
      <main className="flex-grow">
        <MarketingHero />
        <MarketingFeatures />
        <MarketingHowItWorks />
        <MarketingWhySection />
        <MarketingTechStack />
        <MarketingStats />
      </main>
      <MarketingFooter />
    </div>
  );
}

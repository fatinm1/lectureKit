/**
 * Marketing homepage (`/`) — Lumina-style dark landing for LectureKit.
 */

import { MarketingFeatures } from "./components/marketing/MarketingFeatures";
import { MarketingFooter } from "./components/marketing/MarketingFooter";
import { MarketingHero } from "./components/marketing/MarketingHero";
import { MarketingHowItWorks } from "./components/marketing/MarketingHowItWorks";
import { MarketingNav } from "./components/marketing/MarketingNav";
import { MarketingStats } from "./components/marketing/MarketingStats";
import { MarketingTechStack } from "./components/marketing/MarketingTechStack";
import { MarketingWhySection } from "./components/marketing/MarketingWhySection";

export default function MarketingHomePage(): JSX.Element {
  return (
    <div className="lk-marketing-scrollbar flex min-h-screen flex-col overflow-x-hidden bg-zinc-950 font-sans text-zinc-200 antialiased selection:bg-zinc-600/30">
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

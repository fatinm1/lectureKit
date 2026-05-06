/**
 * Marketing homepage (`/`) — LectureKit positioning for students and educators.
 *
 * Purpose: Standalone storytelling surface following DESIGN.md + marketing divider/muted palette.
 * Routing: All conversion CTAs route to `/app` where the URL ingest workflow lives.
 */

import { MarketingFeatures } from "./components/marketing/MarketingFeatures";
import { MarketingFinalCta } from "./components/marketing/MarketingFinalCta";
import { MarketingFooter } from "./components/marketing/MarketingFooter";
import { MarketingHero } from "./components/marketing/MarketingHero";
import { MarketingHowItWorks } from "./components/marketing/MarketingHowItWorks";
import { MarketingNav } from "./components/marketing/MarketingNav";
import { MarketingProductPreview } from "./components/marketing/MarketingProductPreview";

export default function MarketingHomePage(): JSX.Element {
  /**
   * Stack ordered marketing sections top-to-bottom with global fade-in on first paint.
   *
   * Steps:
   * 1. Pin navigation above scrolling narrative sections.
   * 2. Maintain minimum 120px vertical rhythm via `py-section-xl` tokens inside sections.
   */
  return (
    <div className="min-h-screen bg-canvas text-ink animate-fade-in [--tw-duration:300ms]">
      <MarketingNav />
      <MarketingHero />
      <MarketingProductPreview />
      <MarketingHowItWorks />
      <MarketingFeatures />
      <MarketingFinalCta />
      <MarketingFooter />
    </div>
  );
}

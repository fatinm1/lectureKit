/**
 * Closing marketing CTA — subtle surface lift inviting users into `/app`.
 *
 * Purpose: Final conversion band using DESIGN.md `surface-1` lift without card framing.
 */

import Link from "next/link";

export function MarketingFinalCta(): JSX.Element {
  /**
   * Render full-width closing invitation with a single lavender primary button.
   *
   * Steps:
   * 1. Shift background one step up the Linear surface ladder for gentle separation from canvas.
   * 2. Keep typography centered with generous vertical padding (`py-section-xl`).
   */
  return (
    <section
      className="border-t border-marketing-divider bg-surface-1 px-md py-section-xl"
      aria-labelledby="final-cta-title"
    >
      <div className="mx-auto max-w-content text-center">
        <h2
          id="final-cta-title"
          className="text-[clamp(1.85rem,3vw,2.35rem)] font-semibold tracking-tight text-ink"
        >
          Start studying smarter
        </h2>
        <p className="mx-auto mt-md max-w-xl text-body text-marketing-muted">
          No account required. Paste a URL and go.
        </p>
        <div className="mt-xl flex justify-center">
          <Link
            href="/app"
            className="inline-flex min-h-[44px] items-center justify-center rounded-linear bg-primary px-[14px] py-[8px] text-button font-medium text-onprimary transition duration-interaction ease-out hover:bg-primary-hover active:bg-primary-focus"
          >
            Launch the App
          </Link>
        </div>
      </div>
    </section>
  );
}

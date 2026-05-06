/**
 * Marketing site navigation — fixed, blurred chrome over the Linear canvas.
 *
 * Purpose: Frames the LectureKit story at `/` with a single route into `/app`.
 * Styling: DESIGN.md canvas + primary accent; divider `#1a1a1a` per marketing spec.
 */

import Link from "next/link";

export function MarketingNav(): JSX.Element {
  /**
   * Render the sticky marketing navigation shell.
   *
   * Steps:
   * 1. Pin to viewport top with translucent canvas + backdrop blur for scroll-through content.
   * 2. Keep typography compact semibold for the wordmark (Inter).
   * 3. Provide a secondary-style “ghost” CTA that routes to the functional app surface.
   */
  return (
    <header className="fixed inset-x-0 top-0 z-50 border-b border-marketing-divider bg-canvas/75 backdrop-blur-md transition-colors duration-interaction ease-out">
      <div className="mx-auto flex h-14 max-w-content items-center justify-between px-md">
        <Link
          href="/"
          className="text-[15px] font-semibold tracking-tight text-ink transition-opacity duration-interaction ease-out hover:opacity-90"
        >
          LectureKit
        </Link>
        <Link
          href="/app"
          className="rounded-linear border border-marketing-divider px-[14px] py-[8px] text-button font-medium text-marketing-muted transition duration-interaction ease-out hover:border-primary hover:text-ink"
        >
          Launch App
        </Link>
      </div>
    </header>
  );
}

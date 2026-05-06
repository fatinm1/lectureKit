/**
 * Marketing footer — single-line attribution split across brand + internship note.
 */

export function MarketingFooter(): JSX.Element {
  /**
   * Render minimal legal/branding row with a subtle top divider.
   *
   * Steps:
   * 1. Constrain width to the Linear content rail.
   * 2. Keep secondary copy in muted `#6b7280` for tertiary reading.
   */
  return (
    <footer className="border-t border-marketing-divider px-md py-lg">
      <div className="mx-auto flex max-w-content flex-col items-start justify-between gap-sm text-caption text-marketing-muted sm:flex-row sm:items-center">
        <span className="font-semibold text-ink">LectureKit</span>
        <span>Built for the Cloudforce Frontier Internship</span>
      </div>
    </footer>
  );
}

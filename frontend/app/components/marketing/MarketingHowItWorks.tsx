/**
 * Marketing “How it works” narrative — numbered vertical steps separated by hairlines.
 *
 * Purpose: Explain the LectureKit pipeline without icons, cards, or illustration noise.
 */

const STEPS: readonly { number: string; title: string; description: string }[] = [
  {
    number: "01",
    title: "Paste a YouTube URL",
    description: "Any public lecture works — LectureKit pulls the transcript and preserves timestamps.",
  },
  {
    number: "02",
    title: "Three AI agents process the content",
    description:
      "Transcript cleanup, structured analysis, and semantic indexing run in parallel so results land fast.",
  },
  {
    number: "03",
    title: "Study smarter",
    description:
      "Explore the outline, drill flashcards, and search any concept — jump straight to the exact clip.",
  },
];

export function MarketingHowItWorks(): JSX.Element {
  /**
   * Render instructional steps using typography + dividers only.
   *
   * Steps:
   * 1. Provide eyebrow taxonomy (`HOW IT WORKS`) in muted uppercase.
   * 2. Stack numbered rows with 1px separators using `border-marketing-divider`.
   */
  return (
    <section
      id="how-it-works"
      className="border-t border-marketing-divider px-md py-section-xl"
      aria-labelledby="how-it-works-title"
    >
      <div className="mx-auto max-w-content">
        <p className="text-caption font-medium uppercase tracking-[0.22em] text-marketing-muted">
          HOW IT WORKS
        </p>
        <h2 id="how-it-works-title" className="mt-md max-w-3xl text-[clamp(1.75rem,3vw,2.25rem)] font-semibold tracking-tight text-ink">
          From lecture to mastery in seconds
        </h2>

        <ol className="mt-xxl divide-y divide-marketing-divider border-y border-marketing-divider">
          {STEPS.map((step) => (
            <li
              key={step.number}
              className="grid gap-md py-lg md:grid-cols-[72px_1fr] md:items-start md:gap-xl"
            >
              <p className="font-mono text-[13px] tabular-nums text-primary">{step.number}</p>
              <div>
                <h3 className="text-section text-ink">{step.title}</h3>
                <p className="mt-sm max-w-3xl text-body text-marketing-muted">{step.description}</p>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

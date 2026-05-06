/**
 * Marketing features grid — 2×2 typographic grid without icons or raised surfaces.
 *
 * Purpose: Enumerate student-facing capabilities aligned with the shipped study workspace.
 */

const FEATURES: readonly { title: string; description: string }[] = [
  {
    title: "Structured Outline",
    description:
      "Timestamped chapters anchor every topic back to the lecture. Skim fast, then dive deep where you need to.",
  },
  {
    title: "Multi-depth Summaries",
    description:
      "Start with a tight recap, expand into a five-minute synthesis, or read the full narrative when exams demand it.",
  },
  {
    title: "Smart Flashcards",
    description:
      "AI-generated prompts with cited moments so you always know which clip justified the answer.",
  },
  {
    title: "Semantic Search",
    description:
      "Ask natural-language questions and retrieve the precise beat in the video — no scrubbing required.",
  },
];

export function MarketingFeatures(): JSX.Element {
  /**
   * Present four capabilities in a responsive grid with intra-cell dividers instead of cards.
   *
   * Steps:
   * 1. Label the section per marketing taxonomy (`FEATURES`).
   * 2. Render each feature as title → hairline → dual-sentence description.
   */
  return (
    <section
      id="features"
      className="border-t border-marketing-divider px-md py-section-xl"
      aria-labelledby="features-title"
    >
      <div className="mx-auto max-w-content">
        <p className="text-caption font-medium uppercase tracking-[0.22em] text-marketing-muted">
          FEATURES
        </p>
        <h2 id="features-title" className="mt-md max-w-3xl text-[clamp(1.75rem,3vw,2.25rem)] font-semibold tracking-tight text-ink">
          Everything a student needs
        </h2>

        <div className="mt-xxl grid gap-x-xl gap-y-section-xl md:grid-cols-2">
          {FEATURES.map((feature) => (
            <article key={feature.title} className="flex flex-col">
              <h3 className="text-subhead text-ink">{feature.title}</h3>
              <div className="mt-sm h-px w-full bg-marketing-divider" aria-hidden />
              <p className="mt-md text-body text-marketing-muted">{feature.description}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

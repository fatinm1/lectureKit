/**
 * Marketing features grid — typographic grid without icons or raised surfaces.
 *
 * Purpose: Enumerate Student, Faculty, and Provost capabilities aligned with shipped modes.
 */

const FEATURES: readonly { title: string; description: string }[] = [
  {
    title: "Study Smarter",
    description:
      "Timestamped outline, three-depth summaries, flashcards with source citations, semantic search, and bilingual support in 5 languages.",
  },
  {
    title: "Private Lecture Audit",
    description:
      "A private report scoring your lecture across pedagogical quality, accessibility, equity, and clarity — with a prioritized fix list and timestamped suggested rewrites.",
  },
  {
    title: "Curriculum Coverage Map",
    description:
      "Paste multiple lecture URLs and your learning objectives. See exactly which objectives were covered, which were missed, and what to fix — backed by evidence from the lectures themselves.",
  },
];

export function MarketingFeatures(): JSX.Element {
  /**
   * Present three role-based capabilities in a responsive grid with intra-cell dividers instead of cards.
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
          Student, faculty, and institutional workflows
        </h2>

        <div className="mt-xxl grid gap-x-xl gap-y-section-xl md:grid-cols-2 lg:grid-cols-3">
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

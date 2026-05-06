/**
 * Marketing product preview — coded “screenshot” of the study dashboard (Linear-style framing).
 *
 * Purpose: Shows credible UI structure between hero and “How it works” without raster assets.
 * Interaction: Hover scale on shell; right-hand Summary / Flashcards / Search tabs switch panel copy (client).
 */

"use client";

import { useState } from "react";

const OUTLINE_ITEMS: readonly { time: string; title: string }[] = [
  { time: "00:00", title: "Roadmap & prerequisites" },
  { time: "03:42", title: "Forward pass intuition" },
  { time: "09:18", title: "Loss landscapes & gradients" },
  { time: "16:05", title: "Backpropagation walkthrough" },
  { time: "24:31", title: "Training tips & pitfalls" },
];

type PreviewTab = "summary" | "flashcards" | "search";

const TABS: readonly { id: PreviewTab; label: string }[] = [
  { id: "summary", label: "Summary" },
  { id: "flashcards", label: "Flashcards" },
  { id: "search", label: "Search" },
];

export function MarketingProductPreview(): JSX.Element {
  const [activeTab, setActiveTab] = useState<PreviewTab>("summary");

  /**
   * Render the faux dashboard inside a capped-width preview rail.
   *
   * Steps:
   * 1. Announce the block with an eyebrow label (`PRODUCT PREVIEW`).
   * 2. Present a single bordered surface with inset shadow depth (still not “cards” — one preview shell).
   * 3. Lay out outline / player / tabbed columns; tabs update local state only (marketing demo).
   */
  return (
    <section className="border-t border-marketing-divider px-md pb-section-xl pt-lg" aria-label="Product preview">
      <div className="mx-auto max-w-preview">
        <p className="text-caption font-medium uppercase tracking-[0.22em] text-marketing-muted">
          PRODUCT PREVIEW
        </p>

        <div
          className="mt-md rounded-xl border border-marketing-divider bg-surface-1 shadow-[inset_0_1px_0_rgba(247,248,248,0.06),inset_0_0_0_1px_rgba(1,1,2,0.85),inset_0_-40px_80px_rgba(0,0,0,0.55)] transition-transform duration-preview ease-out hover:scale-[1.005]"
          aria-label="Mock LectureKit dashboard showing outline, video player, and study tabs"
        >
          <div className="border-b border-marketing-divider px-lg pb-md pt-lg">
            <p className="text-caption font-medium uppercase tracking-[0.14em] text-marketing-muted">
              Active lecture
            </p>
            <p className="mt-xs text-subhead text-ink">Introduction to Neural Networks</p>
            <p className="mt-xs text-secondary text-marketing-muted">
              CS 229 · Week 2 · Focused on intuition before equations.
            </p>
          </div>

          <div className="grid gap-0 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.4fr)_minmax(0,1.05fr)]">
            {/* Outline column */}
            <div className="border-marketing-divider lg:border-r border-b lg:border-b-0 px-md py-lg">
              <p className="text-caption font-medium uppercase tracking-[0.14em] text-ink-subtle">Outline</p>
              <ul className="mt-md space-y-md">
                {OUTLINE_ITEMS.map((item) => (
                  <li key={item.title}>
                    <button
                      type="button"
                      className="group flex w-full items-start gap-sm text-left transition-colors duration-interaction ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-surface-1"
                    >
                      <span className="inline-flex shrink-0 rounded-xs bg-primary/15 px-xs py-xxs font-mono text-[11px] tabular-nums text-primary transition-colors duration-interaction ease-out group-hover:bg-primary/25">
                        {item.time}
                      </span>
                      <span className="text-secondary text-ink transition-colors duration-interaction ease-out group-hover:text-ink-muted">
                        {item.title}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>

            {/* Player column */}
            <div className="border-marketing-divider lg:border-r border-b lg:border-b-0 px-md py-lg">
              <p className="text-caption font-medium uppercase tracking-[0.14em] text-ink-subtle">Player</p>
              <div className="relative mt-md aspect-video w-full overflow-hidden rounded-linear bg-surface-4 ring-1 ring-hairline">
                <div className="absolute inset-0 bg-gradient-to-b from-surface-3 to-canvas opacity-90" />
                <div className="relative flex h-full w-full items-center justify-center">
                  <div className="flex h-14 w-14 items-center justify-center rounded-full border border-hairline-strong bg-surface-2/80 text-ink shadow-[0_12px_48px_rgba(0,0,0,0.55)] backdrop-blur-sm">
                    <svg
                      viewBox="0 0 24 24"
                      className="ml-1 h-7 w-7 text-ink-muted"
                      fill="currentColor"
                      aria-hidden
                    >
                      <path d="M8 5v14l11-7z" />
                    </svg>
                  </div>
                </div>
              </div>
              <p className="mt-sm text-caption text-marketing-muted">
                Jump-to-moment search lands on exact transcript spans once processing completes.
              </p>
            </div>

            {/* Tabs + panel */}
            <div className="px-md py-lg">
              <div
                role="tablist"
                aria-label="Study tools"
                className="flex gap-lg border-b border-marketing-divider"
              >
                {TABS.map((tab) => {
                  const isActive = activeTab === tab.id;
                  return (
                    <button
                      key={tab.id}
                      type="button"
                      role="tab"
                      id={`preview-tab-${tab.id}`}
                      aria-selected={isActive}
                      aria-controls={`preview-panel-${tab.id}`}
                      tabIndex={0}
                      onClick={() => setActiveTab(tab.id)}
                      className={`relative pb-sm text-button font-medium transition-colors duration-interaction ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-surface-1 ${
                        isActive ? "text-ink" : "text-marketing-muted hover:text-ink-muted"
                      }`}
                    >
                      {tab.label}
                      {isActive ? (
                        <span
                          className="absolute inset-x-0 bottom-0 h-0.5 rounded-full bg-primary"
                          aria-hidden
                        />
                      ) : null}
                    </button>
                  );
                })}
              </div>

              <div className="mt-md">
                {activeTab === "summary" ? (
                  <div
                    role="tabpanel"
                    id="preview-panel-summary"
                    aria-labelledby="preview-tab-summary"
                    className="space-y-sm"
                  >
                    <p className="text-secondary text-marketing-muted">
                      This lecture builds the mental model for neurons as differentiable blocks — why composition
                      scales, and where nonlinearities actually matter.
                    </p>
                    <p className="text-secondary text-marketing-muted">
                      Next it connects prediction errors to parameter updates, setting up backprop as structured
                      bookkeeping rather than a memorized recipe.
                    </p>
                  </div>
                ) : null}

                {activeTab === "flashcards" ? (
                  <div
                    role="tabpanel"
                    id="preview-panel-flashcards"
                    aria-labelledby="preview-tab-flashcards"
                    className="space-y-md border-l-2 border-primary pl-md"
                  >
                    <div>
                      <p className="text-caption font-medium uppercase tracking-[0.12em] text-ink-subtle">
                        Card 1 of 10
                      </p>
                      <p className="mt-xs text-secondary text-ink">
                        Why stack affine transforms without activation functions fail to model nonlinear boundaries?
                      </p>
                      <p className="mt-sm text-secondary text-marketing-muted">
                        Answer: composition of linear maps stays linear — you need a nonlinearity to carve curved
                        decision surfaces (see clip ~06:10).
                      </p>
                    </div>
                  </div>
                ) : null}

                {activeTab === "search" ? (
                  <div
                    role="tabpanel"
                    id="preview-panel-search"
                    aria-labelledby="preview-tab-search"
                    className="space-y-sm"
                  >
                    <div className="rounded-linear border border-marketing-divider bg-canvas px-sm py-xs text-secondary text-marketing-muted">
                      Ask anything about this lecture…
                    </div>
                    <p className="text-caption font-mono tabular-nums text-primary">Top hit · 11:42</p>
                    <p className="text-secondary text-marketing-muted">
                      “Vanishing gradients often trace to saturated sigmoid regions — remedies include careful init,
                      alternative activations, and residual pathways.”
                    </p>
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

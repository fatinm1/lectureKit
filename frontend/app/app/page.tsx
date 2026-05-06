/**
 * Application route (`/app`) — LectureKit workspace for URL submission + study flows.
 *
 * Purpose: Separates product UI from marketing `/`. Imports the client-side URL panel only here.
 * Agents: Posts to FastAPI `/process` today; future parts hydrate outlines, summaries, and search.
 */

import Link from "next/link";
import { ProcessUrlPanel } from "../components/app/ProcessUrlPanel";

export default function AppHomePage(): JSX.Element {
  /**
   * Compose the minimal workspace chrome + interactive panel.
   *
   * Steps:
   * 1. Provide an inline header mirroring marketing typography without marketing blur chrome.
   * 2. Render the client-only form handler beneath for transcript orchestration testing.
   */
  return (
    <div className="min-h-screen bg-canvas text-ink">
      <header className="border-b border-marketing-divider bg-canvas/90 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-content items-center justify-between px-md">
          <Link
            href="/"
            className="text-[15px] font-semibold tracking-tight text-ink transition-opacity duration-interaction ease-out hover:opacity-90"
          >
            LectureKit
          </Link>
          <span className="text-caption font-medium uppercase tracking-[0.18em] text-marketing-muted">
            App
          </span>
        </div>
      </header>

      <main className="animate-fade-in [--tw-duration:300ms]">
        <ProcessUrlPanel />
      </main>
    </div>
  );
}

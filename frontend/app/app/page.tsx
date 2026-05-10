/**
 * Application route (`/app`) — LectureKit workspace for URL submission + study flows.
 */

import { AppWorkspaceNavbar } from "../components/app/AppWorkspaceNavbar";
import { ProcessUrlPanel } from "../components/app/ProcessUrlPanel";

export default function AppHomePage(): JSX.Element {
  return (
    <div className="relative min-h-screen overflow-x-hidden bg-zinc-950 text-zinc-200">
      <div className="pointer-events-none absolute left-1/2 top-0 h-[420px] w-full max-w-[800px] -translate-x-1/2 rounded-full bg-purple-600/10 blur-[120px]" />
      <AppWorkspaceNavbar />
      <main className="relative z-10 pt-20">
        <ProcessUrlPanel />
      </main>
    </div>
  );
}

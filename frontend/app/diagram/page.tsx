"use client";

import { AppWorkspaceNavbar } from "../components/app/AppWorkspaceNavbar";
import { AppSubpageHeader } from "../components/app/AppSubpageHeader";

const BTN_SECONDARY =
  "rounded-full border border-zinc-700 bg-transparent px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-white/5";

export default function DiagramPage(): JSX.Element {
  return (
    <div className="flex min-h-screen flex-col bg-zinc-950 text-zinc-200">
      <AppWorkspaceNavbar />
      <div className="flex flex-1 flex-col pt-20">
        <AppSubpageHeader
          title="Architecture Diagram"
          right={
            <a href="/architecture.html" download="lecturekit_architecture.html" className={BTN_SECONDARY}>
              Download
            </a>
          }
        />
        <div className="flex-1 p-4">
          <iframe
            src="/architecture.html"
            className="w-full rounded-xl border border-white/5 bg-zinc-950"
            style={{ height: "calc(100vh - 140px)" }}
            title="LectureKit Architecture Diagram"
          />
        </div>
      </div>
    </div>
  );
}


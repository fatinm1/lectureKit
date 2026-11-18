/**
 * "Ask the lecture" client: POST /ask and read its SSE stream.
 *
 * EventSource only does GET, so this reads the response body with fetch + a stream reader and
 * parses `event:` / `data:` blocks itself. Aborting the AbortSignal closes the connection,
 * which stops Claude on the server too.
 */

import { getApiBaseUrl } from "./jobs";

export type AskSource = { n: number; start: number; end: number; snippet: string; relevance: number };
export type AskTurn = { question: string; answer: string };
export type AskDone = { answer: string; citations: number[]; grounded: boolean; cached: boolean };

export class AskError extends Error {
  constructor(
    message: string,
    public status: number
  ) {
    super(message);
  }
}

type Handlers = {
  onSources: (sources: AskSource[]) => void;
  onDelta: (text: string) => void;
};

export async function askLecture(
  body: { youtube_url: string; question: string; history: AskTurn[] },
  handlers: Handlers,
  signal?: AbortSignal
): Promise<AskDone> {
  const response = await fetch(`${getApiBaseUrl()}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok || !response.body) {
    let message = "Could not get an answer. Please try again.";
    try {
      const data = (await response.json()) as { detail?: unknown };
      if (typeof data.detail === "string") message = data.detail;
    } catch {
      /* keep the generic message */
    }
    throw new AskError(message, response.status);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      let event = "message";
      let data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7);
        else if (line.startsWith("data: ")) data += line.slice(6);
      }
      if (!data) continue;
      const payload = JSON.parse(data);
      if (event === "sources") handlers.onSources(payload.sources as AskSource[]);
      else if (event === "delta") handlers.onDelta(String(payload.text ?? ""));
      else if (event === "done") return payload as AskDone;
      else if (event === "error") throw new AskError(String(payload.message ?? "Something went wrong."), 500);
    }
  }
  throw new AskError("The answer was cut off. Please try again.", 500);
}

/** Split an answer into text and citation markers ("[2]", "[1, 3]") for rendering as links. */
export type AnswerPart = { kind: "text"; text: string } | { kind: "cite"; numbers: number[]; raw: string };

export function splitCitations(answer: string): AnswerPart[] {
  const parts: AnswerPart[] = [];
  const re = /\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\]/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(answer)) !== null) {
    if (m.index > last) parts.push({ kind: "text", text: answer.slice(last, m.index) });
    parts.push({ kind: "cite", numbers: m[1].split(",").map((s) => Number(s.trim())), raw: m[0] });
    last = m.index + m[0].length;
  }
  if (last < answer.length) parts.push({ kind: "text", text: answer.slice(last) });
  return parts;
}

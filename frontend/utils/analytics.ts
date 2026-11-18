/**
 * Product analytics (PostHog), strictly opt-in.
 *
 * Nothing loads unless NEXT_PUBLIC_POSTHOG_KEY is set: posthog-js is imported on first use, so
 * it isn't in the main bundle either. Autocapture and session recording are off. Events carry
 * only the mode, timings and outcomes, never URLs, lecture content or questions.
 *
 * Events: job_started, job_failed, study_ready, stop_clicked, ask_asked, ask_answered, rate_limited.
 */

type Props = Record<string, string | number | boolean | null | undefined>;
type Client = { capture: (event: string, props?: Props) => void };

let client: Promise<Client | null> | null = null;

function load(): Promise<Client | null> {
  if (client) return client;
  const key = process.env.NEXT_PUBLIC_POSTHOG_KEY?.trim();
  if (!key || typeof window === "undefined") {
    client = Promise.resolve(null);
    return client;
  }
  client = import("posthog-js")
    .then(({ default: posthog }) => {
      posthog.init(key, {
        api_host: process.env.NEXT_PUBLIC_POSTHOG_HOST?.trim() || "https://us.i.posthog.com",
        autocapture: false,
        capture_pageview: true,
        disable_session_recording: true,
        persistence: "localStorage",
      });
      return posthog as Client;
    })
    .catch(() => null); // blocked by an ad blocker, offline, etc.: analytics just stays off
  return client;
}

export function track(event: string, props?: Props): void {
  void load().then((c) => c?.capture(event, props));
}

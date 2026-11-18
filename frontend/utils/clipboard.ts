/**
 * Copy text to the clipboard in every mainstream browser.
 *
 * Browsers only allow clipboard writes during a click. Safari is strict about it: once code has
 * awaited anything (like creating the share link on the server), the click no longer counts and
 * `writeText` is refused. The fix is to start the write *synchronously* in the click handler
 * with a ClipboardItem whose content is a promise; the browser waits for it. Where that isn't
 * supported or is refused, fall back to `writeText`, then to the old execCommand("copy").
 *
 * Call it directly from the click handler, before any `await`.
 */

export async function copyText(text: string | Promise<string>): Promise<boolean> {
  const pending = Promise.resolve(text);

  if (typeof window !== "undefined" && "ClipboardItem" in window && navigator.clipboard?.write) {
    try {
      // Started synchronously, still inside the click; the content arrives when it's ready.
      await navigator.clipboard.write([
        new ClipboardItem({ "text/plain": pending.then((t) => new Blob([t], { type: "text/plain" })) }),
      ]);
      return true;
    } catch {
      /* not allowed here: try the next way */
    }
  }

  const value = await pending;
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value);
      return true;
    } catch {
      /* fall through */
    }
  }
  return legacyCopy(value);
}

function legacyCopy(value: string): boolean {
  const ta = document.createElement("textarea");
  ta.value = value;
  ta.setAttribute("readonly", "");
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  ta.setSelectionRange(0, value.length);
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  document.body.removeChild(ta);
  return ok;
}

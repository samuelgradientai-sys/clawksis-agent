/** Keep the screen on while a voice conversation runs (a phone that dims and
 *  locks mid-reply cuts the mic). Best effort: browsers without the Screen
 *  Wake Lock API, or that refuse it, simply let the screen sleep. */
export function holdScreenAwake(): () => void {
  let sentinel: WakeLockSentinel | null = null;
  let released = false;
  if (typeof navigator !== "undefined" && navigator.wakeLock && document.visibilityState === "visible") {
    navigator.wakeLock.request("screen").then(
      (lock) => {
        if (released) void lock.release();
        else sentinel = lock;
      },
      (err: unknown) => console.info("[voice] screen wake lock refused", err),
    );
  }
  return () => {
    released = true;
    void sentinel?.release().catch(() => undefined);
    sentinel = null;
  };
}

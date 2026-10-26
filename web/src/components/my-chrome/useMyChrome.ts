/** "Mi Chrome" state for the managed profile: the status (polled, so a connecting extension and
 *  its tabs show up on their own) plus the actions. The pairing code lives only in memory: the
 *  server shows it once and keeps nothing but its hash. */

import { useCallback, useEffect, useRef, useState } from "react";
import { myChromeApi, type MyChromeStatus } from "@/lib/api-my-chrome";
import { errorMessage } from "@/lib/api-error";
import { saveBlob } from "@/lib/save-blob";
import { myChromeCopy as copy } from "./copy";

const POLL_MS = 4000;

export type MyChromeBusy = "toggle" | "payments" | "pair" | "revoke" | "download" | null;

export interface MyChromeData {
  status: MyChromeStatus | null;
  loadError: string | null;
  busy: MyChromeBusy;
  pairing: string | null;
  reload: () => void;
  setEnabled: (enabled: boolean) => void;
  setConfirmPayments: (confirm: boolean) => void;
  pair: () => void;
  revoke: () => Promise<void>;
  download: () => void;
}

export function useMyChrome(profile: string, notify: (message: string, kind: "error" | "success") => void): MyChromeData {
  // Tagged with the profile it belongs to: switching profiles hides the old one until it loads.
  const [loaded, setLoaded] = useState<{ profile: string; status: MyChromeStatus } | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState<MyChromeBusy>(null);
  const [pairing, setPairing] = useState<{ profile: string; code: string } | null>(null);
  const request = useRef(0);

  const setStatus = useCallback((status: MyChromeStatus) => setLoaded({ profile, status }), [profile]);

  const reload = useCallback(async () => {
    const mine = ++request.current;
    try {
      const next = await myChromeApi.status();
      if (request.current !== mine) return;
      setStatus(next);
      setLoadError(null);
    } catch (err) {
      if (request.current === mine) setLoadError(errorMessage(err));
    }
  }, [setStatus]);

  useEffect(() => {
    // Dashboard data surfaces fetch from an effect on mount + scope change (same as FilesPage).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void reload();
    const timer = window.setInterval(() => void reload(), POLL_MS);
    return () => window.clearInterval(timer);
  }, [profile, reload]);

  const run = useCallback(
    async (kind: Exclude<MyChromeBusy, null>, failure: string, action: () => Promise<void>) => {
      setBusy(kind);
      try {
        await action();
      } catch (err) {
        notify(`${failure}: ${errorMessage(err)}`, "error");
        throw err;
      } finally {
        setBusy(null);
      }
    },
    [notify],
  );

  const setEnabled = useCallback(
    (enabled: boolean) =>
      void run("toggle", copy.toggleFailed, async () => setStatus(await myChromeApi.saveSettings({ enabled }))).catch(
        () => undefined,
      ),
    [run, setStatus],
  );
  const setConfirmPayments = useCallback(
    (confirm: boolean) =>
      void run("payments", copy.toggleFailed, async () =>
        setStatus(await myChromeApi.saveSettings({ confirm_payments: confirm })),
      ).catch(() => undefined),
    [run, setStatus],
  );
  const pair = useCallback(
    () =>
      void run("pair", copy.pairFailed, async () => {
        const { pairing: code } = await myChromeApi.pair();
        setPairing({ profile, code });
        await reload();
      }).catch(() => undefined),
    [profile, reload, run],
  );
  const revoke = useCallback(
    () =>
      run("revoke", copy.revokeFailed, async () => {
        await myChromeApi.revoke();
        setPairing(null);
        notify(copy.revoked, "success");
        await reload();
      }),
    [notify, reload, run],
  );
  const download = useCallback(
    () =>
      void run("download", copy.downloadFailed, async () =>
        saveBlob(await myChromeApi.extensionZip(), "clawksis-mi-chrome.zip"),
      ).catch(() => undefined),
    [run],
  );

  return {
    status: loaded?.profile === profile ? loaded.status : null,
    loadError,
    busy,
    pairing: pairing?.profile === profile ? pairing.code : null,
    reload: () => void reload(),
    setEnabled,
    setConfirmPayments,
    pair,
    revoke,
    download,
  };
}

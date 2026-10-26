import { en } from "@/i18n/en";
import type { Translations } from "@/i18n/types";

export type SessionsLabels = Required<Translations["sessions"]>;

/** The Sessions page strings with English filling every optional key a locale has not translated. */
export function sessionsLabels(t: Translations): SessionsLabels {
  return { ...en.sessions, ...t.sessions } as SessionsLabels;
}

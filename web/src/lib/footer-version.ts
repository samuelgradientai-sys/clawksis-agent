import type { StatusResponse } from "@/lib/api";

/** `v2026.7.20`, or the commit (`git.abc1234`) for a checkout without a reachable release tag. */
export function footerVersion(status: StatusResponse | null): string {
  if (status?.version == null) return "—";
  const display = (status as StatusResponse & { display_version?: string }).display_version;
  if (status.version === "unknown") return display && display !== "unknown" ? display : "—";
  return `v${status.version}`;
}

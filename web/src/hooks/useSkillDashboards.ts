import { useEffect, useState } from "react";
import { useProfileScope } from "@/contexts/useProfileScope";
import {
  skillDashboardsApi,
  type SkillDashboardSummary,
} from "@/lib/api-skill-dashboards";

/** Skills of the managed profile that declare a mini dashboard. Refreshes on
 *  profile switch and when the tab becomes visible again (a skill installed
 *  from chat shows up without a reload). Failures leave the last list. */
export function useSkillDashboards(): SkillDashboardSummary[] {
  const { profile } = useProfileScope();
  const [dashboards, setDashboards] = useState<SkillDashboardSummary[]>([]);

  useEffect(() => {
    let alive = true;
    const load = () => {
      if (document.hidden) return;
      skillDashboardsApi
        .list()
        .then((res) => alive && setDashboards(res.dashboards))
        .catch(() => {});
    };
    load();
    document.addEventListener("visibilitychange", load);
    return () => {
      alive = false;
      document.removeEventListener("visibilitychange", load);
    };
  }, [profile]);

  return dashboards;
}

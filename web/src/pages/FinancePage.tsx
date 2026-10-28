import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { Landmark, Package } from "lucide-react";
import { useI18n } from "@/i18n";
import { cn } from "@/lib/utils";
import { usePageHeader } from "@/contexts/usePageHeader";
import { useProfileScope } from "@/contexts/useProfileScope";
import { useSkillDashboards } from "@/hooks/useSkillDashboards";
import { api, type SkillInfo } from "@/lib/api";
import { financeCopy, FINANCE_CATEGORY, financePath } from "@/lib/finance";
import { SkillDashboardView } from "./SkillDashboardPage";

/** Finanzas: every finance skill in one place. Skills with a dashboard get a
 *  tab (their panels and settings); the rest are listed below. */
export default function FinancePage() {
  const { name } = useParams();
  const navigate = useNavigate();
  const { t } = useI18n();
  const copy = financeCopy(t);
  const { setTitle } = usePageHeader();
  const { profile } = useProfileScope();
  const boards = useSkillDashboards().filter((d) => d.category === FINANCE_CATEGORY && d.enabled);
  const [skills, setSkills] = useState<SkillInfo[]>([]);

  useEffect(() => setTitle(copy.title), [setTitle, copy.title]);
  useEffect(() => {
    let alive = true;
    api
      .getSkills()
      .then((all) => alive && setSkills(all.filter((s) => s.category === FINANCE_CATEGORY)))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [profile]);

  const selected = boards.find((b) => b.name === name) ?? boards[0];
  useEffect(() => {
    if (name && boards.length && !boards.some((b) => b.name === name)) {
      navigate(financePath(), { replace: true });
    }
  }, [name, boards, navigate]);

  const withBoard = useMemo(() => new Set(boards.map((b) => b.name)), [boards]);
  const others = skills.filter((s) => !withBoard.has(s.name));

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-5 px-1 sm:px-0">
      {boards.length > 1 && (
        <div className="flex flex-wrap gap-2" role="tablist" aria-label={copy.title}>
          {boards.map((board) => (
            <Link
              key={board.name}
              to={financePath(board.name)}
              role="tab"
              aria-selected={board.name === selected?.name}
              className={cn(
                "clawk-liquid-chip rounded-full px-4 py-1.5 text-sm transition-colors",
                board.name === selected?.name ? "text-midground" : "text-text-secondary hover:text-midground",
              )}
            >
              {board.emoji ? `${board.emoji} ` : ""}
              {board.title}
            </Link>
          ))}
        </div>
      )}

      {selected ? (
        <SkillDashboardView key={selected.name} name={selected.name} backTo={null} setsTitle={false} />
      ) : (
        <div className="clawk-liquid-panel rounded-3xl px-6 py-10 text-center">
          <Landmark className="mx-auto mb-3 h-6 w-6 text-midground" />
          <p className="text-base text-text-primary">{copy.empty}</p>
          <p className="mt-2 text-sm text-text-tertiary">{copy.emptyHint}</p>
        </div>
      )}

      {others.length > 0 && (
        <section className="clawk-liquid-panel rounded-3xl border border-white/10 px-5 py-4">
          <h2 className="mb-3 text-base font-semibold text-text-primary">{copy.otherSkills}</h2>
          <ul className="grid gap-2 sm:grid-cols-2">
            {others.map((skill) => (
              <li key={skill.name} className="flex items-start gap-3 rounded-2xl border border-white/5 px-3 py-2">
                <Package className="mt-0.5 h-4 w-4 shrink-0 text-text-tertiary" />
                <div className="min-w-0">
                  <p className="text-sm text-text-primary">
                    {skill.name}
                    {!skill.enabled && <span className="ml-2 text-xs text-text-tertiary">· {copy.disabled}</span>}
                  </p>
                  <p className="text-xs text-text-tertiary">{skill.description}</p>
                </div>
              </li>
            ))}
          </ul>
          <Link to="/skills" className="mt-3 inline-block text-sm text-text-tertiary hover:text-midground">
            {copy.manageSkills}
          </Link>
        </section>
      )}
    </div>
  );
}

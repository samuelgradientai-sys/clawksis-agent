import { useEffect, useState, type ComponentType, type FocusEvent, type MouseEvent } from "react";
import { createPortal } from "react-dom";
import { NavLink, useLocation } from "react-router";
import { ChevronDown, Gauge, Plug } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Translations } from "@/i18n/types";
import { useSkillDashboards } from "@/hooks/useSkillDashboards";
import { skillDashboardPath, type SkillDashboardSummary } from "@/lib/api-skill-dashboards";

export interface NavItem {
  icon: ComponentType<{ className?: string }>;
  label: string;
  labelKey?: string;
  path: string;
}

export type TooltipWarmRef = React.RefObject<number>;

// ── Collapsible sidebar groups ──────────────────────────────────────────────
// Chat holds its sibling views; Plugins ("Complementos") holds everything that
// extends the agent — Skills, each skill's mini dashboard, plugin tabs and
// MCP — so extensions live in one place. `home` is where the group header
// navigates; the chevron folds the group. `extensions` marks the group that
// receives the dynamic entries (skill dashboards + plugin tabs).

interface NavGroup {
  extensions?: boolean;
  home?: string;
  id: string;
  /** English fallback for locales that don't translate `labelKey` yet. */
  label: string;
  labelKey: keyof Translations["app"]["nav"];
  paths: string[];
}

const NAV_GROUPS: NavGroup[] = [
  { id: "chat", label: "Chat", labelKey: "chat", home: "/chat", paths: ["/chat", "/sessions", "/models", "/media"] },
  {
    id: "complementos",
    label: "Plugins",
    labelKey: "plugins",
    home: "/plugins",
    paths: ["/plugins", "/skills", "/mcp"],
    extensions: true,
  },
  { id: "integraciones", label: "Integrations", labelKey: "integrations", paths: ["/channels", "/webhooks", "/pairing"] },
];

// Paths whose nav entry must not stay lit on their sub-routes.
const EXACT_PATHS = new Set(["/sessions", "/skills"]);

const NAV_GROUP_STORAGE_PREFIX = "clawksis-nav-group-";

function dashboardItems(dashboards: SkillDashboardSummary[]): NavItem[] {
  return dashboards
    .filter((d) => d.enabled)
    .map((d) => ({ icon: Gauge, label: d.title, path: skillDashboardPath(d.name) }));
}

function navLabel(item: NavItem, t: Translations): string {
  return item.labelKey
    ? ((t.app.nav as Record<string, string>)[item.labelKey] ?? item.label)
    : item.label;
}

interface SidebarNavProps {
  closeMobile: () => void;
  collapsed: boolean;
  coreItems: NavItem[];
  pluginItems: NavItem[];
  t: Translations;
  tooltipWarmRef: TooltipWarmRef;
}

/** The sidebar's navigation: built-in pages folded into groups, with skill
 *  dashboards and plugin tabs inside the Plugins group. Collapsed (icon-only)
 *  mode renders one flat list — groups add nothing there. */
export function SidebarNav({ closeMobile, collapsed, coreItems, pluginItems, t, tooltipWarmRef }: SidebarNavProps) {
  const skillBoards = dashboardItems(useSkillDashboards());
  const extensions = [...skillBoards, ...pluginItems];
  const link = (item: NavItem, isCollapsed = collapsed) => (
    <SidebarNavLink
      closeMobile={closeMobile}
      collapsed={isCollapsed}
      item={item}
      key={item.path}
      t={t}
      tooltipWarmRef={tooltipWarmRef}
    />
  );

  if (collapsed) {
    return (
      <nav className="clawk-liquid-nav min-h-0 w-full flex-1 overflow-y-auto overflow-x-hidden border-t border-current/10 py-2" aria-label={t.app.navigation}>
        <ul className="flex flex-col gap-0.5">{[...coreItems, ...extensions].map((item) => link(item))}</ul>
      </nav>
    );
  }

  const byPath = new Map(coreItems.map((i) => [i.path, i]));
  const groupedPaths = new Set(NAV_GROUPS.flatMap((g) => g.paths));
  // Skill dashboards sit right under Skills; plugin tabs close the group.
  const groupItems = (group: NavGroup) => [
    ...group.paths.flatMap((p) => {
      const item = byPath.get(p);
      if (!item) return [];
      return group.extensions && p === "/skills" ? [item, ...skillBoards] : [item];
    }),
    ...(group.extensions ? pluginItems : []),
  ];

  return (
    <nav className="clawk-liquid-nav min-h-0 w-full flex-1 overflow-y-auto overflow-x-hidden border-t border-current/10 py-2" aria-label={t.app.navigation}>
      <ul className="flex flex-col gap-0.5">
        {coreItems.map((item) => {
          if (!groupedPaths.has(item.path)) return link(item);
          // A group renders where its FIRST present member sits; the rest are
          // skipped at the root level.
          const group = NAV_GROUPS.find((g) => g.paths.find((p) => byPath.has(p)) === item.path);
          if (!group) return null;
          return (
            <SidebarNavGroup
              key={"group:" + group.id}
              group={group}
              items={groupItems(group)}
              renderLink={(child) => link(child, false)}
              t={t}
              closeMobile={closeMobile}
            />
          );
        })}
      </ul>
    </nav>
  );
}

function readGroupOpen(id: string): boolean {
  try {
    const v = window.localStorage.getItem(NAV_GROUP_STORAGE_PREFIX + id);
    if (v === "0") return false;
  } catch {
    /* no persistence available */
  }
  return true; // open by default: nothing vanishes at once
}

function SidebarNavGroup({
  closeMobile,
  group,
  items,
  renderLink,
  t,
}: {
  closeMobile: () => void;
  group: NavGroup;
  items: NavItem[];
  renderLink: (item: NavItem) => React.ReactNode;
  t: Translations;
}) {
  const { pathname } = useLocation();
  const containsActive = items.some((i) => pathname === i.path || pathname.startsWith(i.path + "/"));
  const [open, setOpen] = useState<boolean>(() => readGroupOpen(group.id));
  const label = t.app.nav[group.labelKey] ?? group.label;
  const toggle = () => {
    setOpen((prev) => {
      try {
        window.localStorage.setItem(NAV_GROUP_STORAGE_PREFIX + group.id, prev ? "0" : "1");
      } catch {
        /* no persistence available */
      }
      return !prev;
    });
  };

  const home = group.home ? items.find((i) => i.path === group.home) : null;
  const HomeIcon = home?.icon;
  const children = items.filter((i) => i.path !== group.home);
  const headerClasses = cn(
    "clawk-liquid-nav-item group/nav relative flex w-full items-center gap-3",
    "px-4 py-2.5",
    "font-sans font-bold text-display uppercase text-sm tracking-[0.12em]",
    "whitespace-nowrap transition-colors cursor-pointer",
    "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-midground",
    containsActive && !open ? "text-midground" : "text-text-secondary hover:text-midground",
  );

  return (
    <li>
      <div className="flex items-center">
        {home && HomeIcon ? (
          <NavLink
            to={home.path}
            end
            onClick={closeMobile}
            className={({ isActive }) =>
              cn(headerClasses, "flex-1", isActive && "clawk-liquid-nav-active text-midground")
            }
            style={{ clipPath: "var(--component-tab-clip-path)" }}
          >
            <HomeIcon className="h-4 w-4 shrink-0" />
            <span>{label}</span>
          </NavLink>
        ) : (
          <button type="button" onClick={toggle} className={cn(headerClasses, "flex-1 text-left")}>
            <Plug className="h-4 w-4 shrink-0" />
            <span>{label}</span>
          </button>
        )}
        <button
          type="button"
          onClick={toggle}
          aria-expanded={open}
          aria-label={(open ? t.common.collapse : t.common.expand) + " " + label}
          className="mr-3 rounded-full p-1 text-text-tertiary transition-colors hover:text-midground"
        >
          <ChevronDown className={cn("h-3.5 w-3.5 transition-transform duration-150", !open && "-rotate-90")} />
        </button>
      </div>

      {open && (
        <ul className="clawk-liquid-nav-branch ml-6 mt-0.5 flex flex-col gap-0.5 border-l border-current/10 pl-1">
          {children.map((item) => renderLink(item))}
        </ul>
      )}
    </li>
  );
}

interface SidebarNavLinkProps {
  closeMobile: () => void;
  collapsed: boolean;
  item: NavItem;
  t: Translations;
  tooltipWarmRef: TooltipWarmRef;
}

function SidebarNavLink({ closeMobile, collapsed, item, tooltipWarmRef, t }: SidebarNavLinkProps) {
  const { path, icon: Icon } = item;
  const [tooltipAnchor, setTooltipAnchor] = useState<HTMLElement | null>(null);
  const label = navLabel(item, t);
  const showTooltip = (event: MouseEvent<HTMLElement> | FocusEvent<HTMLElement>) =>
    setTooltipAnchor(event.currentTarget);
  const hideTooltip = () => setTooltipAnchor(null);

  return (
    <li
      onMouseEnter={collapsed ? showTooltip : undefined}
      onMouseLeave={collapsed ? hideTooltip : undefined}
    >
      <NavLink
        to={path}
        end={EXACT_PATHS.has(path)}
        onClick={closeMobile}
        aria-label={collapsed ? label : undefined}
        onFocus={collapsed ? showTooltip : undefined}
        onBlur={collapsed ? hideTooltip : undefined}
        className={({ isActive }) =>
          cn(
            "clawk-liquid-nav-item group/nav relative flex items-center gap-3",
            "px-4 py-2",
            "font-sans font-bold text-display uppercase text-sm tracking-[0.12em]",
            "whitespace-nowrap transition-colors cursor-pointer",
            "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-midground",
            isActive ? "clawk-liquid-nav-active text-midground" : "text-text-secondary hover:text-midground",
          )
        }
        style={{ clipPath: "var(--component-tab-clip-path)" }}
      >
        <Icon className="h-3.5 w-3.5 shrink-0" />
        <span className={cn("truncate transition-opacity duration-300", collapsed ? "lg:opacity-0" : "lg:opacity-100")}>
          {label}
        </span>
      </NavLink>

      {collapsed && tooltipAnchor && (
        <SidebarTooltip anchor={tooltipAnchor} label={label} warmRef={tooltipWarmRef} />
      )}
    </li>
  );
}

interface SidebarTooltipProps {
  anchor: HTMLElement;
  label: string;
  warmRef?: TooltipWarmRef;
}

export function SidebarTooltip({ anchor, label, warmRef }: SidebarTooltipProps) {
  const rect = anchor.getBoundingClientRect();
  const sidebar = document.getElementById("app-sidebar");
  const sidebarRight = sidebar?.getBoundingClientRect().right ?? rect.right;
  const [isWarm, setIsWarm] = useState(false);

  useEffect(() => {
    if (!warmRef) {
      setIsWarm(false);
      return;
    }
    const now = Date.now();
    setIsWarm(now - warmRef.current < 300);
    warmRef.current = now;
    return () => {
      if (warmRef) warmRef.current = Date.now();
    };
  }, [warmRef]);

  return createPortal(
    <span
      className={cn(
        "clawk-liquid-chip fixed z-[100] pointer-events-none rounded-lg",
        "px-2 py-1",
        "bg-background-base border border-current/20 shadow-lg",
        "font-sans text-display text-xs tracking-[0.1em] text-midground uppercase",
      )}
      style={{
        top: rect.top + rect.height / 2,
        left: sidebarRight + 8,
        transform: "translateY(-50%)",
        opacity: isWarm ? 1 : undefined,
        animation: isWarm ? "none" : "sidebar-tooltip-in 120ms ease-out",
      }}
    >
      {label}
    </span>,
    document.body,
  );
}

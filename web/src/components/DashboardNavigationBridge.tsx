import { useEffect } from "react";
import { useNavigate } from "react-router";
import {
  DASHBOARD_NAVIGATE_EVENT,
  dashboardRoute,
} from "@/lib/dashboard-navigation";

/** Follows `dashboard_open` requests from the agent (relayed by the chat) with the app router. */
export function DashboardNavigationBridge(): null {
  const navigate = useNavigate();
  useEffect(() => {
    const onNavigate = (event: Event) => {
      const path = dashboardRoute((event as CustomEvent<unknown>).detail);
      if (path) navigate(path);
    };
    window.addEventListener(DASHBOARD_NAVIGATE_EVENT, onNavigate);
    return () => window.removeEventListener(DASHBOARD_NAVIGATE_EVENT, onNavigate);
  }, [navigate]);
  return null;
}

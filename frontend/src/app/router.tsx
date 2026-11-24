import { createBrowserRouter, Navigate, redirect } from "react-router";
import { api, ApiError } from "@/lib/api";
import { AppShell } from "./layout";
import { LoginPage } from "./login-page";
import { RouteError } from "./route-error";

async function loadRole() {
  try {
    return (await api.me()).role;
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) throw redirect("/login");
    throw e;
  }
}

async function requireAdmin() {
  if ((await loadRole()) !== "admin") throw redirect("/");
  return null;
}

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    id: "root",
    path: "/",
    loader: loadRole,
    element: <AppShell />,
    errorElement: <RouteError />,
    children: [
      {
        errorElement: <RouteError />,
        children: [
          { index: true, lazy: () => import("@/features/today/today-page").then((m) => ({ Component: m.TodayPage })) },
          { path: "grid", lazy: () => import("@/features/grid/grid-page").then((m) => ({ Component: m.GridPage })) },
          { path: "archive", lazy: () => import("@/features/archive/archive-page").then((m) => ({ Component: m.ArchivePage })) },
          { path: "analytics", lazy: () => import("@/features/analytics/analytics-page").then((m) => ({ Component: m.AnalyticsPage })) },
          { path: "alerts", lazy: () => import("@/features/alerts/alerts-page").then((m) => ({ Component: m.AlertsPage })) },
          { path: "monitor", loader: requireAdmin, lazy: () => import("@/features/monitor/monitor-page").then((m) => ({ Component: m.MonitorPage })) },
          { path: "attendance", loader: requireAdmin, lazy: () => import("@/features/attendance/attendance-page").then((m) => ({ Component: m.AttendancePage })) },
          { path: "employees", loader: requireAdmin, lazy: () => import("@/features/employees/employees-page").then((m) => ({ Component: m.EmployeesPage })) },
          { path: "settings", loader: requireAdmin, lazy: () => import("@/features/settings/settings-page").then((m) => ({ Component: m.SettingsPage })) },
          { path: "admin/employees", element: <Navigate to="/employees" replace /> },
          { path: "*", element: <Navigate to="/" replace /> },
        ],
      },
    ],
  },
]);

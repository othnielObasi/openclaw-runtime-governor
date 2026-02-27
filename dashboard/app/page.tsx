"use client";

/**
 * page.tsx — Entry point
 *
 * Two modes are supported:
 *  - Demo:  fully self-contained, simulated data, no backend needed
 *  - Live:  connects to governor-service backend via JWT auth
 *
 * The GovernorComplete component handles the full landing → login → dashboard flow.
 * For production-only deployment (no demo mode), use GovernorLogin + GovernorDashboard directly.
 */

// GovernorComplete is the self-contained single-file artifact that includes:
//   LandingPage (mode selector) → LoginPage (demo or live) → GovernorDashboard
// It is the recommended entry point for demo + live hybrid deployments.
import GovernorDashboard from "../components/GovernorDashboard";
import DemoDashboard from "../components/Governordashboard-demo";

const IS_DEMO = process.env.NEXT_PUBLIC_GOVERNOR_DEMO === "true";

export default function Page() {
  return IS_DEMO ? <DemoDashboard /> : <GovernorDashboard />;
}

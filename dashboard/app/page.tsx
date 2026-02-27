"use client";

/**
 * page.tsx — Entry point
 *
 * Landing page lets visitors choose between:
 *  - Demo:  fully self-contained, simulated data, no backend needed
 *  - Live:  connects to governor-service backend via JWT auth
 *
 * The GovernorComplete component handles the full landing → login → dashboard flow.
 */

import React, { useState } from "react";
import GovernorDashboard from "../components/GovernorDashboard";
import DemoDashboard from "../components/Governordashboard-demo";

// ── Design tokens (matching dashboard theme) ──
const C = {
  bg0: "#080e1a",
  bg1: "#0e1e30",
  bg2: "#162840",
  line: "#1a2e44",
  p1: "#dde8f5",
  p2: "#7a9dbd",
  p3: "#3d5e7a",
  accent: "#e8412a",
  green: "#22c55e",
};
const mono = "'IBM Plex Mono', monospace";
const sans = "'DM Sans', sans-serif";

function ClawIcon({ size = 54 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" style={{
      display: "block",
      filter: `drop-shadow(0 0 8px ${C.accent}) drop-shadow(0 0 20px ${C.accent}44)`,
    }}>
      <polygon points="50,4 88,25 88,75 50,96 12,75 12,25"
        fill="none" stroke={C.accent} strokeWidth="1.5" opacity="0.9" />
      <polygon points="50,12 82,30 82,70 50,88 18,70 18,30"
        fill="none" stroke={C.accent} strokeWidth="0.5" opacity="0.25" />
      <line x1="30" y1="28" x2="46" y2="72" stroke={C.accent} strokeWidth="4.5" strokeLinecap="round" />
      <line x1="46" y1="22" x2="62" y2="78" stroke={C.accent} strokeWidth="4.5" strokeLinecap="round" />
      <line x1="62" y1="28" x2="76" y2="72" stroke={C.accent} strokeWidth="4.5" strokeLinecap="round" />
    </svg>
  );
}

function LandingPage({ onSelect }: { onSelect: (mode: "demo" | "live") => void }) {
  const [hovered, setHovered] = useState<string | null>(null);

  const cardStyle = (id: string): React.CSSProperties => ({
    flex: 1,
    maxWidth: 340,
    background: hovered === id ? C.bg2 : C.bg1,
    border: `1px solid ${hovered === id ? C.accent : C.line}`,
    borderRadius: 12,
    padding: "36px 28px",
    cursor: "pointer",
    transition: "all 0.25s ease",
    transform: hovered === id ? "translateY(-4px)" : "none",
    boxShadow: hovered === id ? `0 8px 32px ${C.accent}22` : "none",
    textAlign: "center",
  });

  return (
    <div style={{
      minHeight: "100vh",
      background: C.bg0,
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      padding: 24,
    }}>
      {/* Logo + Title */}
      <div style={{ marginBottom: 12 }}>
        <ClawIcon size={64} />
      </div>
      <h1 style={{
        fontFamily: mono,
        fontSize: 22,
        fontWeight: 700,
        color: C.p1,
        letterSpacing: 3,
        textTransform: "uppercase",
        margin: "0 0 6px",
      }}>
        OpenClaw Governor
      </h1>
      <p style={{
        fontFamily: sans,
        fontSize: 13,
        color: C.p3,
        margin: "0 0 40px",
        letterSpacing: 0.5,
      }}>
        Runtime governance &amp; safety console
      </p>

      {/* Mode cards */}
      <div style={{
        display: "flex",
        gap: 24,
        flexWrap: "wrap",
        justifyContent: "center",
        width: "100%",
        maxWidth: 720,
      }}>
        {/* Demo Card */}
        <div
          style={cardStyle("demo")}
          onMouseEnter={() => setHovered("demo")}
          onMouseLeave={() => setHovered(null)}
          onClick={() => onSelect("demo")}
        >
          <div style={{ fontSize: 36, marginBottom: 14 }}>🎮</div>
          <h2 style={{
            fontFamily: mono,
            fontSize: 15,
            fontWeight: 700,
            color: C.green,
            letterSpacing: 2,
            textTransform: "uppercase",
            margin: "0 0 10px",
          }}>
            Demo Mode
          </h2>
          <p style={{ fontFamily: sans, fontSize: 12.5, color: C.p2, margin: 0, lineHeight: 1.6 }}>
            Fully self-contained with simulated data. No backend required. Explore the governance dashboard instantly.
          </p>
          <div style={{
            marginTop: 18,
            fontFamily: mono,
            fontSize: 10,
            color: C.p3,
            letterSpacing: 1,
          }}>
            admin@openclaw.io / govern
          </div>
        </div>

        {/* Live Card */}
        <div
          style={cardStyle("live")}
          onMouseEnter={() => setHovered("live")}
          onMouseLeave={() => setHovered(null)}
          onClick={() => onSelect("live")}
        >
          <div style={{ fontSize: 36, marginBottom: 14 }}>🔒</div>
          <h2 style={{
            fontFamily: mono,
            fontSize: 15,
            fontWeight: 700,
            color: C.accent,
            letterSpacing: 2,
            textTransform: "uppercase",
            margin: "0 0 10px",
          }}>
            Live Mode
          </h2>
          <p style={{ fontFamily: sans, fontSize: 12.5, color: C.p2, margin: 0, lineHeight: 1.6 }}>
            Connect to the governor-service backend with JWT auth. Real-time policy enforcement and telemetry.
          </p>
          <div style={{
            marginTop: 18,
            fontFamily: mono,
            fontSize: 10,
            color: C.p3,
            letterSpacing: 1,
          }}>
            REQUIRES RUNNING BACKEND
          </div>
        </div>
      </div>

      {/* Footer */}
      <p style={{
        fontFamily: mono,
        fontSize: 9,
        color: C.p3,
        marginTop: 48,
        letterSpacing: 1.5,
        textTransform: "uppercase",
      }}>
        SOVEREIGN AI LAB
      </p>
    </div>
  );
}

export default function Page() {
  const [mode, setMode] = useState<"landing" | "demo" | "live">("landing");

  if (mode === "demo") return <DemoDashboard />;
  if (mode === "live") return <GovernorDashboard />;
  return <LandingPage onSelect={setMode} />;
}

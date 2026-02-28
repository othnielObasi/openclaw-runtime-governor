"use client";

/**
 * page.tsx — Entry point
 *
 * Landing page lets visitors choose between:
 *  - Demo:  fully self-contained, simulated data, no backend needed
 *  - Live:  connects to governor-service backend via JWT auth
 */

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useAuth } from "../components/AuthContext";
import GovernorLogin from "../components/GovernorLogin";
import GovernorDashboard from "../components/GovernorDashboard";
import DemoDashboard from "../components/Governordashboard-demo";

// ── Design tokens ──
const C = {
  bg0: "#080e1a",
  bg1: "#0e1e30",
  bg2: "#162840",
  bg3: "#1d3452",
  line: "#1a2e44",
  line2: "#243d58",
  p1: "#dde8f5",
  p2: "#7a9dbd",
  p3: "#3d5e7a",
  accent: "#e8412a",
  green: "#22c55e",
  greenDim: "rgba(34,197,94,0.10)",
  amber: "#f59e0b",
  amberDim: "rgba(245,158,11,0.10)",
  red: "#ef4444",
  redDim: "rgba(239,68,68,0.10)",
  accentDim: "rgba(232,65,42,0.10)",
};
const mono = "'IBM Plex Mono', monospace";
const sans = "'DM Sans', sans-serif";

// ── Governance layers (core identity of the project) ──
const LAYERS = [
  { key: "kill",     icon: "⚡", label: "Kill Switch",       color: C.red,   desc: "Instant global halt" },
  { key: "firewall", icon: "🛡", label: "Injection Firewall", color: C.amber, desc: "Prompt-injection scan" },
  { key: "scope",    icon: "🔒", label: "Scope Enforcer",    color: C.amber, desc: "Tool allow-listing" },
  { key: "policy",   icon: "📋", label: "Policy Engine",     color: C.accent,desc: "YAML + runtime rules" },
  { key: "neuro",    icon: "🧠", label: "Neuro Estimator",   color: C.p2,    desc: "Heuristic risk scoring" },
];

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

// ── Animated layer pipeline visualization ──
function LayerPipeline() {
  const [activeIdx, setActiveIdx] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setActiveIdx(i => (i + 1) % LAYERS.length), 2200);
    return () => clearInterval(t);
  }, []);

  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 0,
      justifyContent: "center", flexWrap: "wrap",
      margin: "0 auto", maxWidth: 900,
    }}>
      {LAYERS.map((layer, i) => {
        const active = i === activeIdx;
        return (
          <React.Fragment key={layer.key}>
            {i > 0 && (
              <div style={{
                width: 40, height: 2,
                background: i <= activeIdx ? C.green : C.line,
                transition: "background 0.4s ease",
                flexShrink: 0,
              }} />
            )}
            <div style={{
              display: "flex", flexDirection: "column", alignItems: "center",
              gap: 6, padding: "10px 10px", minWidth: 115,
              opacity: active ? 1 : 0.55, transition: "all 0.4s ease",
              transform: active ? "scale(1.08)" : "scale(1)",
            }}>
              <div style={{
                width: 48, height: 48, borderRadius: 10,
                background: active ? `${layer.color}18` : C.bg1,
                border: `1.5px solid ${active ? layer.color : C.line}`,
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 22, transition: "all 0.4s ease",
                boxShadow: active ? `0 0 12px ${layer.color}33` : "none",
              }}>
                {layer.icon}
              </div>
              <span style={{
                fontFamily: mono, fontSize: 10, fontWeight: 600,
                color: active ? layer.color : C.p3,
                letterSpacing: 1.2, textTransform: "uppercase",
                transition: "color 0.4s ease", textAlign: "center",
              }}>
                {layer.label}
              </span>
              <span style={{
                fontFamily: sans, fontSize: 11, color: C.p3,
                textAlign: "center", lineHeight: 1.4,
              }}>
                {layer.desc}
              </span>
            </div>
          </React.Fragment>
        );
      })}
    </div>
  );
}

// ── Simulated evaluation result ──
function SimulatedDecision() {
  const [phase, setPhase] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setPhase(p => (p + 1) % 3), 3500);
    return () => clearInterval(t);
  }, []);

  const scenarios = [
    { decision: "ALLOW", risk: 12, color: C.green, tool: "http_request", policy: "base-allow" },
    { decision: "BLOCK", risk: 87, color: C.red,   tool: "shell_exec",   policy: "injection-firewall" },
    { decision: "REVIEW", risk: 55, color: C.amber, tool: "file_write",  policy: "scope-enforcer" },
  ];
  const s = scenarios[phase];

  return (
    <div style={{
      background: C.bg1, border: `1px solid ${C.line}`,
      borderLeft: `3px solid ${s.color}`,
      padding: "16px 22px", maxWidth: 560, margin: "0 auto",
      fontFamily: mono, fontSize: 13, transition: "border-color 0.4s ease",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
        <span style={{ color: C.p3, letterSpacing: 1.5 }}>EVALUATION</span>
        <span style={{
          color: s.color, fontWeight: 700, letterSpacing: 1.5,
          textShadow: `0 0 8px ${s.color}44`,
        }}>
          {s.decision}
        </span>
      </div>
      <div style={{ display: "flex", gap: 20, color: C.p2, fontSize: 12 }}>
        <span>tool: <span style={{ color: C.p1 }}>{s.tool}</span></span>
        <span>risk: <span style={{ color: s.color }}>{s.risk}</span></span>
        <span>policy: <span style={{ color: C.p1 }}>{s.policy}</span></span>
      </div>
    </div>
  );
}

function LandingPage({ onSelect }: { onSelect: (mode: "demo" | "live") => void }) {
  const [hovered, setHovered] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);
  useEffect(() => { setTimeout(() => setMounted(true), 50); }, []);

  return (
    <div style={{
      minHeight: "100vh",
      background: `radial-gradient(ellipse 60% 40% at 50% 20%, #0d2233 0%, ${C.bg0} 60%)`,
      display: "flex", flexDirection: "column", alignItems: "center",
      padding: "60px 32px 48px",
      opacity: mounted ? 1 : 0, transition: "opacity 0.6s ease",
    }}>
      {/* ── Header ── */}
      <div style={{ display: "flex", alignItems: "center", gap: 18, marginBottom: 12 }}>
        <ClawIcon size={64} />
        <div>
          <h1 style={{
            fontFamily: mono, fontSize: 28, fontWeight: 700,
            color: C.p1, letterSpacing: 4, textTransform: "uppercase",
            margin: 0,
          }}>
            OpenClaw Governor
          </h1>
          <div style={{
            fontFamily: mono, fontSize: 11, color: C.p3,
            letterSpacing: 3, textTransform: "uppercase", marginTop: 4,
          }}>
            RUNTIME GOVERNANCE · SAFETY · AUDIT
          </div>
        </div>
      </div>

      {/* ── Tagline ── */}
      <p style={{
        fontFamily: sans, fontSize: 17, color: C.p2,
        margin: "20px 0 10px", textAlign: "center", maxWidth: 640, lineHeight: 1.65,
      }}>
        A 5-layer runtime governance engine that intercepts every AI agent tool call —
        evaluating risk, enforcing policies, and producing auditable decisions in real time.
      </p>
      <div style={{
        display: "flex", gap: 14, justifyContent: "center", flexWrap: "wrap",
        marginBottom: 36,
      }}>
        {["Policy-as-Code", "Kill Switch", "RBAC Auth", "Audit Trail", "SURGE Tokens"].map(tag => (
          <span key={tag} style={{
            fontFamily: mono, fontSize: 10.5, color: C.p3,
            padding: "5px 14px", border: `1px solid ${C.line}`,
            letterSpacing: 1.2, textTransform: "uppercase",
          }}>
            {tag}
          </span>
        ))}
      </div>

      {/* ── Layer Pipeline ── */}
      <div style={{
        width: "100%", maxWidth: 900, marginBottom: 32,
        padding: "24px 20px", background: `${C.bg1}88`,
        border: `1px solid ${C.line}`, borderRadius: 10,
      }}>
        <div style={{
          fontFamily: mono, fontSize: 10, color: C.p3,
          letterSpacing: 2.5, textTransform: "uppercase",
          textAlign: "center", marginBottom: 16,
        }}>
          EVALUATION PIPELINE
        </div>
        <LayerPipeline />
      </div>

      {/* ── Live decision preview ── */}
      <div style={{ width: "100%", maxWidth: 900, marginBottom: 40 }}>
        <SimulatedDecision />
      </div>

      {/* ── Mode selection ── */}
      <div style={{
        display: "flex", gap: 24, flexWrap: "wrap", justifyContent: "center",
        width: "100%", maxWidth: 900,
      }}>
        {/* Demo */}
        <div
          style={{
            flex: 1, minWidth: 300, maxWidth: 420,
            background: hovered === "demo" ? C.bg2 : C.bg1,
            border: `1px solid ${hovered === "demo" ? C.green : C.line}`,
            borderTop: `3px solid ${hovered === "demo" ? C.green : C.line}`,
            padding: "30px 28px", cursor: "pointer",
            transition: "all 0.25s ease",
            transform: hovered === "demo" ? "translateY(-3px)" : "none",
            boxShadow: hovered === "demo" ? `0 6px 24px ${C.green}18` : "none",
          }}
          onMouseEnter={() => setHovered("demo")}
          onMouseLeave={() => setHovered(null)}
          onClick={() => onSelect("demo")}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
            <div style={{
              width: 10, height: 10, borderRadius: "50%",
              background: C.green, boxShadow: `0 0 8px ${C.green}`,
            }} />
            <h2 style={{
              fontFamily: mono, fontSize: 16, fontWeight: 700,
              color: C.green, letterSpacing: 2.5, textTransform: "uppercase", margin: 0,
            }}>
              Demo Mode
            </h2>
          </div>
          <p style={{
            fontFamily: sans, fontSize: 14, color: C.p2, margin: "0 0 16px", lineHeight: 1.6,
          }}>
            Self-contained with simulated agents, tool calls, and policy decisions.
            No backend required — explore the full governance dashboard instantly.
          </p>
          <div style={{
            fontFamily: mono, fontSize: 11, color: C.p3,
            padding: "7px 14px", background: C.bg0,
            border: `1px solid ${C.line}`, letterSpacing: 0.5,
          }}>
            <span style={{ color: C.p3 }}>credentials:</span>{" "}
            <span style={{ color: C.p2 }}>admin</span>{" "}
            <span style={{ color: C.p3 }}>/</span>{" "}
            <span style={{ color: C.p2 }}>govern</span>
          </div>
        </div>

        {/* Live */}
        <div
          style={{
            flex: 1, minWidth: 300, maxWidth: 420,
            background: hovered === "live" ? C.bg2 : C.bg1,
            border: `1px solid ${hovered === "live" ? C.accent : C.line}`,
            borderTop: `3px solid ${hovered === "live" ? C.accent : C.line}`,
            padding: "30px 28px", cursor: "pointer",
            transition: "all 0.25s ease",
            transform: hovered === "live" ? "translateY(-3px)" : "none",
            boxShadow: hovered === "live" ? `0 6px 24px ${C.accent}18` : "none",
          }}
          onMouseEnter={() => setHovered("live")}
          onMouseLeave={() => setHovered(null)}
          onClick={() => onSelect("live")}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
            <div style={{
              width: 10, height: 10, borderRadius: "50%",
              background: C.accent, boxShadow: `0 0 8px ${C.accent}`,
            }} />
            <h2 style={{
              fontFamily: mono, fontSize: 16, fontWeight: 700,
              color: C.accent, letterSpacing: 2.5, textTransform: "uppercase", margin: 0,
            }}>
              Live Mode
            </h2>
          </div>
          <p style={{
            fontFamily: sans, fontSize: 14, color: C.p2, margin: "0 0 16px", lineHeight: 1.6,
          }}>
            Connect to governor-service with JWT auth. Real-time policy enforcement,
            telemetry streams, and admin controls for production governance.
          </p>
          <div style={{
            fontFamily: mono, fontSize: 11, color: C.p3,
            padding: "7px 14px", background: C.bg0,
            border: `1px solid ${C.line}`, letterSpacing: 0.5,
          }}>
            <span style={{ color: C.p3 }}>requires:</span>{" "}
            <span style={{ color: C.p2 }}>governor-service backend</span>
          </div>
        </div>
      </div>

      {/* ── Documentation link ── */}
      <Link href="/docs" style={{
        fontFamily: mono, fontSize: 12, fontWeight: 600,
        color: C.p3, letterSpacing: 2, textDecoration: "none",
        padding: "10px 24px", marginTop: 32,
        border: `1px solid ${C.line}`,
        transition: "all 0.2s ease",
        textTransform: "uppercase",
      }}
        onMouseEnter={(e: React.MouseEvent<HTMLAnchorElement>) => {
          e.currentTarget.style.borderColor = C.p2;
          e.currentTarget.style.color = C.p1;
        }}
        onMouseLeave={(e: React.MouseEvent<HTMLAnchorElement>) => {
          e.currentTarget.style.borderColor = C.line;
          e.currentTarget.style.color = C.p3;
        }}
      >
        📖 Documentation
      </Link>

      {/* ── Footer ── */}
      <div style={{
        marginTop: 52, display: "flex", flexDirection: "column",
        alignItems: "center", gap: 6,
      }}>
        <div style={{
          display: "flex", gap: 16, alignItems: "center",
        }}>
          <span style={{ fontFamily: mono, fontSize: 11, color: C.p3, letterSpacing: 2 }}>
            SOVEREIGN AI LAB
          </span>
          <span style={{ color: C.line }}>·</span>
          <span style={{ fontFamily: mono, fontSize: 11, color: C.p3, letterSpacing: 2 }}>
            TRACK 3 · DEV INFRA
          </span>
          <span style={{ color: C.line }}>·</span>
          <span style={{ fontFamily: mono, fontSize: 11, color: C.p3, letterSpacing: 2 }}>
            SURGE × OPENCLAW
          </span>
        </div>
      </div>
    </div>
  );
}

export default function Page() {
  const { user, logout, loading } = useAuth();
  const [mode, setMode] = useState<"landing" | "demo" | "live">("landing");

  // Loading auth state from localStorage
  if (loading) {
    return (
      <div style={{
        minHeight:"100vh", background:"#080e1a",
        display:"flex", alignItems:"center", justifyContent:"center",
        fontFamily: mono, fontSize: 10, color: "#3d5e7a",
        letterSpacing: 3, textTransform: "uppercase",
      }}>
        INITIALISING GOVERNOR…
      </div>
    );
  }

  // Demo mode — self-contained, has its own login/logout
  if (mode === "demo") {
    return <DemoDashboard onExit={() => setMode("landing")} />;
  }

  // Live mode — require real authentication
  if (mode === "live") {
    if (!user) {
      return <GovernorLogin onBack={() => setMode("landing")} />;
    }
    return (
      <GovernorDashboard
        userRole={user.role}
        userName={user.name}
        onLogout={() => { logout(); setMode("landing"); }}
      />
    );
  }

  return <LandingPage onSelect={setMode} />;
}

"use client";
import React, { useState, useEffect, useRef, useCallback } from "react";

// ═══════════════════════════════════════════════════════════
// ONBOARDING GUIDE  —  Floating step-through overlay
// Users can dismiss permanently or re-open from Settings / "?" FAB
// ═══════════════════════════════════════════════════════════

const C = {
  bg0:"#080e1a", bg1:"#0e1e30", bg2:"#162840", bg3:"#1d3452",
  line:"#1a2e44", line2:"#243d58",
  p1:"#dde8f5", p2:"#7a9dbd", p3:"#3d5e7a",
  green:"#22c55e", greenDim:"rgba(34,197,94,0.12)",
  amber:"#f59e0b", amberDim:"rgba(245,158,11,0.12)",
  red:"#ef4444", redDim:"rgba(239,68,68,0.12)",
  accent:"#e8412a", accentDim:"rgba(232,65,42,0.12)",
};
const mono = "'IBM Plex Mono', monospace";
const sans = "'DM Sans', sans-serif";

const STORAGE_KEY = "ocg_onboarding_dismissed";

// Each step: { title, body, tabId (optional — highlights that sidebar tab), icon }
const STEPS = [
  { title: "Welcome to OpenClaw Governor", body: "Your AI governance control plane. This quick tour will walk you through the key hubs — you can skip or dismiss at any time.", icon: "🛡", tabId: null },
  { title: "Dashboard — Live Overview", body: "Real-time evaluations, allow/review/block counts, risk distribution, and a live action feed — all updating via SSE.", icon: "◈", tabId: "dashboard" },
  { title: "Agent Demo", body: "Run a governed agent in the Agent Demo to observe decisions and telemetry in real-time.", icon: "🤖", tabId: "agent" },
  { title: "Action Tester", body: "Use the Action Tester to simulate tool calls against the 6-layer governance pipeline and inspect evaluation traces.", icon: "▶", tabId: "tester" },
  { title: "Policy Editor", body: "Create, edit, toggle and version governance policies. Policy changes are applied across evaluations immediately.", icon: "◆", tabId: "policyEditor" },
  { title: "Review Queue & SURGE", body: "Inspect the Review Queue for pending escalations and view SURGE receipts for cryptographic audit evidence.", icon: "⚡", tabId: "reviewQueue" },
  { title: "Audit Trail & Traces", body: "Explore the Audit Trail and distributed Traces to review full evaluation histories and span trees.", icon: "☰", tabId: "auditTrail" },
  { title: "Conversations & Traces", body: "View encrypted Conversations and Traces to investigate agent interactions and post-execution verification logs.", icon: "💬", tabId: "conversations" },
  { title: "Topology & API Keys", body: "Check the Topology view for deployed module health and copy API Keys to access the Governor programmatically.", icon: "◎", tabId: "topology" },
  { title: "Settings & Users", body: "Configure escalation thresholds, kill-switch rules, notification channels, and manage users and RBAC.", icon: "⚙", tabId: "settings" },
  { title: "You're All Set!", body: "Explore freely. Re-open this guide anytime from Settings or the ? button in the bottom-right corner.", icon: "🚀", tabId: null },
];

export default function OnboardingGuide({ onNavigateTab, visible, onClose }) {
  const [step, setStep] = useState(0);
  const [minimized, setMinimized] = useState(false);
  const cardRef = useRef(null);

  // Reset step when guide opens
  useEffect(() => {
    if (visible) setStep(0);
  }, [visible]);

  // Navigate to the tab when a step with tabId is active
  useEffect(() => {
    if (visible && !minimized && STEPS[step]?.tabId && onNavigateTab) {
      onNavigateTab(STEPS[step].tabId);
    }
  }, [step, visible, minimized]);

  // Add highlight pulse to sidebar tab button
  useEffect(() => {
    if (!visible || minimized) return;
    const tabId = STEPS[step]?.tabId;
    if (!tabId) return;

    // Find the sidebar button by matching data-tab attribute
    const btn = document.querySelector(`[data-tab="${tabId}"]`);
    if (!btn) return;

    const prev = btn.style.boxShadow;
    const prevBg = btn.style.background;
    btn.style.boxShadow = `0 0 0 2px ${C.accent}, 0 0 12px ${C.accent}44`;
    btn.style.background = C.accentDim;
    btn.style.transition = "box-shadow 0.3s, background 0.3s";

    return () => {
      btn.style.boxShadow = prev;
      btn.style.background = prevBg;
      btn.style.transition = "";
    };
  }, [step, visible, minimized]);

  const handleDismiss = useCallback(() => {
    if (typeof window !== "undefined") {
      localStorage.setItem(STORAGE_KEY, "true");
    }
    onClose();
  }, [onClose]);

  const handleSkip = useCallback(() => {
    onClose();
  }, [onClose]);

  if (!visible) return null;

  const s = STEPS[step];
  const isFirst = step === 0;
  const isLast = step === STEPS.length - 1;
  const progress = ((step + 1) / STEPS.length) * 100;

  // ── Minimized FAB ──
  if (minimized) {
    return (
      <div
        onClick={() => setMinimized(false)}
        style={{
          position: "fixed", bottom: 24, right: 24, zIndex: 10000,
          width: 48, height: 48, borderRadius: "50%",
          background: C.accent, color: "#fff",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 22, cursor: "pointer",
          boxShadow: `0 4px 20px rgba(0,0,0,0.5), 0 0 0 2px ${C.line2}`,
          transition: "transform 0.2s",
        }}
        onMouseEnter={e => e.currentTarget.style.transform = "scale(1.1)"}
        onMouseLeave={e => e.currentTarget.style.transform = "scale(1)"}
        title="Resume onboarding tour"
      >
        ?
      </div>
    );
  }

  // ── Full floating card ──
  return (
    <>
      {/* Subtle backdrop overlay on content area only */}
      <div style={{
        position: "fixed", inset: 0, zIndex: 9998,
        background: "rgba(0,0,0,0.25)",
        pointerEvents: "none",
      }} />

      <div ref={cardRef} style={{
        position: "fixed", bottom: 28, right: 28, zIndex: 10000,
        width: 380, maxWidth: "calc(100vw - 56px)",
        background: C.bg1,
        border: `1px solid ${C.line2}`,
        borderRadius: 12,
        boxShadow: `0 8px 32px rgba(0,0,0,0.6), 0 0 0 1px ${C.line}`,
        fontFamily: sans,
        animation: "onboardSlideIn 0.3s ease-out",
        overflow: "hidden",
      }}>

        {/* ── Progress bar ── */}
        <div style={{ height: 3, background: C.bg0 }}>
          <div style={{
            height: "100%", width: `${progress}%`,
            background: `linear-gradient(90deg, ${C.accent}, ${C.amber})`,
            transition: "width 0.3s ease",
          }} />
        </div>

        {/* ── Header ── */}
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "14px 16px 0",
        }}>
          <div style={{
            fontFamily: mono, fontSize: 10, color: C.p3,
            letterSpacing: 1.5, textTransform: "uppercase",
          }}>
            TOUR · {step + 1} / {STEPS.length}
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <button
              onClick={() => setMinimized(true)}
              style={{
                background: "transparent", border: "none", color: C.p3,
                cursor: "pointer", fontSize: 16, padding: "2px 6px",
                lineHeight: 1,
              }}
              title="Minimize"
            >
              ─
            </button>
            <button
              onClick={handleSkip}
              style={{
                background: "transparent", border: "none", color: C.p3,
                cursor: "pointer", fontSize: 16, padding: "2px 6px",
                lineHeight: 1,
              }}
              title="Close tour"
            >
              ✕
            </button>
          </div>
        </div>

        {/* ── Content ── */}
        <div style={{ padding: "12px 16px 16px" }}>
          <div style={{
            display: "flex", alignItems: "center", gap: 10, marginBottom: 10,
          }}>
            <span style={{ fontSize: 24 }}>{s.icon}</span>
            <div style={{
              fontFamily: mono, fontSize: 15, fontWeight: 700,
              color: C.p1, letterSpacing: 0.5,
            }}>
              {s.title}
            </div>
          </div>
          <div style={{
            fontSize: 13, color: C.p2, lineHeight: 1.6,
            minHeight: 48,
          }}>
            {s.body}
          </div>
        </div>

        {/* ── Step dots ── */}
        <div style={{
          display: "flex", justifyContent: "center", gap: 5,
          padding: "0 16px 12px",
        }}>
          {STEPS.map((_, i) => (
            <div
              key={i}
              onClick={() => setStep(i)}
              style={{
                width: i === step ? 18 : 6, height: 6,
                borderRadius: 3,
                background: i === step ? C.accent : i < step ? C.p3 : C.line2,
                cursor: "pointer",
                transition: "all 0.2s",
              }}
            />
          ))}
        </div>

        {/* ── Footer buttons ── */}
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "0 16px 14px",
        }}>
          {/* Left: dismiss link */}
          <button
            onClick={handleDismiss}
            style={{
              background: "transparent", border: "none",
              color: C.p3, fontSize: 11, cursor: "pointer",
              fontFamily: mono, letterSpacing: 0.5,
              textDecoration: "underline", textUnderlineOffset: 2,
            }}
          >
            Don't show again
          </button>

          {/* Right: nav buttons */}
          <div style={{ display: "flex", gap: 8 }}>
            {!isFirst && (
              <button
                onClick={() => setStep(s => s - 1)}
                style={{
                  fontFamily: mono, fontSize: 11, letterSpacing: 1,
                  padding: "6px 14px",
                  border: `1px solid ${C.line2}`, borderRadius: 6,
                  color: C.p2, background: "transparent",
                  cursor: "pointer",
                  transition: "all 0.15s",
                }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = C.p3; e.currentTarget.style.color = C.p1; }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = C.line2; e.currentTarget.style.color = C.p2; }}
              >
                ← BACK
              </button>
            )}
            {isLast ? (
              <button
                onClick={handleDismiss}
                style={{
                  fontFamily: mono, fontSize: 11, letterSpacing: 1,
                  padding: "6px 16px",
                  border: "none", borderRadius: 6,
                  color: "#fff", background: C.accent,
                  cursor: "pointer", fontWeight: 700,
                  transition: "all 0.15s",
                }}
                onMouseEnter={e => e.currentTarget.style.opacity = "0.85"}
                onMouseLeave={e => e.currentTarget.style.opacity = "1"}
              >
                FINISH ✓
              </button>
            ) : (
              <button
                onClick={() => setStep(s => s + 1)}
                style={{
                  fontFamily: mono, fontSize: 11, letterSpacing: 1,
                  padding: "6px 16px",
                  border: "none", borderRadius: 6,
                  color: "#fff", background: C.accent,
                  cursor: "pointer", fontWeight: 700,
                  transition: "all 0.15s",
                }}
                onMouseEnter={e => e.currentTarget.style.opacity = "0.85"}
                onMouseLeave={e => e.currentTarget.style.opacity = "1"}
              >
                NEXT →
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Animations */}
      <style>{`
        @keyframes onboardSlideIn {
          from { opacity: 0; transform: translateY(16px) scale(0.97); }
          to   { opacity: 1; transform: translateY(0) scale(1); }
        }
      `}</style>
    </>
  );
}

// Helper check for first-visit auto-show
export function shouldShowOnboarding() {
  if (typeof window === "undefined") return false;
  return localStorage.getItem(STORAGE_KEY) !== "true";
}

// Reset onboarding (for Settings "Restart Tour" button)
export function resetOnboarding() {
  if (typeof window !== "undefined") {
    localStorage.removeItem(STORAGE_KEY);
  }
}

"use client";

import { useState, useEffect } from "react";
import { useAuth } from "./AuthContext";

// ── DESIGN TOKENS ────────────────────────────────────────────
const C = {
  bg0:"#080e1a", bg1:"#0e1e30", bg2:"#162840",
  line:"#1a2e44", line2:"#243d58",
  p1:"#dde8f5", p2:"#7a9dbd", p3:"#3d5e7a",
  green:"#22c55e", greenDim:"rgba(34,197,94,0.10)",
  amber:"#f59e0b",
  red:"#ef4444",   redDim:"rgba(239,68,68,0.10)",
  accent:"#e8412a", accentDim:"rgba(232,65,42,0.12)",
};
const mono = "'IBM Plex Mono', 'Courier New', monospace";

function ClawIcon({ size = 54, pulse = false }: { size?: number; pulse?: boolean }) {
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" style={{
      display:"block",
      filter: pulse
        ? `drop-shadow(0 0 8px ${C.accent}) drop-shadow(0 0 20px ${C.accent}44)`
        : `drop-shadow(0 0 4px ${C.accent}66)`,
      transition:"filter 0.4s ease",
    }}>
      <polygon points="50,4 88,25 88,75 50,96 12,75 12,25"
        fill="none" stroke={C.accent} strokeWidth="1.5" opacity="0.9"/>
      <polygon points="50,12 82,30 82,70 50,88 18,70 18,30"
        fill="none" stroke={C.accent} strokeWidth="0.5" opacity="0.25"/>
      <line x1="30" y1="28" x2="46" y2="72" stroke={C.accent} strokeWidth="4.5" strokeLinecap="round"/>
      <line x1="46" y1="22" x2="62" y2="78" stroke={C.accent} strokeWidth="4.5" strokeLinecap="round"/>
      <line x1="62" y1="28" x2="76" y2="72" stroke={C.accent} strokeWidth="4.5" strokeLinecap="round"/>
    </svg>
  );
}

const SCAN_STEPS = [
  "Verifying identity token…",
  "Checking authority binding…",
  "Loading governance context…",
  "Establishing secure session…",
];

export default function GovernorLogin() {
  const { login } = useAuth();
  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [showPass, setShowPass] = useState(false);
  const [phase, setPhase]       = useState<"idle"|"scanning"|"error"|"success">("idle");
  const [scanStep, setScanStep] = useState(0);
  const [errorMsg, setErrorMsg] = useState("");
  const [mounted, setMounted]   = useState(false);
  const [glitch, setGlitch]     = useState(false);

  useEffect(() => { setTimeout(() => setMounted(true), 80); }, []);

  useEffect(() => {
    const t = setInterval(() => {
      setGlitch(true);
      setTimeout(() => setGlitch(false), 150);
    }, 7000);
    return () => clearInterval(t);
  }, []);

  const handleAuth = async () => {
    if (!email || !password || phase === "scanning") return;
    setPhase("scanning");
    setScanStep(0);
    setErrorMsg("");

    // Animate scan steps
    for (let i = 0; i < SCAN_STEPS.length; i++) {
      await new Promise(r => setTimeout(r, 480));
      setScanStep(i + 1);
    }

    try {
      await login(email, password);
      setPhase("success");
      // page.tsx will redirect automatically via AuthContext state change
    } catch (err: any) {
      setErrorMsg(err.message || "Access denied.");
      setPhase("error");
      setTimeout(() => setPhase("idle"), 3000);
    }
  };

  const isScanning = phase === "scanning";
  const isError    = phase === "error";
  const isSuccess  = phase === "success";

  return (
    <div style={{
      minHeight:"100vh", background:C.bg0,
      display:"flex", flexDirection:"column",
      alignItems:"center", justifyContent:"center",
      position:"relative", overflow:"hidden",
      fontFamily:mono,
    }}>
      {/* Grid bg */}
      <div style={{
        position:"fixed", inset:0, zIndex:0, pointerEvents:"none",
        backgroundImage:`linear-gradient(${C.line}55 1px,transparent 1px),linear-gradient(90deg,${C.line}55 1px,transparent 1px)`,
        backgroundSize:"48px 48px",
      }}/>

      {/* Ambient glow */}
      <div style={{
        position:"fixed", top:"-10%", left:"-5%", width:"50vw", height:"60vh",
        background:`radial-gradient(ellipse, ${C.accent}0d 0%, transparent 70%)`,
        pointerEvents:"none", zIndex:0,
      }}/>

      {/* Classification bars */}
      <div style={{ position:"fixed", top:0, left:0, right:0, zIndex:10, height:4, background:C.accent }}/>
      <div style={{
        position:"fixed", top:4, left:0, right:0, zIndex:10,
        padding:"5px 0", textAlign:"center", background:`${C.bg0}ee`,
        borderBottom:`1px solid ${C.line}`,
        fontSize:"8.5px", letterSpacing:4, color:C.p3, textTransform:"uppercase",
      }}>
        Sovereign AI Lab · Restricted · Authorised Access Only
      </div>
      <div style={{ position:"fixed", bottom:0, left:0, right:0, zIndex:10, height:4, background:C.accent }}/>
      <div style={{
        position:"fixed", bottom:4, left:0, right:0, zIndex:10,
        padding:"5px 0", textAlign:"center", background:`${C.bg0}ee`,
        borderTop:`1px solid ${C.line}`,
        fontSize:"8.5px", letterSpacing:3, color:C.p3, textTransform:"uppercase",
      }}>
        OpenClaw Governor v0.2.0 · Runtime Governance Platform · SOVEREIGN AI LAB Core
      </div>

      {/* Login panel */}
      <div style={{
        position:"relative", zIndex:5,
        width:"100%", maxWidth:400, margin:"0 auto", padding:"0 20px",
        opacity: mounted ? 1 : 0,
        transform: mounted ? "translateY(0)" : "translateY(16px)",
        transition:"opacity 0.6s ease, transform 0.6s ease",
      }}>
        <div style={{
          background:C.bg1,
          border:`1px solid ${isError ? C.red : isSuccess ? C.green : C.line2}`,
          borderTop:`2px solid ${isError ? C.red : isSuccess ? C.green : C.accent}`,
          transition:"border-color 0.3s",
          padding:"32px 28px", position:"relative",
        }}>
          {/* Corner accents */}
          <div style={{ position:"absolute", top:8, right:8, width:16, height:16,
            borderTop:`1px solid ${C.line2}`, borderRight:`1px solid ${C.line2}` }}/>
          <div style={{ position:"absolute", bottom:8, left:8, width:16, height:16,
            borderBottom:`1px solid ${C.line2}`, borderLeft:`1px solid ${C.line2}` }}/>

          {/* Wordmark */}
          <div style={{ textAlign:"center", marginBottom:28 }}>
            <div style={{ marginBottom:16, display:"flex", justifyContent:"center" }}>
              <ClawIcon size={54} pulse={isScanning || isSuccess}/>
            </div>
            <div style={{
              fontSize:22, fontWeight:700, letterSpacing:3,
              color: glitch ? C.accent : C.p1,
              textTransform:"uppercase",
              textShadow: glitch ? `0 0 12px ${C.accent}` : "none",
              transition:"all 0.1s", marginBottom:4,
            }}>OPENCLAW</div>
            <div style={{ fontSize:11, letterSpacing:5, color:C.p3, textTransform:"uppercase", marginBottom:8 }}>
              RUNTIME GOVERNOR
            </div>
            <div style={{
              display:"inline-block", fontSize:8, letterSpacing:2, color:C.p3,
              padding:"2px 10px", border:`1px solid ${C.line2}`, textTransform:"uppercase",
            }}>
              SOVEREIGN AI LAB
            </div>
          </div>

          {/* Divider */}
          <div style={{ borderTop:`1px solid ${C.line}`, marginBottom:22, position:"relative" }}>
            <span style={{
              position:"absolute", top:-8, left:"50%", transform:"translateX(-50%)",
              background:C.bg1, padding:"0 10px",
              fontSize:"8px", letterSpacing:2, color:C.p3, textTransform:"uppercase",
            }}>AUTHENTICATE</span>
          </div>

          {/* Error */}
          {isError && (
            <div style={{
              padding:"8px 12px", marginBottom:14,
              background:C.redDim, border:`1px solid ${C.red}`,
              fontSize:"9px", letterSpacing:1, color:C.red,
              textTransform:"uppercase", textAlign:"center",
            }}>
              ⚠ ACCESS DENIED — {errorMsg}
            </div>
          )}

          {/* Success */}
          {isSuccess && (
            <div style={{
              padding:"8px 12px", marginBottom:14,
              background:C.greenDim, border:`1px solid ${C.green}`,
              fontSize:"9px", letterSpacing:1, color:C.green,
              textTransform:"uppercase", textAlign:"center",
            }}>
              ✓ AUTHENTICATED — Loading Governor…
            </div>
          )}

          {/* Fields */}
          <div style={{ display:"flex", flexDirection:"column", gap:12, marginBottom:18 }}>
            <div style={{ display:"flex", flexDirection:"column", gap:4 }}>
              <label style={{ fontSize:"8px", letterSpacing:2, color:C.p3, textTransform:"uppercase" }}>
                Operator Email
              </label>
              <input
                type="email" value={email}
                onChange={e => setEmail(e.target.value)}
                onKeyDown={e => e.key === "Enter" && handleAuth()}
                disabled={isScanning || isSuccess}
                placeholder="operator@organisation.io"
                style={{
                  background:C.bg0, border:`1px solid ${C.line2}`,
                  borderBottom:`1px solid ${email ? C.accent : C.line2}`,
                  color:C.p1, fontFamily:mono, fontSize:11,
                  padding:"10px 12px", outline:"none", width:"100%", boxSizing:"border-box",
                  transition:"border-color 0.2s",
                }}
              />
            </div>
            <div style={{ display:"flex", flexDirection:"column", gap:4 }}>
              <label style={{ fontSize:"8px", letterSpacing:2, color:C.p3, textTransform:"uppercase" }}>
                Access Key
              </label>
              <div style={{ position:"relative" }}>
                <input
                  type={showPass ? "text" : "password"} value={password}
                  onChange={e => setPassword(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && handleAuth()}
                  disabled={isScanning || isSuccess}
                  placeholder="••••••••••••"
                  style={{
                    background:C.bg0, border:`1px solid ${C.line2}`,
                    borderBottom:`1px solid ${password ? C.accent : C.line2}`,
                    color:C.p1, fontFamily:mono, fontSize:11,
                    padding:"10px 44px 10px 12px", outline:"none",
                    width:"100%", boxSizing:"border-box",
                    transition:"border-color 0.2s",
                  }}
                />
                <button onClick={() => setShowPass(s => !s)} style={{
                  position:"absolute", right:10, top:"50%", transform:"translateY(-50%)",
                  background:"none", border:"none", cursor:"pointer",
                  fontSize:"9px", letterSpacing:1, color:C.p3, fontFamily:mono,
                }}>
                  {showPass ? "HIDE" : "SHOW"}
                </button>
              </div>
            </div>
          </div>

          {/* Scan progress */}
          {isScanning && (
            <div style={{
              marginBottom:14, padding:"10px 12px",
              background:C.bg0, border:`1px solid ${C.line2}`,
            }}>
              {SCAN_STEPS.map((step, i) => (
                <div key={i} style={{
                  display:"flex", alignItems:"center", gap:8, padding:"3px 0",
                  opacity: i < scanStep ? 1 : i === scanStep ? 0.5 : 0.15,
                  transition:"opacity 0.3s",
                }}>
                  <span style={{ fontSize:"9px", color: i < scanStep ? C.green : C.amber, width:12, textAlign:"center" }}>
                    {i < scanStep ? "✓" : i === scanStep ? "›" : "○"}
                  </span>
                  <span style={{ fontSize:"9px", letterSpacing:0.5, color: i < scanStep ? C.p2 : C.p3 }}>
                    {step}
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Button */}
          <button onClick={handleAuth}
            disabled={isScanning || isSuccess || !email || !password}
            style={{
              width:"100%", padding:"12px",
              fontFamily:mono, fontSize:11, fontWeight:700,
              letterSpacing:2, textTransform:"uppercase",
              cursor: isScanning || isSuccess || !email || !password ? "not-allowed" : "pointer",
              border:`1px solid ${isSuccess ? C.green : isError ? C.red : C.accent}`,
              color: isSuccess ? C.green : isError ? C.red : C.accent,
              background: isSuccess ? C.greenDim : isError ? C.redDim : C.accentDim,
              transition:"all 0.2s",
              opacity: !email || !password ? 0.4 : 1,
            }}>
            {isScanning ? "VERIFYING…" : isSuccess ? "✓ AUTHORISED" : isError ? "ACCESS DENIED" : "AUTHENTICATE →"}
          </button>

          {/* Footer */}
          <div style={{ marginTop:18, textAlign:"center" }}>
            <div style={{ fontSize:"8px", letterSpacing:2, color:C.p3, textTransform:"uppercase", marginBottom:6 }}>
              AUTHORISED PERSONNEL ONLY
            </div>
            <div style={{ display:"flex", justifyContent:"center", gap:10 }}>
              {["DEFAULT-DENY","AUDIT-LOGGED","SESSION-BOUND"].map(tag => (
                <span key={tag} style={{
                  fontSize:"7.5px", letterSpacing:1, color:C.p3,
                  padding:"1px 6px", border:`1px solid ${C.line}`, textTransform:"uppercase",
                }}>
                  {tag}
                </span>
              ))}
            </div>
          </div>
        </div>

        <div style={{
          marginTop:14, textAlign:"center",
          fontSize:"8.5px", letterSpacing:1.5, color:C.p3, textTransform:"uppercase",
        }}>
          All access attempts are recorded in the immutable audit trail
        </div>
      </div>

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600;700&display=swap');
        * { box-sizing: border-box; }
        input::placeholder { color: ${C.p3}; opacity: 0.6; }
      `}</style>
    </div>
  );
}

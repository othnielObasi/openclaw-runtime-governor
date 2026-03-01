"use client";
import React, { useState, useEffect, useRef } from "react";

/* ═══════════════════════════════════════════════════════════
   DESIGN TOKENS (same as main dashboard)
   ═══════════════════════════════════════════════════════════ */
const C = {
  bg0:"#080e1a", bg1:"#0e1e30", bg2:"#162840", bg3:"#1d3452",
  line:"#1a2e44", line2:"#243d58",
  p1:"#dde8f5", p2:"#7a9dbd", p3:"#3d5e7a",
  green:"#22c55e", greenDim:"rgba(34,197,94,0.10)",
  amber:"#f59e0b", amberDim:"rgba(245,158,11,0.10)",
  red:"#ef4444", redDim:"rgba(239,68,68,0.10)",
  accent:"#e8412a", accentDim:"rgba(232,65,42,0.10)",
};
const mono = "'IBM Plex Mono', monospace";
const sans = "'DM Sans', sans-serif";

/* ═══════════════════════════════════════════════════════════
   TABLE OF CONTENTS
   ═══════════════════════════════════════════════════════════ */
const TOC = [
  { id:"quick-start",     label:"Quick Start",        icon:"⚡" },
  { id:"architecture",    label:"Architecture",        icon:"◈" },
  { id:"authentication",  label:"Authentication",      icon:"🔑" },
  { id:"sdk-integration", label:"SDK Integration",     icon:"⬡" },
  { id:"dashboard",       label:"Dashboard Guide",     icon:"📊" },
  { id:"verification",    label:"Verification",        icon:"✅" },
  { id:"conversations",   label:"Conversations",       icon:"💬" },
  { id:"traces",          label:"Traces",              icon:"⧉" },
  { id:"streaming",       label:"Real-Time (SSE)",     icon:"📡" },
  { id:"policies",        label:"Policy Management",   icon:"◆" },
  { id:"chain-analysis",  label:"Chain Analysis",      icon:"⛓" },
  { id:"surge",           label:"SURGE Tokens",        icon:"💎" },
  { id:"escalation",      label:"Escalation",          icon:"🚨" },
  { id:"environment",     label:"Environment Vars",    icon:"⚙" },
  { id:"deployment",      label:"Deployment",          icon:"🚀" },
  { id:"testing",         label:"Testing",             icon:"🧪" },
  { id:"extending",       label:"Extending",           icon:"🔧" },
  { id:"troubleshooting", label:"Troubleshooting",     icon:"🩺" },
];

/* ═══════════════════════════════════════════════════════════
   REUSABLE COMPONENTS
   ═══════════════════════════════════════════════════════════ */
function Code({ children }) {
  return (
    <code style={{
      fontFamily:mono, fontSize:12.5, background:C.bg0,
      padding:"2px 7px", borderRadius:3, color:C.green,
      border:`1px solid ${C.line}`,
    }}>{children}</code>
  );
}

function CodeBlock({ children, title }) {
  const [copied,setCopied] = useState(false);
  const copy = () => { navigator.clipboard.writeText(children); setCopied(true); setTimeout(()=>setCopied(false),2000); };
  return (
    <div style={{ marginBottom:20, position:"relative" }}>
      {title && (
        <div style={{
          fontFamily:mono, fontSize:10, color:C.p3, letterSpacing:1.5,
          textTransform:"uppercase", padding:"8px 16px",
          background:C.bg1, borderBottom:`1px solid ${C.line}`,
          borderTopLeftRadius:6, borderTopRightRadius:6,
          border:`1px solid ${C.line}`, borderBottomWidth:0,
        }}>{title}</div>
      )}
      <pre style={{
        fontFamily:mono, fontSize:12.5, lineHeight:1.7,
        background:C.bg0, color:C.p2, padding:"16px 18px",
        border:`1px solid ${C.line}`, overflowX:"auto", margin:0,
        borderTopLeftRadius:title?0:6, borderTopRightRadius:title?0:6,
        borderBottomLeftRadius:6, borderBottomRightRadius:6,
      }}>{children}</pre>
      <button onClick={copy} style={{
        position:"absolute", top:title?36:8, right:10,
        fontFamily:mono, fontSize:10, letterSpacing:1,
        padding:"4px 10px", background:copied?C.greenDim:C.bg2,
        border:`1px solid ${copied?C.green:C.line2}`,
        color:copied?C.green:C.p3, cursor:"pointer",
        borderRadius:4, transition:"all 0.2s",
      }}>{copied?"✓ COPIED":"COPY"}</button>
    </div>
  );
}

function Table({ headers, rows }) {
  return (
    <div style={{ overflowX:"auto", marginBottom:20 }}>
      <table style={{ width:"100%", borderCollapse:"collapse", fontFamily:mono, fontSize:12.5 }}>
        <thead>
          <tr>
            {headers.map((h,i)=>(
              <th key={i} style={{
                textAlign:"left", padding:"10px 14px",
                borderBottom:`2px solid ${C.line2}`,
                color:C.p3, letterSpacing:1, textTransform:"uppercase",
                fontSize:10, fontWeight:600,
              }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row,ri)=>(
            <tr key={ri} style={{ background:ri%2===0?"transparent":`${C.bg1}66` }}>
              {row.map((cell,ci)=>(
                <td key={ci} style={{
                  padding:"9px 14px", borderBottom:`1px solid ${C.line}`,
                  color:ci===0?C.p1:C.p2, whiteSpace:"nowrap",
                }}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SectionHeading({ id, children }) {
  return (
    <h2 id={id} style={{
      fontFamily:mono, fontSize:20, fontWeight:700, color:C.p1,
      letterSpacing:1.5, margin:"52px 0 18px", paddingTop:20,
      borderBottom:`1px solid ${C.line}`, paddingBottom:14,
      scrollMarginTop:20,
    }}>{children}</h2>
  );
}

function SubHeading({ children }) {
  return (
    <h3 style={{
      fontFamily:mono, fontSize:15, fontWeight:600, color:C.accent,
      letterSpacing:1, margin:"28px 0 12px",
    }}>{children}</h3>
  );
}

function P({ children }) {
  return (
    <p style={{
      fontFamily:sans, fontSize:14.5, color:C.p2, lineHeight:1.75,
      margin:"0 0 16px", maxWidth:780,
    }}>{children}</p>
  );
}

function Callout({ type="info", children }) {
  const styles = {
    info:{ border:C.accent, bg:C.accentDim, icon:"ℹ" },
    warn:{ border:C.amber, bg:C.amberDim, icon:"⚠" },
    tip: { border:C.green, bg:C.greenDim, icon:"💡" },
  }[type];
  return (
    <div style={{
      padding:"14px 18px", marginBottom:20,
      background:styles.bg, borderLeft:`3px solid ${styles.border}`,
      borderRadius:4, fontFamily:sans, fontSize:13.5, color:C.p2,
      lineHeight:1.65, display:"flex", gap:10, alignItems:"flex-start",
    }}>
      <span style={{ fontSize:16, flexShrink:0 }}>{styles.icon}</span>
      <div>{children}</div>
    </div>
  );
}

function Badge({ children, color=C.p3 }) {
  return (
    <span style={{
      fontFamily:mono, fontSize:10, letterSpacing:1,
      padding:"3px 10px", border:`1px solid ${color}`,
      color, borderRadius:3, textTransform:"uppercase",
    }}>{children}</span>
  );
}

/* Pipeline diagram */
function PipelineDiagram() {
  const layers = [
    { n:1, name:"Kill Switch",       icon:"⚡", color:C.red,   desc:"Global emergency halt (DB-persisted)" },
    { n:2, name:"Injection Firewall", icon:"🛡", color:C.amber, desc:"20 regex patterns + Unicode normalisation" },
    { n:3, name:"Scope Enforcer",    icon:"🔒", color:C.amber, desc:"allowed_tools whitelist from context" },
    { n:4, name:"Policy Engine",     icon:"📋", color:C.accent,desc:"10 YAML base + dynamic DB policies" },
    { n:5, name:"Neuro + Chain",     icon:"🧠", color:C.p2,    desc:"Heuristic scoring + 11 attack patterns" },
    { n:6, name:"Verification",      icon:"✅", color:C.green,  desc:"8 post-execution checks" },
  ];
  return (
    <div style={{ display:"flex", flexWrap:"wrap", gap:0, alignItems:"stretch", margin:"20px 0 28px" }}>
      {layers.map((l,i)=>(
        <React.Fragment key={l.n}>
          {i>0 && <div style={{ display:"flex", alignItems:"center", padding:"0 2px" }}><span style={{ color:C.p3, fontSize:14 }}>→</span></div>}
          <div style={{
            background:C.bg1, border:`1px solid ${C.line}`,
            borderTop:`2px solid ${l.color}`,
            padding:"12px 14px", minWidth:120, flex:"1 1 120px",
            display:"flex", flexDirection:"column", gap:4,
          }}>
            <div style={{ fontFamily:mono, fontSize:10, color:C.p3, letterSpacing:1 }}>LAYER {l.n}</div>
            <div style={{ fontFamily:mono, fontSize:12, fontWeight:600, color:l.color }}>{l.icon} {l.name}</div>
            <div style={{ fontFamily:sans, fontSize:11, color:C.p3, lineHeight:1.4 }}>{l.desc}</div>
          </div>
        </React.Fragment>
      ))}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   DOCS TAB — embeddable inside GovernorDashboard
   ═══════════════════════════════════════════════════════════ */
export default function DocsTab() {
  const [activeSection, setActiveSection] = useState("quick-start");
  const [searchQuery, setSearchQuery] = useState("");
  const contentRef = useRef(null);

  // Intersection observer for TOC highlighting (rooted in the scrollable main container)
  useEffect(() => {
    const root = contentRef.current;
    if (!root) return;
    const observer = new IntersectionObserver(
      (entries) => { for (const entry of entries) { if (entry.isIntersecting) setActiveSection(entry.target.id); } },
      { root, rootMargin:"-20px 0px -60% 0px", threshold:0.1 }
    );
    TOC.forEach(({ id }) => { const el = document.getElementById(id); if (el) observer.observe(el); });
    return () => observer.disconnect();
  }, []);

  const filteredToc = searchQuery
    ? TOC.filter(t => t.label.toLowerCase().includes(searchQuery.toLowerCase()))
    : TOC;

  const scrollTo = (id) => {
    const el = document.getElementById(id);
    const container = contentRef.current;
    if (el && container) {
      const elRect = el.getBoundingClientRect();
      const containerRect = container.getBoundingClientRect();
      container.scrollTo({ top: container.scrollTop + elRect.top - containerRect.top - 20, behavior:"smooth" });
    }
  };

  return (
    <div style={{ display:"flex", height:"100%", minHeight:0, overflow:"hidden" }}>

      {/* ═══ LEFT SIDEBAR — TABLE OF CONTENTS (fixed) ═══ */}
      <nav style={{
        width:240, flexShrink:0,
        background:C.bg1, borderRight:`1px solid ${C.line}`,
        overflowY:"auto", padding:"16px 0",
        display:"flex", flexDirection:"column",
        height:"100%",
      }}>
        {/* Header */}
        <div style={{
          padding:"0 16px 14px",
          borderBottom:`1px solid ${C.line}`, marginBottom:10,
        }}>
          <div style={{
            fontFamily:mono, fontSize:10, color:C.accent,
            letterSpacing:3, textTransform:"uppercase", marginBottom:4,
          }}>OPENCLAW GOVERNOR</div>
          <div style={{
            fontFamily:mono, fontSize:14, fontWeight:700, color:C.p1,
            letterSpacing:2,
          }}>Documentation</div>
          <div style={{ display:"flex", gap:6, marginTop:8, flexWrap:"wrap" }}>
            <Badge color={C.green}>v0.3.0</Badge>
            <Badge color={C.green}>Python 3.12</Badge>
            <Badge color={C.amber}>PostgreSQL</Badge>
          </div>
        </div>

        {/* Search */}
        <div style={{ padding:"0 12px 12px" }}>
          <div style={{
            display:"flex", alignItems:"center", gap:8,
            padding:"7px 10px", background:C.bg0,
            border:`1px solid ${C.line}`, borderRadius:5,
          }}>
            <span style={{ color:C.p3, fontSize:12 }}>⌕</span>
            <input
              type="text"
              placeholder="Search docs…"
              value={searchQuery}
              onChange={(e)=>setSearchQuery(e.target.value)}
              style={{
                background:"transparent", border:"none", outline:"none",
                fontFamily:mono, fontSize:11.5, color:C.p1, width:"100%",
                letterSpacing:0.5,
              }}
            />
          </div>
        </div>

        {/* TOC items */}
        <div style={{ flex:1, overflowY:"auto" }}>
          {filteredToc.map((item) => {
            const active = activeSection === item.id;
            return (
              <button
                key={item.id}
                onClick={()=>scrollTo(item.id)}
                style={{
                  width:"100%", display:"flex", alignItems:"center", gap:8,
                  padding:"8px 16px", border:"none", cursor:"pointer",
                  background:active?C.accentDim:"transparent",
                  borderLeft:active?`3px solid ${C.accent}`:"3px solid transparent",
                  color:active?C.accent:C.p3,
                  fontFamily:mono, fontSize:11.5,
                  fontWeight:active?600:400, letterSpacing:0.8,
                  transition:"all 0.12s", textAlign:"left",
                }}
              >
                <span style={{ fontSize:13, width:16, textAlign:"center", flexShrink:0 }}>{item.icon}</span>
                <span>{item.label}</span>
              </button>
            );
          })}
        </div>

        {/* Bottom meta */}
        <div style={{
          padding:"12px 16px", borderTop:`1px solid ${C.line}`,
          fontFamily:mono, fontSize:10, color:C.p3, letterSpacing:1,
        }}>
          <div>246 TESTS · 17 TABLES</div>
          <div style={{ marginTop:3 }}>80 ROUTES · 16 TABS</div>
          <div style={{ marginTop:6 }}>
            <a href="https://github.com/othnielObasi/openclaw-runtime-governor"
               target="_blank" rel="noopener noreferrer"
               style={{ color:C.p3, textDecoration:"none", transition:"color 0.15s" }}
               onMouseEnter={(e)=>(e.currentTarget.style.color=C.accent)}
               onMouseLeave={(e)=>(e.currentTarget.style.color=C.p3)}>
              GITHUB →
            </a>
          </div>
        </div>
      </nav>

      {/* ═══ MAIN CONTENT ═══ */}
      <main ref={contentRef} style={{
        flex:1, padding:"32px 44px 80px", overflowY:"auto",
        height:"100%",
        maxWidth:920, animation:"fadeIn 0.4s ease-out",
      }}>

        {/* Hero */}
        <div style={{ marginBottom:44 }}>
          <div style={{
            fontFamily:mono, fontSize:10, color:C.accent,
            letterSpacing:3, textTransform:"uppercase", marginBottom:8,
          }}>OPENCLAW RUNTIME GOVERNOR</div>
          <h1 style={{
            fontFamily:mono, fontSize:28, fontWeight:700, color:C.p1,
            letterSpacing:2, margin:"0 0 14px",
          }}>Getting Started</h1>
          <P>
            A 6-layer runtime governance engine that intercepts every AI agent tool call —
            evaluating risk, enforcing policies, detecting multi-step attacks, and producing
            auditable decisions in real time. This guide walks you through setup, integration,
            and daily use.
          </P>
          <div style={{ display:"flex", gap:10, flexWrap:"wrap" }}>
            <Badge color={C.green}>Python 3.12</Badge>
            <Badge color={C.green}>FastAPI</Badge>
            <Badge color={C.green}>Next.js 14</Badge>
            <Badge color={C.amber}>PostgreSQL 16</Badge>
            <Badge color={C.accent}>SURGE</Badge>
          </div>
        </div>

        {/* ═══ SECTION: Quick Start ═══ */}
        <SectionHeading id="quick-start">Quick Start</SectionHeading>

        <SubHeading>1. Start the Backend</SubHeading>
        <CodeBlock title="Terminal">{`cd governor-service
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000`}</CodeBlock>
        <P>
          On first startup the server automatically creates all 17 database tables (SQLite at <Code>./governor.db</Code>),
          seeds a default admin account (<Code>admin / changeme</Code>), and loads 10 base governance policies.
        </P>

        <SubHeading>2. Start the Dashboard</SubHeading>
        <CodeBlock title="Terminal">{`cd dashboard
npm install
NEXT_PUBLIC_GOVERNOR_API=http://localhost:8000 npm run dev`}</CodeBlock>
        <P>
          Open <Code>http://localhost:3000</Code> — choose <strong style={{ color:C.green }}>Live Mode</strong> to
          connect to the backend or <strong style={{ color:C.amber }}>Demo Mode</strong> for a self-contained preview.
        </P>

        <SubHeading>3. Your First Evaluation</SubHeading>
        <CodeBlock title="bash">{`# Get a JWT token
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \\
  -H "Content-Type: application/json" \\
  -d '{"username":"admin","password":"changeme"}' | jq -r .access_token)

# Ask the Governor: "Can this agent run rm -rf /?"
curl -s -X POST http://localhost:8000/actions/evaluate \\
  -H "Authorization: Bearer $TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{
    "tool": "shell",
    "args": {"command": "rm -rf /"},
    "context": {"agent_id": "my-agent"}
  }' | jq .`}</CodeBlock>

        <Callout type="tip">
          <strong>Response:</strong> <Code>decision: "block"</Code>, <Code>risk_score: 95</Code>,
          <Code>explanation: "Destructive filesystem operation"</Code>
        </Callout>

        <SubHeading>4. Run the Demo Agent</SubHeading>
        <CodeBlock title="Terminal">{`python demo_agent.py              # 17 evaluations + 8 verifications
python demo_agent.py --verbose    # detailed trace per evaluation
python demo_agent.py --fee-gating # enable SURGE fee depletion`}</CodeBlock>
        <P>
          The demo agent runs 17 tool calls across 5 phases (safe → dangerous), plus 8 verification
          scenarios — producing traces, SURGE receipts, conversation turns, and audit logs.
        </P>

        {/* ═══ SECTION: Architecture ═══ */}
        <SectionHeading id="architecture">Architecture</SectionHeading>

        <SubHeading>The 6-Layer Governance Pipeline</SubHeading>
        <P>
          Every tool call passes through 6 evaluation layers that short-circuit on the first block.
          Each layer emits a <Code>TraceStep</Code> with timing, risk contribution, and detail text — making
          every decision fully explainable.
        </P>
        <PipelineDiagram />

        <SubHeading>Decision Types</SubHeading>
        <Table
          headers={["Decision","Meaning","Agent Should"]}
          rows={[
            ["allow","Tool call is safe","Proceed with execution"],
            ["review","Needs human review","Queue for approval or skip"],
            ["block","Dangerous — rejected","Do NOT execute the tool"],
          ]}
        />

        <SubHeading>Database — 17 Tables</SubHeading>
        <Table
          headers={["Table","Purpose"]}
          rows={[
            ["action_logs","Every evaluation (tool, args, decision, risk, chain_pattern)"],
            ["policy_models","Dynamic policies created via API"],
            ["users","RBAC accounts (superadmin / admin / operator / auditor)"],
            ["governor_state","Key-value store (kill switch state)"],
            ["conversation_turns","Agent conversation turns (encrypted at rest)"],
            ["verification_logs","Post-execution verification results (8 checks)"],
            ["trace_spans","Agent lifecycle trace spans"],
            ["surge_receipts","SHA-256 governance attestation receipts"],
            ["surge_wallets","Virtual $SURGE agent wallets"],
            ["surge_staked_policies","$SURGE staked on policies"],
            ["escalation_events","Review queue (pending → approve / reject)"],
            ["escalation_config","Per-agent escalation thresholds"],
            ["escalation_webhooks","Webhook URLs for escalation"],
            ["notification_channels","Multi-channel notification config"],
            ["policy_versions","Immutable policy version snapshots"],
            ["policy_audit_log","Before/after diffs for policy changes"],
            ["login_history","Auth events with IP + user-agent"],
          ]}
        />

        {/* ═══ SECTION: Authentication ═══ */}
        <SectionHeading id="authentication">Authentication &amp; Access Control</SectionHeading>

        <SubHeading>Auth Methods</SubHeading>
        <Table
          headers={["Method","Header / Param","How to Obtain"]}
          rows={[
            ["JWT Bearer","Authorization: Bearer <token>","POST /auth/login"],
            ["API Key","X-API-Key: ocg_<key>","Dashboard API Keys tab or POST /auth/me/rotate-key"],
            ["Query Param","?token=<jwt>","For SSE / EventSource (can't set headers)"],
          ]}
        />

        <SubHeading>Getting a Token</SubHeading>
        <CodeBlock title="bash">{`TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \\
  -H "Content-Type: application/json" \\
  -d '{"username":"admin","password":"changeme"}' | jq -r .access_token)`}</CodeBlock>

        <SubHeading>Role-Based Access Control (RBAC)</SubHeading>
        <Table
          headers={["Role","Evaluate","View Logs","Policies","Kill Switch","Verify","Users"]}
          rows={[
            ["superadmin","✅","✅","✅ CRUD","✅","✅","✅ CRUD"],
            ["admin",     "✅","✅","✅ CRUD","✅","✅","✅ CRUD"],
            ["operator",  "✅","✅","✅ CRUD","—", "✅","—"],
            ["auditor",   "—", "✅","Read",   "—", "—", "—"],
          ]}
        />

        <Callout type="warn">
          <strong>Change the defaults before any deployment.</strong> The server refuses to start in
          <Code>production</Code> mode with the default JWT secret.
        </Callout>

        {/* ═══ SECTION: SDK Integration ═══ */}
        <SectionHeading id="sdk-integration">SDK Integration</SectionHeading>

        <P>
          Three official SDKs — authenticate with <Code>X-API-Key</Code>, auto-throw on <Code>block</Code> decisions.
        </P>

        <SubHeading>Python · pip install openclaw-governor-client</SubHeading>
        <CodeBlock title="python">{`import governor_client
from governor_client import evaluate_action, GovernorBlockedError

governor_client.GOVERNOR_URL = "https://openclaw-governor.fly.dev"
governor_client.GOVERNOR_API_KEY = "ocg_your_key_here"

try:
    decision = evaluate_action("shell", {"command": "ls -la"}, context={
        "agent_id": "my-agent",
        "session_id": "session-123",
        "allowed_tools": ["shell", "http_request", "file_read"],
    })
    print(f"{decision['decision']} — risk {decision['risk_score']}")
except GovernorBlockedError as e:
    print(f"Blocked: {e}")  # Do NOT execute`}</CodeBlock>

        <SubHeading>TypeScript · npm install @openclaw/governor-client</SubHeading>
        <CodeBlock title="typescript">{`import { GovernorClient, GovernorBlockedError } from "@openclaw/governor-client";

const gov = new GovernorClient({
  baseUrl: "https://openclaw-governor.fly.dev",
  apiKey: "ocg_your_key_here",
});

try {
  const d = await gov.evaluate("shell", { command: "ls -la" }, {
    agent_id: "my-agent",
    allowed_tools: ["shell", "http_request"],
  });
  console.log(\`\${d.decision} — risk \${d.risk_score}\`);
} catch (err) {
  if (err instanceof GovernorBlockedError) {
    console.error("Blocked:", err.message);
  }
}`}</CodeBlock>

        <SubHeading>Java · dev.openclaw:governor-client:0.3.0</SubHeading>
        <CodeBlock title="java">{`GovernorClient gov = new GovernorClient.Builder()
    .baseUrl("https://openclaw-governor.fly.dev")
    .apiKey("ocg_your_key_here")
    .build();

try {
    GovernorDecision d = gov.evaluate("shell", Map.of("command", "ls -la"));
    System.out.println(d.getDecision() + " — risk " + d.getRiskScore());
} catch (GovernorBlockedError e) {
    System.err.println("Blocked: " + e.getMessage());
}`}</CodeBlock>

        <SubHeading>Direct HTTP (No SDK)</SubHeading>
        <CodeBlock title="bash">{`curl -s -X POST https://openclaw-governor.fly.dev/actions/evaluate \\
  -H "X-API-Key: ocg_your_key_here" \\
  -H "Content-Type: application/json" \\
  -d '{
    "tool": "http_request",
    "args": {"method": "POST", "url": "https://api.example.com/data"},
    "context": {"agent_id": "data-agent", "allowed_tools": ["http_request"]}
  }' | jq .`}</CodeBlock>

        <SubHeading>Context Fields</SubHeading>
        <Table
          headers={["Field","Type","Purpose"]}
          rows={[
            ["agent_id","string","Identifies the agent for chain analysis and filtering"],
            ["session_id","string","Groups related tool calls into a session (60-min chain window)"],
            ["allowed_tools","string[]","Layer 3 blocks any tool not in this list"],
            ["trace_id","string","Links evaluation to an agent trace tree"],
            ["conversation_id","string","Links to a conversation for conversation logging"],
            ["prompt","string","(opt-in) Agent reasoning — encrypted at rest"],
          ]}
        />

        {/* ═══ SECTION: Dashboard ═══ */}
        <SectionHeading id="dashboard">Dashboard Guide</SectionHeading>

        <P>
          The dashboard has <strong style={{ color:C.p1 }}>16 tabs</strong>, each accessible based on your role.
        </P>

        <Table
          headers={["Tab","Icon","What It Shows"]}
          rows={[
            ["Dashboard",     "◈", "Summary: evaluations, allow/review/block counts, risk distribution"],
            ["Agent Demo",    "🤖","Run the 17-step demo agent from the browser"],
            ["Action Tester", "▶", "Manual tool evaluation — test any tool / args / context"],
            ["Policy Editor", "◆", "CRUD for dynamic policies with active/inactive toggle"],
            ["Review Queue",  "◎", "Pending escalation events — approve / reject actions"],
            ["SURGE",         "⬡", "Receipts, fee tiers, wallet balances, policy staking"],
            ["Audit Trail",   "☰", "Full action history + live SSE merge (LIVE badge)"],
            ["Conversations", "💬","Agent conversation turns + unified timeline"],
            ["Verification",  "✅","Post-execution verification logs (8 checks)"],
            ["Drift Detection","📈","Per-agent drift scores and trends"],
            ["Chain Analysis","⛓", "Detected multi-step attack patterns (dynamic chart)"],
            ["Traces",        "⧉", "Span tree explorer — governance correlation"],
            ["Topology",      "◎", "Agent-to-tool interaction graph"],
            ["API Keys",      "🔑","View / copy / regenerate API key + code samples"],
            ["Settings",      "⚙", "Kill switch, escalation thresholds, notification channels"],
            ["Users",         "👥","User management — create operators and auditors"],
          ]}
        />

        <Callout type="info">
          <strong>Demo vs Live:</strong> Demo Mode is fully self-contained — no backend needed.
          Live Mode connects via <Code>NEXT_PUBLIC_GOVERNOR_API</Code>.
        </Callout>

        {/* ═══ SECTION: Verification ═══ */}
        <SectionHeading id="verification">Post-Execution Verification</SectionHeading>

        <P>
          The verification engine inspects tool <em>results</em> after execution — closing the gap between
          allowing an intent and validating the outcome.
        </P>

        <SubHeading>8 Verification Checks</SubHeading>
        <Table
          headers={["Check","What It Does"]}
          rows={[
            ["credential-scan","Scans output/diff for API keys, tokens, passwords, secrets"],
            ["destructive-output","Detects SQL drops, file deletions, dangerous patterns"],
            ["scope-compliance","Verifies result is consistent with allowed scope"],
            ["diff-size","Flags unexpectedly large changes (anomaly detection)"],
            ["intent-alignment","Catches agents executing BLOCKED actions (policy bypass)"],
            ["output-injection","Scans output for prompt injection patterns"],
            ["independent-reverify","Re-runs the full policy engine against output text"],
            ["drift-detection","Compares behavior against historical baselines"],
          ]}
        />

        <SubHeading>Submit a Verification</SubHeading>
        <CodeBlock title="bash">{`curl -s -X POST http://localhost:8000/actions/verify \\
  -H "Authorization: Bearer $TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{
    "action_id": 42,
    "tool": "file_write",
    "result": {
      "status": "success",
      "output": "Wrote 150 lines to config.py"
    },
    "context": {"agent_id": "my-agent"}
  }' | jq .`}</CodeBlock>

        <Table
          headers={["Verdict","Meaning"]}
          rows={[
            ["compliant","All 8 checks passed"],
            ["suspicious","Some flags — below violation threshold"],
            ["violation","Critical failure — auto-escalated"],
          ]}
        />

        {/* ═══ SECTION: Conversations ═══ */}
        <SectionHeading id="conversations">Conversation Logging</SectionHeading>

        <P>
          Opt-in capture of agent reasoning and prompts. All content is <strong style={{ color:C.amber }}>encrypted at rest</strong> with
          Fernet symmetric encryption.
        </P>

        <SubHeading>Include Context in Evaluations</SubHeading>
        <CodeBlock title="python">{`decision = evaluate_action("shell", {"command": "ls"}, context={
    "agent_id": "my-agent",
    "conversation_id": "conv-abc-123",
    "turn_id": 1,
    "prompt": "User asked me to list directory contents"
})`}</CodeBlock>

        <SubHeading>Batch Ingest Turns</SubHeading>
        <CodeBlock title="bash">{`curl -s -X POST http://localhost:8000/conversations/turns/batch \\
  -H "Authorization: Bearer $TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '[
    {"conversation_id":"conv-123","turn_number":1,"role":"user","content":"List /tmp"},
    {"conversation_id":"conv-123","turn_number":2,"role":"assistant","content":"Running shell tool"}
  ]' | jq .`}</CodeBlock>

        {/* ═══ SECTION: Traces ═══ */}
        <SectionHeading id="traces">Agent Trace Observability</SectionHeading>

        <P>
          Capture the full lifecycle of every agent task — LLM reasoning, tool invocations, retrieval steps,
          and governance decisions as an OpenTelemetry-inspired span tree.
        </P>

        <SubHeading>Ingest Trace Spans</SubHeading>
        <CodeBlock title="bash">{`curl -s -X POST http://localhost:8000/traces/ingest \\
  -H "Authorization: Bearer $TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{
    "spans": [
      {"trace_id":"t-001","span_id":"root","name":"Research Task","kind":"agent",
       "start_time":"2026-02-28T12:00:00Z","end_time":"2026-02-28T12:00:05Z"},
      {"trace_id":"t-001","span_id":"llm-1","parent_span_id":"root",
       "name":"GPT-4 reasoning","kind":"llm",
       "start_time":"2026-02-28T12:00:01Z","end_time":"2026-02-28T12:00:03Z"}
    ]
  }' | jq .`}</CodeBlock>

        <SubHeading>Span Kinds</SubHeading>
        <Table
          headers={["Kind","Color","Represents"]}
          rows={[
            ["agent","Red","Root agent task / orchestration"],
            ["llm","Violet","LLM inference call"],
            ["tool","Amber","Tool invocation"],
            ["governance","Red","Governor evaluation (auto-created)"],
            ["retrieval","Cyan","RAG / vector search"],
            ["chain","Green","Multi-step chain execution"],
          ]}
        />

        <Callout type="tip">
          Pass <Code>trace_id</Code> and <Code>span_id</Code> in the evaluation context — the Governor
          auto-creates a <Code>governance</Code> span as a child. Zero config required.
        </Callout>

        {/* ═══ SECTION: Streaming ═══ */}
        <SectionHeading id="streaming">Real-Time Streaming (SSE)</SectionHeading>

        <P>
          The Governor pushes every governance decision to connected clients via Server-Sent Events.
          The dashboard auto-connects in Live Mode — a <strong style={{ color:C.green }}>LIVE</strong> badge
          indicates an active stream.
        </P>

        <SubHeading>Connect to the Stream</SubHeading>
        <CodeBlock title="bash">{`# Terminal
curl -N -H "Authorization: Bearer $TOKEN" \\
  http://localhost:8000/actions/stream

# JavaScript
const es = new EventSource(
  "https://openclaw-governor.fly.dev/actions/stream?token=" + jwt
);
es.addEventListener("action_evaluated", (e) => {
  const { tool, decision, risk_score } = JSON.parse(e.data);
  console.log(\`\${tool}: \${decision} (risk \${risk_score})\`);
});`}</CodeBlock>

        <Table
          headers={["Event","When"]}
          rows={[
            ["connected","On initial connection"],
            ["action_evaluated","After every POST /actions/evaluate"],
            [":heartbeat","Every 15 seconds (keep-alive)"],
          ]}
        />

        {/* ═══ SECTION: Policies ═══ */}
        <SectionHeading id="policies">Policy Management</SectionHeading>

        <SubHeading>Base Policies (YAML)</SubHeading>
        <P>
          10 policies ship with the Governor in <Code>app/policies/base_policies.yml</Code> — version-controlled
          and loaded on startup.
        </P>
        <CodeBlock title="yaml">{`- policy_id: shell-dangerous
  description: "Block destructive shell commands"
  tool: "shell"
  severity: critical
  action: block
  args_regex: "(rm\\\\s+-rf|mkfs|dd\\\\s+if=|shutdown|reboot)"`}</CodeBlock>

        <SubHeading>Dynamic Policies (API)</SubHeading>
        <CodeBlock title="bash">{`# Create a policy
curl -s -X POST http://localhost:8000/policies \\
  -H "Authorization: Bearer $TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{
    "policy_id": "block-external-uploads",
    "description": "Block HTTP uploads to external domains",
    "tool": "http_request",
    "severity": "high",
    "action": "block",
    "url_regex": "^https?://(?!internal\\\\.company\\\\.com)"
  }' | jq .

# Toggle on/off
curl -s -X PATCH http://localhost:8000/policies/block-external-uploads/toggle \\
  -H "Authorization: Bearer $TOKEN" | jq .`}</CodeBlock>

        <Callout type="info">
          Every edit creates an immutable <Code>PolicyVersion</Code> snapshot + <Code>PolicyAuditLog</Code> with
          JSON diffs. Restore any previous version via the API.
        </Callout>

        {/* ═══ SECTION: Chain Analysis ═══ */}
        <SectionHeading id="chain-analysis">Chain Analysis — 11 Patterns</SectionHeading>

        <P>
          The Governor detects multi-step attack patterns by examining session history (60-minute window,
          max 50 actions). The first matching pattern is stored in <Code>chain_pattern</Code>.
        </P>

        <Table
          headers={["Pattern","Risk Boost","What It Catches"]}
          rows={[
            ["repeated-scope-probing","+60","Agent probes tools outside its scope"],
            ["multi-cred-harvest","+60","Multiple credential-related tool calls"],
            ["credential-then-http","+55","Credential access → network request (exfiltration)"],
            ["privilege-escalation","+50","Sudo/admin → system changes"],
            ["read-write-exec","+45","File read → write → shell (lateral movement)"],
            ["delayed-exfil","+45","Long gap between data access and exfiltration"],
            ["block-bypass-retry","+40","Retrying blocked actions with variations"],
            ["data-staging","+40","Multiple file reads → network send"],
            ["browse-then-exfil","+35","HTTP browse → messaging send"],
            ["env-recon","+35","Environment probing → writes"],
            ["rapid-tool-switching","+30","5+ distinct tools in quick succession"],
          ]}
        />

        {/* ═══ SECTION: SURGE ═══ */}
        <SectionHeading id="surge">SURGE Token Governance</SectionHeading>

        <P>
          Economically-backed governance layer — all data DB-persisted. SHA-256 signed receipts,
          tiered fees, virtual wallets, and policy staking.
        </P>

        <SubHeading>Fee Tiers</SubHeading>
        <Table
          headers={["Risk Score","Fee"]}
          rows={[
            ["0–39 (standard)","0.001 $SURGE"],
            ["40–69 (elevated)","0.005 $SURGE"],
            ["70–89 (high)","0.010 $SURGE"],
            ["90–100 (critical)","0.025 $SURGE"],
          ]}
        />

        <P>
          Wallets are auto-provisioned on first call (100 $SURGE). When a wallet is depleted, the API returns
          <Code>402 Payment Required</Code>.
        </P>

        {/* ═══ SECTION: Escalation ═══ */}
        <SectionHeading id="escalation">Escalation &amp; Alerting</SectionHeading>

        <P>
          Automated escalation engine with 5 notification channels: <strong>Email</strong>, <strong>Slack</strong>,
          <strong> WhatsApp</strong>, <strong>Jira</strong>, and <strong>generic Webhooks</strong>.
        </P>

        <SubHeading>Auto-Kill-Switch Triggers</SubHeading>
        <Callout type="warn">
          The escalation engine auto-engages the kill switch when:
          <br />• <strong>3+ blocks</strong> in recent evaluations
          <br />• <strong>Average risk ≥ 82</strong> in last 10 actions
        </Callout>

        <SubHeading>Configure Notifications</SubHeading>
        <CodeBlock title="bash">{`curl -s -X POST http://localhost:8000/notifications/channels \\
  -H "Authorization: Bearer $TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{
    "name": "security-alerts",
    "channel_type": "slack",
    "config_json": {"webhook_url": "https://hooks.slack.com/services/T.../B.../..."},
    "is_active": true
  }' | jq .`}</CodeBlock>

        {/* ═══ SECTION: Environment ═══ */}
        <SectionHeading id="environment">Environment Variables</SectionHeading>

        <SubHeading>Governor Service</SubHeading>
        <Table
          headers={["Variable","Default","Description"]}
          rows={[
            ["GOVERNOR_DATABASE_URL","sqlite:///./governor.db","Database URL (postgresql:// in prod)"],
            ["GOVERNOR_JWT_SECRET","(must set in prod)","JWT HS256 signing secret"],
            ["GOVERNOR_ENVIRONMENT","development","development or production"],
            ["GOVERNOR_LOG_LEVEL","info","debug, info, warning, error"],
            ["GOVERNOR_ALLOW_CORS_ORIGINS",'[\"*\"]',"CORS allowed origins (JSON array)"],
            ["GOVERNOR_ENCRYPTION_KEY","(auto-generated)","Fernet key for conversation encryption"],
            ["GOVERNOR_POLICIES_PATH","app/policies/base_policies.yml","Base policy YAML path"],
            ["GOVERNOR_POLICY_CACHE_TTL_SECONDS","10","Policy cache TTL (0 to disable)"],
            ["GOVERNOR_ADMIN_USERNAME","admin","Seed admin username"],
            ["GOVERNOR_ADMIN_PASSWORD","changeme","Seed admin password"],
            ["GOVERNOR_SURGE_GOVERNANCE_FEE_ENABLED","false","Enable $SURGE micro-fees"],
            ["GOVERNOR_SURGE_WALLET_ADDRESS","(empty)","SURGE wallet for fee collection"],
          ]}
        />

        <SubHeading>Dashboard</SubHeading>
        <Table
          headers={["Variable","Default","Description"]}
          rows={[
            ["NEXT_PUBLIC_GOVERNOR_API","http://localhost:8000","Governor service URL (build-time)"],
          ]}
        />

        {/* ═══ SECTION: Deployment ═══ */}
        <SectionHeading id="deployment">Deployment</SectionHeading>

        <SubHeading>Live Deployments</SubHeading>
        <Table
          headers={["Component","Platform","URL"]}
          rows={[
            ["Backend (primary)","Fly.io","openclaw-governor.fly.dev"],
            ["Backend (standby)","Vultr VPS","45.76.141.204:8000"],
            ["Dashboard (primary)","Vercel","openclaw-runtime-governor.vercel.app"],
            ["Dashboard (mirror)","Vercel","openclaw-runtime-governor-j9py.vercel.app"],
            ["Dashboard (standby)","Vultr VPS","45.76.141.204:3000"],
          ]}
        />

        <SubHeading>Deploy to Fly.io</SubHeading>
        <CodeBlock title="Terminal">{`cd governor-service
fly deploy

fly secrets set GOVERNOR_JWT_SECRET="your-long-random-secret"
fly secrets set GOVERNOR_ADMIN_PASSWORD="your-secure-password"
fly secrets set GOVERNOR_DATABASE_URL="postgresql://..."
fly secrets set GOVERNOR_ENVIRONMENT="production"`}</CodeBlock>

        <SubHeading>Deploy to Vultr (Docker Compose)</SubHeading>
        <CodeBlock title="Terminal">{`git clone https://github.com/othnielObasi/openclaw-runtime-governor.git
cd openclaw-runtime-governor/governor-service/vultr
cp .env.vultr.example .env
nano .env                    # fill in real secrets
docker compose up -d`}</CodeBlock>

        <SubHeading>Deploy Dashboard to Vercel</SubHeading>
        <P>
          Import the repo → set root directory to <Code>dashboard</Code> → set env var
          <Code>NEXT_PUBLIC_GOVERNOR_API</Code> → deploy.
        </P>

        {/* ═══ SECTION: Testing ═══ */}
        <SectionHeading id="testing">Testing</SectionHeading>

        <CodeBlock title="Terminal">{`cd governor-service
pytest tests/ -v          # 246 tests across 8 files`}</CodeBlock>

        <Table
          headers={["File","Coverage"]}
          rows={[
            ["test_governor.py","Pipeline: decisions, firewall, scope, kill switch, neuro, chain, SURGE"],
            ["test_conversations.py","Conversation logging: turns, batch ingest, timeline, encryption"],
            ["test_escalation.py","Escalation engine: review queue, auto-kill-switch, thresholds"],
            ["test_policies.py","Policy CRUD: create, update, toggle, regex validation"],
            ["test_stream.py","SSE streaming: event bus, subscribers, auth, heartbeat"],
            ["test_traces.py","Trace observability: ingest, tree, governance correlation"],
            ["test_verification.py","Post-execution: 8 checks, intent-alignment, drift"],
            ["test_versioning.py","Policy versioning + notification channels (5 types)"],
          ]}
        />

        <SubHeading>Writing a Test</SubHeading>
        <CodeBlock title="python">{`from app.schemas import ActionInput
from app.policies.engine import evaluate_action

def test_my_scenario():
    inp = ActionInput(
        tool="shell",
        args={"command": "echo hello"},
        context={"agent_id": "test-agent"}
    )
    result = evaluate_action(inp)
    assert result.decision == "allow"
    assert result.risk_score < 50`}</CodeBlock>

        {/* ═══ SECTION: Extending ═══ */}
        <SectionHeading id="extending">Extending the Governor</SectionHeading>

        <SubHeading>Add a Pipeline Layer</SubHeading>
        <P>
          Implement your check in <Code>app/</Code>, hook it into <Code>evaluate_action()</Code>
          in <Code>app/policies/engine.py</Code>, and emit a <Code>TraceStep</Code>.
        </P>
        <CodeBlock title="python">{`trace.append(TraceStep(
    layer=7,
    name="my_new_layer",
    key="my-check",
    outcome="pass",            # pass | block | review
    risk_contribution=0,
    matched_ids=[],
    detail="No issues found",
    duration_ms=round(elapsed * 1000, 2),
))`}</CodeBlock>

        <SubHeading>Add a Dashboard Tab</SubHeading>
        <P>
          Use inline styles with the project design tokens. Import <Code>ApiClient</Code> for API calls and
          <Code>useAuth()</Code> for auth context.
        </P>
        <CodeBlock title="javascript">{`// Design tokens
const C = {
  bg0: "#080e1a", bg1: "#0f1b2d", bg2: "#1d3452",
  p1: "#e2e8f0", p2: "#8fa3bf", p3: "#4a6785",
  accent: "#e8412a", green: "#22c55e", amber: "#f59e0b", red: "#ef4444",
};
const mono = "'IBM Plex Mono', monospace";
const sans = "'DM Sans', sans-serif";`}</CodeBlock>

        {/* ═══ SECTION: Troubleshooting ═══ */}
        <SectionHeading id="troubleshooting">Troubleshooting</SectionHeading>

        <Table
          headers={["Problem","Solution"]}
          rows={[
            ["\"JWT secret must be changed\"","Set GOVERNOR_JWT_SECRET to a long random string (production mode only)"],
            ["Dashboard says \"API is not set\"","Set NEXT_PUBLIC_GOVERNOR_API before build: NEXT_PUBLIC_GOVERNOR_API=... npm run build"],
            ["Policy changes not taking effect","Wait 10s for cache TTL or set GOVERNOR_POLICY_CACHE_TTL_SECONDS=0"],
            ["Kill switch won't release","POST /admin/resume with admin token"],
            ["SQLite \"database is locked\"","Switch to PostgreSQL: GOVERNOR_DATABASE_URL=postgresql://..."],
            ["CORS errors","Set GOVERNOR_ALLOW_CORS_ORIGINS='[\"https://your-dashboard.vercel.app\"]'"],
            ["SSE stream disconnects","15s heartbeat keeps alive. Check proxy timeouts. Dashboard auto-reconnects."],
            ["Vultr data not persisting","Ensure GOVERNOR_DATABASE_URL is set. Use docker compose (not raw docker run)."],
            ["Demo agent all blocks","Check if kill switch is engaged: GET /admin/status. Resume if needed."],
          ]}
        />

        {/* Footer */}
        <div style={{
          marginTop:64, paddingTop:32,
          borderTop:`1px solid ${C.line}`,
          display:"flex", justifyContent:"space-between", alignItems:"center",
          flexWrap:"wrap", gap:16,
        }}>
          <div style={{ fontFamily:mono, fontSize:11, color:C.p3, letterSpacing:1 }}>
            © 2026 SOVEREIGN AI LAB · MIT LICENSE
          </div>
          <a
            href="https://github.com/othnielObasi/openclaw-runtime-governor"
            target="_blank" rel="noopener noreferrer"
            style={{ fontFamily:mono, fontSize:11, color:C.p3, textDecoration:"none", letterSpacing:1, transition:"color 0.15s" }}
            onMouseEnter={(e)=>(e.currentTarget.style.color=C.accent)}
            onMouseLeave={(e)=>(e.currentTarget.style.color=C.p3)}
          >GITHUB →</a>
        </div>
      </main>
    </div>
  );
}

"use client";

import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./AuthContext";

const C = {
  bg0:"#080e1a", bg1:"#0e1e30", bg2:"#162840", bg3:"#1d3452",
  line:"#1a2e44", line2:"#243d58",
  p1:"#dde8f5", p2:"#7a9dbd", p3:"#3d5e7a",
  green:"#22c55e", greenDim:"rgba(34,197,94,0.10)",
  amber:"#f59e0b", amberDim:"rgba(245,158,11,0.10)",
  red:"#ef4444",   redDim:"rgba(239,68,68,0.10)",
  accent:"#e8412a", accentDim:"rgba(232,65,42,0.12)",
};
const mono = "'IBM Plex Mono','Courier New',monospace";
const sans = "'DM Sans',system-ui,sans-serif";
const API  = process.env.NEXT_PUBLIC_GOVERNOR_API;
if (!API) {
  console.warn('NEXT_PUBLIC_GOVERNOR_API is not set; requests may fail');
}

interface User {
  id: number;
  email: string;
  name: string;
  role: string;
  is_active: boolean;
  api_key?: string;
  created_at: string;
}

const ROLE_COLOR: Record<string, string> = {
  admin:    C.accent,
  operator: C.amber,
  auditor:  C.p2,
};

function Badge({ children, color }: { children: string; color: string }) {
  return (
    <span style={{
      fontFamily:mono, fontSize:8, letterSpacing:1.5,
      padding:"2px 8px", border:`1px solid ${color}`,
      color, textTransform:"uppercase",
    }}>{children}</span>
  );
}

function Btn({
  children, onClick, variant = "default", disabled = false, small = false,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  variant?: "default"|"red"|"green"|"amber"|"accent";
  disabled?: boolean;
  small?: boolean;
}) {
  const styles: Record<string, React.CSSProperties> = {
    default: { border:`1px solid ${C.line2}`,  color:C.p3,    background:"transparent" },
    red:     { border:`1px solid ${C.red}`,    color:C.red,   background:C.redDim },
    green:   { border:`1px solid ${C.green}`,  color:C.green, background:C.greenDim },
    amber:   { border:`1px solid ${C.amber}`,  color:C.amber, background:C.amberDim },
    accent:  { border:`1px solid ${C.accent}`, color:C.accent, background:C.accentDim },
  };
  return (
    <button onClick={onClick} disabled={disabled} style={{
      fontFamily:mono, fontSize: small ? 8 : 9,
      letterSpacing:1, textTransform:"uppercase",
      padding: small ? "3px 10px" : "6px 14px",
      cursor: disabled ? "not-allowed" : "pointer",
      opacity: disabled ? 0.4 : 1,
      transition:"all 0.15s",
      ...styles[variant],
    }}>{children}</button>
  );
}

function Fld({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display:"flex", flexDirection:"column", gap:4 }}>
      <label style={{ fontFamily:mono, fontSize:"8px", letterSpacing:2, color:C.p3, textTransform:"uppercase" }}>
        {label}
      </label>
      {children}
    </div>
  );
}

function Input({ value, onChange, placeholder, type = "text" }: {
  value: string; onChange: (v: string) => void;
  placeholder?: string; type?: string;
}) {
  return (
    <input type={type} value={value} placeholder={placeholder}
      onChange={e => onChange(e.target.value)}
      style={{
        background:C.bg0, border:`1px solid ${C.line2}`, color:C.p1,
        fontFamily:mono, fontSize:10, padding:"7px 10px",
        outline:"none", width:"100%", boxSizing:"border-box" as const,
      }}/>
  );
}

export default function UserManagement() {
  const { token } = useAuth();
  const [users, setUsers]       = useState<User[]>([]);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState("");
  const [pendingRevoke, setPendingRevoke] = useState<number | null>(null);
  const [showCreate, setShowCreate]       = useState(false);
  const [creating, setCreating]           = useState(false);
  const [createErr, setCreateErr]         = useState("");
  const [form, setForm] = useState({ email:"", name:"", password:"", role:"operator" });

  const authHeaders = { Authorization: `Bearer ${token}`, "Content-Type":"application/json" };

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/auth/users`, { headers: authHeaders });
      if (!res.ok) throw new Error("Failed to load users.");
      setUsers(await res.json());
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { fetchUsers(); }, [fetchUsers]);

  const handleRevoke = async (id: number) => {
    if (pendingRevoke !== id) { setPendingRevoke(id); setTimeout(() => setPendingRevoke(null), 4000); return; }
    await fetch(`${API}/auth/users/${id}`, { method:"DELETE", headers: authHeaders });
    setPendingRevoke(null);
    fetchUsers();
  };

  const handleRestore = async (id: number) => {
    await fetch(`${API}/auth/users/${id}`, {
      method:"PATCH", headers: authHeaders,
      body: JSON.stringify({ is_active: true }),
    });
    fetchUsers();
  };

  const handleRotateKey = async (id: number) => {
    await fetch(`${API}/auth/users/${id}/rotate-key`, { method:"POST", headers: authHeaders });
    fetchUsers();
  };

  const handleCreate = async () => {
    if (!form.email || !form.name || !form.password) { setCreateErr("All fields required."); return; }
    setCreating(true); setCreateErr("");
    try {
      const res = await fetch(`${API}/auth/users`, {
        method:"POST", headers: authHeaders,
        body: JSON.stringify(form),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to create user.");
      }
      setForm({ email:"", name:"", password:"", role:"operator" });
      setShowCreate(false);
      fetchUsers();
    } catch (e: any) {
      setCreateErr(e.message);
    } finally {
      setCreating(false);
    }
  };

  const active   = users.filter(u => u.is_active);
  const inactive = users.filter(u => !u.is_active);

  return (
    <div style={{ padding:20, fontFamily:mono }}>

      {/* Header */}
      <div style={{
        display:"flex", alignItems:"center", justifyContent:"space-between",
        marginBottom:20, paddingBottom:14, borderBottom:`1px solid ${C.line2}`,
      }}>
        <div>
          <div style={{ fontSize:13, fontWeight:700, color:C.p1, letterSpacing:1 }}>
            User Management
          </div>
          <div style={{ fontSize:9, color:C.p3, marginTop:3, letterSpacing:1 }}>
            {active.length} active · {inactive.length} revoked · admin access only
          </div>
        </div>
        <Btn variant="accent" onClick={() => setShowCreate(s => !s)}>
          {showCreate ? "✕ CANCEL" : "+ ADD OPERATOR"}
        </Btn>
      </div>

      {/* Create form */}
      {showCreate && (
        <div style={{
          padding:16, marginBottom:20,
          background:C.bg2, border:`1px solid ${C.accent}`,
          borderTop:`2px solid ${C.accent}`,
        }}>
          <div style={{ fontSize:9, color:C.accent, letterSpacing:2, marginBottom:14 }}>
            NEW OPERATOR ACCOUNT
          </div>
          {createErr && (
            <div style={{
              padding:"6px 10px", marginBottom:12,
              background:C.redDim, border:`1px solid ${C.red}`,
              fontSize:9, color:C.red,
            }}>⚠ {createErr}</div>
          )}
          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr 120px", gap:10, marginBottom:14 }}>
            <Fld label="Name">
              <Input value={form.name} onChange={v => setForm(f => ({...f, name:v}))} placeholder="Jane Smith"/>
            </Fld>
            <Fld label="Email">
              <Input value={form.email} onChange={v => setForm(f => ({...f, email:v}))} placeholder="jane@org.io" type="email"/>
            </Fld>
            <Fld label="Temp Password">
              <Input value={form.password} onChange={v => setForm(f => ({...f, password:v}))} placeholder="••••••••" type="password"/>
            </Fld>
            <Fld label="Role">
              <select value={form.role} onChange={e => setForm(f => ({...f, role:e.target.value}))}
                style={{
                  background:C.bg0, border:`1px solid ${C.line2}`, color:C.p1,
                  fontFamily:mono, fontSize:10, padding:"7px 8px", outline:"none",
                }}>
                <option value="operator">operator</option>
                <option value="auditor">auditor</option>
                <option value="admin">admin</option>
              </select>
            </Fld>
          </div>
          <Btn variant="green" onClick={handleCreate} disabled={creating}>
            {creating ? "CREATING…" : "✓ CREATE ACCOUNT"}
          </Btn>
        </div>
      )}

      {error && (
        <div style={{ padding:"8px 12px", marginBottom:14, background:C.redDim,
          border:`1px solid ${C.red}`, fontSize:9, color:C.red }}>
          {error}
        </div>
      )}

      {loading ? (
        <div style={{ fontFamily:mono, fontSize:9, color:C.p3, padding:"24px 0", textAlign:"center" }}>
          Loading users…
        </div>
      ) : (
        <>
          {/* Column headers */}
          <div style={{
            display:"grid", gridTemplateColumns:"1fr 160px 90px 80px 200px",
            gap:8, padding:"6px 12px", marginBottom:4,
            borderBottom:`1px solid ${C.line}`,
          }}>
            {["OPERATOR","EMAIL","ROLE","STATUS","ACTIONS"].map(h => (
              <div key={h} style={{ fontSize:8, color:C.p3, letterSpacing:1.5, textTransform:"uppercase" }}>
                {h}
              </div>
            ))}
          </div>

          {/* Active users */}
          {active.map(u => (
            <div key={u.id} style={{
              display:"grid", gridTemplateColumns:"1fr 160px 90px 80px 200px",
              gap:8, alignItems:"center", padding:"10px 12px",
              borderBottom:`1px solid ${C.line}`,
              background:"transparent",
            }}>
              <div>
                <div style={{ fontSize:11, fontWeight:600, color:C.p1 }}>{u.name}</div>
                {u.api_key && (
                  <div style={{ fontSize:8, color:C.p3, marginTop:2, fontFamily:mono }}>
                    key: {u.api_key.slice(0,20)}…
                  </div>
                )}
              </div>
              <div style={{ fontSize:9, color:C.p2, fontFamily:mono }}>{u.email}</div>
              <div><Badge color={ROLE_COLOR[u.role] || C.p3}>{u.role}</Badge></div>
              <div><Badge color={C.green}>ACTIVE</Badge></div>
              <div style={{ display:"flex", gap:4 }}>
                <Btn small variant="default" onClick={() => handleRotateKey(u.id)}>↻ KEY</Btn>
                <Btn small variant={pendingRevoke === u.id ? "red" : "default"}
                  onClick={() => handleRevoke(u.id)}>
                  {pendingRevoke === u.id ? "CONFIRM?" : "REVOKE"}
                </Btn>
              </div>
            </div>
          ))}

          {/* Revoked users */}
          {inactive.length > 0 && (
            <>
              <div style={{
                fontSize:8, color:C.p3, letterSpacing:2,
                textTransform:"uppercase", padding:"12px 12px 4px",
              }}>
                REVOKED ACCOUNTS
              </div>
              {inactive.map(u => (
                <div key={u.id} style={{
                  display:"grid", gridTemplateColumns:"1fr 160px 90px 80px 200px",
                  gap:8, alignItems:"center", padding:"10px 12px",
                  borderBottom:`1px solid ${C.line}`, opacity:0.45,
                }}>
                  <div style={{ fontSize:11, color:C.p2 }}>{u.name}</div>
                  <div style={{ fontSize:9, color:C.p3 }}>{u.email}</div>
                  <div><Badge color={ROLE_COLOR[u.role] || C.p3}>{u.role}</Badge></div>
                  <div><Badge color={C.red}>REVOKED</Badge></div>
                  <div>
                    <Btn small variant="amber" onClick={() => handleRestore(u.id)}>↩ RESTORE</Btn>
                  </div>
                </div>
              ))}
            </>
          )}

          {users.length === 0 && (
            <div style={{ fontSize:9, color:C.p3, padding:"24px 0", textAlign:"center" }}>
              No users found.
            </div>
          )}
        </>
      )}
    </div>
  );
}

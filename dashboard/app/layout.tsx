import React from "react";
import type { Metadata } from "next";
import { AuthProvider } from "../components/AuthContext";

export const metadata: Metadata = {
  title: "OpenClaw Governor",
  description: "Runtime governance & safety console for OpenClaw agents — Sovereign AI Lab · NOVTIA",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        {/* Early client-side safeguard: expose React on window for injected extensions
            that expect a global React variable (prevents "React is not defined" errors).
            This is intentionally conservative and only assigns if not already present. */}
        <script dangerouslySetInnerHTML={{ __html: `if(typeof window!=='undefined'&&typeof window.React==='undefined'){try{window.React=React}catch(e){}}` }} />
        <link
          href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600;700&family=DM+Sans:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body style={{ margin:0, padding:0, background:"#080e1a", color:"#dde8f5" }}>
        <AuthProvider>
          {children}
        </AuthProvider>
      </body>
    </html>
  );
}

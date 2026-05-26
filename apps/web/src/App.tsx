import { useState } from "react";
import {
  BrowserRouter,
  Navigate,
  NavLink,
  Route,
  Routes,
} from "react-router-dom";
import { Alerts } from "./pages/Alerts";
import { Cameras } from "./pages/Cameras";
import { Dashboard } from "./pages/Dashboard";
import { Login } from "./pages/Login";
import { Persons } from "./pages/Persons";
import { Settings } from "./pages/Settings";
import { Timeline } from "./pages/Timeline";

const NAV = [
  { to: "/",         label: "dashboard",  icon: "◆" },
  { to: "/timeline", label: "timeline",   icon: "▦" },
  { to: "/cameras",  label: "cameras",    icon: "▣" },
  { to: "/persons",  label: "persons",    icon: "▧" },
  { to: "/alerts",   label: "alerts",     icon: "▲" },
  { to: "/settings", label: "settings",   icon: "▤" },
] as const;

function Sidebar() {
  function logout() {
    localStorage.removeItem("access_token");
    window.location.reload();
  }

  return (
    <nav
      style={{
        width: 176,
        flexShrink: 0,
        display: "flex",
        flexDirection: "column",
        borderRight: "1px solid var(--border)",
        background: "var(--surface)",
      }}
    >
      {/* Logo */}
      <div
        style={{
          padding: "16px 20px",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <div
          style={{
            fontSize: 11,
            fontWeight: "bold",
            letterSpacing: "0.2em",
            color: "var(--accent)",
            textTransform: "uppercase",
          }}
        >
          OMNISCIENT
        </div>
        <div style={{ fontSize: 10, color: "var(--text-dim)", marginTop: 2 }}>
          home intelligence
        </div>
      </div>

      {/* Nav links */}
      <ul style={{ flex: 1, margin: 0, padding: "8px 8px", listStyle: "none" }}>
        {NAV.map(({ to, label, icon }) => (
          <li key={to}>
            <NavLink
              to={to}
              end={to === "/"}
              style={({ isActive }) => ({
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "7px 12px",
                fontSize: 12,
                textDecoration: "none",
                letterSpacing: "0.06em",
                color: isActive ? "var(--text-bright)" : "var(--text-dim)",
                background: isActive ? "var(--elevated)" : "transparent",
                borderLeft: isActive
                  ? "2px solid var(--accent)"
                  : "2px solid transparent",
                marginBottom: 1,
              })}
            >
              <span style={{ color: "var(--accent)", fontSize: 9 }}>{icon}</span>
              {label}
            </NavLink>
          </li>
        ))}
      </ul>

      {/* Bottom status + logout */}
      <div
        style={{
          borderTop: "1px solid var(--border)",
          padding: "10px 12px",
          display: "flex",
          flexDirection: "column",
          gap: 6,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            fontSize: 10,
            color: "var(--green)",
            letterSpacing: "0.1em",
            textTransform: "uppercase",
          }}
        >
          <span
            style={{
              width: 6,
              height: 6,
              background: "var(--green)",
              display: "inline-block",
            }}
          />
          online
        </div>
        <button
          className="btn btn-ghost"
          style={{ padding: "4px 10px", fontSize: 10 }}
          onClick={logout}
        >
          sign out
        </button>
      </div>
    </nav>
  );
}

export default function App() {
  const [authed, setAuthed] = useState(
    () => Boolean(localStorage.getItem("access_token"))
  );

  if (!authed) {
    return <Login onAuth={() => setAuthed(true)} />;
  }

  return (
    <BrowserRouter>
      <div style={{ display: "flex", height: "100%", overflow: "hidden" }}>
        <Sidebar />
        <main
          style={{
            flex: 1,
            overflow: "hidden",
            display: "flex",
            flexDirection: "column",
          }}
        >
          <Routes>
            <Route path="/"         element={<Dashboard />} />
            <Route path="/timeline" element={<Timeline />} />
            <Route path="/cameras"  element={<Cameras />} />
            <Route path="/persons"  element={<Persons />} />
            <Route path="/alerts"   element={<Alerts />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*"         element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

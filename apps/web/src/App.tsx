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

function Sidebar({ open, onNavigate }: { open: boolean; onNavigate: () => void }) {
  function logout() {
    localStorage.removeItem("access_token");
    window.location.reload();
  }

  return (
    <nav
      id="primary-navigation"
      className={`sidebar${open ? " open" : ""}`}
      aria-label="Primary navigation"
    >
      {/* Logo */}
      <div className="brand-lockup">
        <div className="brand-mark">O</div>
        <div>
          <div className="brand-name">Omniscient</div>
          <div className="brand-subtitle">home intelligence</div>
        </div>
      </div>

      {/* Nav links */}
      <ul className="nav-list">
        {NAV.map(({ to, label, icon }) => (
          <li key={to}>
            <NavLink
              to={to}
              end={to === "/"}
              className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
              onClick={onNavigate}
              title={label}
            >
              <span className="nav-icon" data-icon={icon} aria-hidden="true" /><span>{label}</span>
            </NavLink>
          </li>
        ))}
      </ul>

      {/* Bottom status + logout */}
      <div className="sidebar-footer">
        <div className="system-status"><span className="status-dot" /> all systems nominal</div>
        <button
          className="btn btn-ghost"
          style={{ padding: "5px 10px", fontSize: 10 }}
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
  const [navOpen, setNavOpen] = useState(false);

  if (!authed) {
    return <Login onAuth={() => setAuthed(true)} />;
  }

  return (
    <BrowserRouter>
      <div className="app-shell">
        <button
          className="mobile-nav-toggle btn btn-ghost"
          type="button"
          aria-label={navOpen ? "Close navigation" : "Open navigation"}
          aria-expanded={navOpen}
          aria-controls="primary-navigation"
          onClick={() => setNavOpen((open) => !open)}
        >
          {navOpen ? "close" : "menu"}
        </button>
        <Sidebar open={navOpen} onNavigate={() => setNavOpen(false)} />
        <main className="main-pane">
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

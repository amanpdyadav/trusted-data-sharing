import { useHash } from "./hooks.js";
import AttackView from "./components/AttackView.jsx";
import AuditView from "./components/AuditView.jsx";

const VIEWS = [
  { id: "attack", label: "Mosaic attack" },
  { id: "audit", label: "Release audit" },
];

export default function App() {
  const hash = useHash("attack");
  const view = VIEWS.some((v) => v.id === hash) ? hash : "attack";
  return (
    <>
      <nav className="topnav" aria-label="Views">
        <div className="topnav-inner">
          <span className="brand">PETs Transformer</span>
          <div className="topnav-links">
            {VIEWS.map((v) => (
              <a key={v.id} href={`#${v.id}`} aria-current={view === v.id ? "page" : undefined}>
                {v.label}
              </a>
            ))}
          </div>
        </div>
      </nav>
      {view === "audit" ? <AuditView /> : <AttackView />}
    </>
  );
}

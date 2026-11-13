import { NavLink, Link } from 'react-router-dom';
import { useFarm } from '../context/FarmContext.jsx';

const links = [
  ['Overview', '/dashboard'], ['Farm profile', '/farm'], ['New assessment', '/assessment'],
  ['Weather', '/weather'], ['Soil health', '/soil'], ['Crop health', '/crop'],
  ['Irrigation', '/irrigation'], ['Weekly advisory', '/advisory'], ['Farm history', '/history'], ['Settings', '/settings'],
];

export function Wordmark({ light = false }) {
  return <Link className={`wordmark ${light ? 'wordmark-light' : ''}`} to="/"><span>AGRI</span> VISION</Link>;
}

export default function AppShell({ children }) {
  const { farm, demoMode, setDemoMode } = useFarm();
  return <div className="app-shell">
    <aside className="sidebar">
      <Wordmark />
      <div className="sidebar-caption">SMART FARM ADVISORY</div>
      <nav className="side-nav" aria-label="Application navigation">
        {links.map(([label, to], i) => <NavLink key={to} to={to} className={({ isActive }) => `side-link ${isActive ? 'active' : ''}`}>
          <span className="side-index">{String(i + 1).padStart(2, '0')}</span>{label}
        </NavLink>)}
      </nav>
      <div className="sidebar-bottom"><span className="status-dot" />{demoMode ? 'Demo access' : 'Ready when you are'}<button className="text-button" onClick={() => setDemoMode(false)}>Exit demo</button></div>
    </aside>
    <div className="app-main">
      <header className="app-topbar">
        <div><span className="eyebrow">SELECTED FARM</span><strong>{farm.farm_id}</strong></div>
        <Link className="button button-small" to="/assessment">New assessment <span aria-hidden="true">↗</span></Link>
      </header>
      <main className="page-content">{children}</main>
      <footer className="app-footer"><span>Agri Vision · Smart Farm Advisory Council</span><span>Advice supports informed decisions; consult local agricultural experts where needed.</span></footer>
    </div>
  </div>;
}

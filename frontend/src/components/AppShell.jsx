import { NavLink, Link, useNavigate } from 'react-router-dom';
import { useFarm } from '../context/FarmContext.jsx';
import { exitFarmSession, logoutAccount } from '../services/api.js';

const links = [
  ['Overview', '/dashboard'], ['Farm profile', '/farm'], ['New assessment', '/assessment'],
  ['Weather', '/weather'], ['Soil health', '/soil'], ['Crop health', '/crop'],
  ['Irrigation', '/irrigation'], ['Weekly advisory', '/advisory'], ['Farm history', '/history'], ['Settings', '/settings'],
];

export function Wordmark({ light = false }) {
  return <Link className={`wordmark ${light ? 'wordmark-light' : ''}`} to="/"><span>AGRI</span> VISION</Link>;
}

export default function AppShell({ children }) {
  const { farm, demoMode, setDemoMode, setCredentialFarmId, selectFarm, account, setAccount, farms, setFarms } = useFarm();
  const navigate = useNavigate();
  function startAddFarm() {
    navigate('/assessment', { state: { createFarm: true, farmId: `farm-${crypto.randomUUID()}` } });
  }
  async function exitSession() {
    try {
      if (account) await logoutAccount();
      else await exitFarmSession();
    } catch { /* Clear local access even if the service is unavailable. */ }
    setAccount(null);
    setFarms([]);
    setCredentialFarmId(null);
    setDemoMode(false);
    navigate('/', { replace: true });
  }
  return <div className="app-shell">
    <aside className="sidebar">
      <Wordmark />
      <div className="sidebar-caption">SMART FARM ADVISORY</div>
      <nav className="side-nav" aria-label="Application navigation">
        {links.map(([label, to], i) => <NavLink key={to} to={to} className={({ isActive }) => `side-link ${isActive ? 'active' : ''}`}>
          <span className="side-index">{String(i + 1).padStart(2, '0')}</span>{label}
        </NavLink>)}
      </nav>
      <div className="sidebar-bottom"><span className="status-dot" />{account ? account.email : demoMode ? 'Demo access' : 'Farm access'}<button className="text-button" onClick={exitSession}>{account ? 'Log out' : 'Exit demo'}</button></div>
    </aside>
    <div className="app-main">
      <header className="app-topbar">
        <div><span className="eyebrow">SELECTED FARM</span>{account && farms.length === 0 ? <strong>No farm added</strong> : account && farms.length > 1 ? <select aria-label="Selected farm" value={farm.farm_id || ''} onChange={(event) => {
          const selected = farms.find(({ farm_id }) => farm_id === event.target.value);
          if (selected) selectFarm(selected.farm_id, selected.profile || null);
        }}>{farms.map(({ farm_id }) => <option key={farm_id} value={farm_id}>{farm_id}</option>)}</select> : <strong>{farm.farm_id}</strong>}</div>
        {(account || demoMode) && <button className="button button-outline button-small account-mobile-action" onClick={exitSession}>{account ? 'Log out' : 'Exit demo'}</button>}
        {account && farms.length === 0 ? <button className="button button-small" onClick={startAddFarm}>Add farm</button> : <>{account && <button className="button button-outline button-small" onClick={startAddFarm}>Add farm</button>}<Link className="button button-small" to="/assessment">New assessment <span aria-hidden="true">&#8599;</span></Link></>}
      </header>
      <main className="page-content">{children}</main>
      <footer className="app-footer"><span>Agri Vision · Smart Farm Advisory Council</span><span>Advice supports informed decisions; consult local agricultural experts where needed.</span></footer>
    </div>
  </div>;
}

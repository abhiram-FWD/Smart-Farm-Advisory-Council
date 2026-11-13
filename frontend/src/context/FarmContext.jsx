import { createContext, useContext, useMemo, useState } from 'react';

const FarmContext = createContext(null);
const FARM_KEY = 'agri-vision-farm';
const ADVISORY_KEY = 'agri-vision-latest-advisory';
const CREDENTIAL_FARM_KEY = 'agri-vision-credential-farm';
const defaultFarm = () => ({
  farm_id: `farm-${crypto.randomUUID()}`,
  latitude: '', longitude: '', crop_name: '', growth_stage: '',
});

function readJson(key, fallback) {
  try { const value = localStorage.getItem(key); return value ? JSON.parse(value) : fallback; }
  catch { return fallback; }
}

export function FarmProvider({ children }) {
  const [farm, setFarmState] = useState(() => readJson(FARM_KEY, null) || defaultFarm());
  const [advisory, setAdvisoryState] = useState(() => readJson(ADVISORY_KEY, null));
  const [credentialFarmId, setCredentialFarmIdState] = useState(() => localStorage.getItem(CREDENTIAL_FARM_KEY));
  const [demoMode, setDemoMode] = useState(false);

  const setFarm = (next) => setFarmState((current) => {
    const value = typeof next === 'function' ? next(current) : { ...current, ...next };
    localStorage.setItem(FARM_KEY, JSON.stringify(value));
    return value;
  });
  const setAdvisory = (value) => {
    setAdvisoryState(value);
    if (value) localStorage.setItem(ADVISORY_KEY, JSON.stringify(value));
    else localStorage.removeItem(ADVISORY_KEY);
  };
  const setCredentialFarmId = (farmId) => {
    setCredentialFarmIdState(farmId);
    if (farmId) localStorage.setItem(CREDENTIAL_FARM_KEY, farmId);
    else localStorage.removeItem(CREDENTIAL_FARM_KEY);
  };
  const value = useMemo(() => ({ farm, setFarm, advisory, setAdvisory, credentialFarmId, setCredentialFarmId, demoMode, setDemoMode }), [farm, advisory, credentialFarmId, demoMode]);
  return <FarmContext.Provider value={value}>{children}</FarmContext.Provider>;
}

export function useFarm() {
  const value = useContext(FarmContext);
  if (!value) throw new Error('useFarm must be used inside FarmProvider');
  return value;
}

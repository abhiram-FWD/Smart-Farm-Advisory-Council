import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { apiErrorMessage, requestCurrentAccount, requestAllFarmAdvisories, requestAllFarmObservations, requestMyFarms } from '../services/api.js';

const FarmContext = createContext(null);
const FARM_KEY = 'agri-vision-farm';
const ADVISORY_KEY = 'agri-vision-latest-advisory';
const CREDENTIAL_FARM_KEY = 'agri-vision-credential-farm';
const ACCOUNT_KEY = 'agri-vision-account';
const FARM_PROFILES_KEY = 'agri-vision-farm-profiles';
const emptyFarm = (farm_id) => ({ farm_id, latitude: '', longitude: '', crop_name: '', growth_stage: '' });
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
  // MongoDB history is the authoritative source and is loaded for the selected farm.
  // A single old browser cache cannot safely identify which farm it belongs to.
  const [advisory, setAdvisoryState] = useState(null);
  const [credentialFarmId, setCredentialFarmIdState] = useState(() => localStorage.getItem(CREDENTIAL_FARM_KEY));
  const [demoMode, setDemoMode] = useState(false);
  const [account, setAccountState] = useState(() => readJson(ACCOUNT_KEY, null));
  const [accountLoading, setAccountLoading] = useState(() => Boolean(readJson(ACCOUNT_KEY, null)));
  const [farms, setFarms] = useState([]);
  const [farmAdvisories, setFarmAdvisories] = useState([]);
  const [farmObservations, setFarmObservations] = useState([]);
  const [farmDataLoading, setFarmDataLoading] = useState(false);
  const [farmDataError, setFarmDataError] = useState('');

  const setFarm = (next) => setFarmState((current) => {
    const value = typeof next === 'function' ? next(current) : { ...current, ...next };
    localStorage.setItem(FARM_KEY, JSON.stringify(value));
    const profiles = readJson(FARM_PROFILES_KEY, {});
    profiles[value.farm_id] = value;
    localStorage.setItem(FARM_PROFILES_KEY, JSON.stringify(profiles));
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
  const selectFarm = (farmId, profile = null) => {
    const profiles = readJson(FARM_PROFILES_KEY, {});
    const selected = profile ? { ...emptyFarm(farmId), ...profile, farm_id: farmId } : profiles[farmId] || emptyFarm(farmId);
    if (profile) {
      profiles[farmId] = selected;
      localStorage.setItem(FARM_PROFILES_KEY, JSON.stringify(profiles));
    }
    setFarmState(selected);
    localStorage.setItem(FARM_KEY, JSON.stringify(selected));
    setCredentialFarmId(farmId);
    setAdvisory(null);
  };
  const clearFarmSelection = (staleFarmId = readJson(FARM_KEY, null)?.farm_id) => {
    setFarmState(emptyFarm(''));
    localStorage.removeItem(FARM_KEY);
    const profiles = readJson(FARM_PROFILES_KEY, {});
    for (const farmId of Array.isArray(staleFarmId) ? staleFarmId : [staleFarmId]) {
      if (farmId) delete profiles[farmId];
    }
    localStorage.setItem(FARM_PROFILES_KEY, JSON.stringify(profiles));
    setCredentialFarmId(null);
    setAdvisory(null);
    setFarmAdvisories([]);
    setFarmObservations([]);
    setFarmDataError('');
  };
  const setAccount = (next) => {
    setAccountState(next);
    setAccountLoading(false);
    if (next) localStorage.setItem(ACCOUNT_KEY, JSON.stringify(next));
    else localStorage.removeItem(ACCOUNT_KEY);
  };
  const refreshFarmData = async (farmId = farm?.farm_id) => {
    if (!farmId) return;
    try {
      const [advisories, observations] = await Promise.all([
        requestAllFarmAdvisories(farmId), requestAllFarmObservations(farmId),
      ]);
      if (farmId !== farm?.farm_id) return;
      const records = advisories || [];
      setFarmAdvisories(records);
      setFarmObservations(observations || []);
      setAdvisoryState(records[0] ? {
        ...records[0].advisory,
        memory: { ...(records[0].advisory?.memory || {}), advisory_saved: true, advisory_id: records[0].advisory_id },
      } : null);
      setFarmDataError('');
    } catch (error) {
      if (farmId === farm?.farm_id) setFarmDataError(apiErrorMessage(error));
    }
  };
  useEffect(() => {
    if (!account) return;
    let active = true;
    Promise.all([requestCurrentAccount(), requestMyFarms()]).then(([current, ownedFarms]) => {
      if (!active) return;
      setAccount(current);
      setFarms(ownedFarms);
      const profiles = readJson(FARM_PROFILES_KEY, {});
      ownedFarms.forEach((item) => {
        profiles[item.farm_id] = { ...emptyFarm(item.farm_id), ...profiles[item.farm_id], ...(item.profile || {}) };
      });
      localStorage.setItem(FARM_PROFILES_KEY, JSON.stringify(profiles));
      const selected = ownedFarms.find((item) => item.farm_id === credentialFarmId)
        || ownedFarms.find((item) => item.farm_id === farm?.farm_id)
        || ownedFarms[0];
      if (selected) {
        const staleFarmIds = [credentialFarmId, farm?.farm_id].filter((farmId) => farmId && farmId !== selected.farm_id && !ownedFarms.some((item) => item.farm_id === farmId));
        if (staleFarmIds.length) clearFarmSelection(staleFarmIds);
        const cachedProfile = readJson(FARM_PROFILES_KEY, {})[selected.farm_id] || {};
        selectFarm(selected.farm_id, { ...cachedProfile, ...(selected.profile || {}) });
      } else {
        clearFarmSelection([credentialFarmId, farm?.farm_id]);
      }
    }).catch(() => {
      if (active) {
        setAccount(null);
        setCredentialFarmId(null);
        setFarms([]);
      }
    }).finally(() => { if (active) setAccountLoading(false); });
    return () => { active = false; };
  // Validate a persisted account cookie once when the provider mounts.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (!farm?.farm_id || (!account && !credentialFarmId)) {
      setFarmAdvisories([]);
      setFarmObservations([]);
      setFarmDataError('');
      setFarmDataLoading(false);
      return undefined;
    }
    let active = true;
    setFarmDataLoading(true);
    setFarmDataError('');
    setFarmAdvisories([]);
    setFarmObservations([]);
    setAdvisoryState(null);
    Promise.all([requestAllFarmAdvisories(farm.farm_id), requestAllFarmObservations(farm.farm_id)]).then(([data, observations]) => {
      if (!active) return;
      const records = data || [];
      setFarmAdvisories(records);
      setFarmObservations(observations || []);
      setAdvisoryState(records[0] ? {
        ...records[0].advisory,
        memory: { ...(records[0].advisory?.memory || {}), advisory_saved: true, advisory_id: records[0].advisory_id },
      } : null);
    }).catch((error) => {
      if (active) { setFarmAdvisories([]); setFarmObservations([]); setFarmDataError(apiErrorMessage(error)); }
    }).finally(() => { if (active) setFarmDataLoading(false); });
    return () => { active = false; };
  // Key the load to both farm and active credential so stale data cannot cross farms.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [farm?.farm_id, account?.user_id, credentialFarmId]);
  const value = useMemo(() => ({ farm, setFarm, advisory, setAdvisory, farmAdvisories, farmObservations, farmDataLoading, farmDataError, refreshFarmData, credentialFarmId, setCredentialFarmId, selectFarm, clearFarmSelection, demoMode, setDemoMode, account, setAccount, accountLoading, farms, setFarms }), [farm, advisory, farmAdvisories, farmObservations, farmDataLoading, farmDataError, credentialFarmId, demoMode, account, accountLoading, farms]);
  return <FarmContext.Provider value={value}>{children}</FarmContext.Provider>;
}

export function useFarm() {
  const value = useContext(FarmContext);
  if (!value) throw new Error('useFarm must be used inside FarmProvider');
  return value;
}

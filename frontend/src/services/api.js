import axios from 'axios';

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 120000,
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
});

export function apiErrorMessage(error) {
  if (error?.code === 'ECONNABORTED') return 'The advisory is taking longer than expected. Please try again.';
  if (!error?.response) return 'Could not reach the advisory service. Check that the backend is running and the API URL is correct.';
  if (error.config?.url?.startsWith('/api/auth/login') && error.response.status === 401) return 'Email or password is incorrect.';
  if (error.config?.url?.startsWith('/api/auth/register') && error.response.status === 409) return 'An account with this email already exists.';
  if (error.response.status === 401) return error.response.data?.detail || 'Farm access is unavailable in this browser. No new credential was created.';
  if (error.response.status === 403) return error.response.data?.detail || 'This request was blocked because its origin could not be verified.';
  if (error.response.status === 404) return error.response.data?.detail || 'This farm is not available to the active browser credential.';
  if (error.response.status === 409) return error.response.data?.detail || 'This browser already has a different active farm credential.';
  const detail = error.response.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((item) => `${item.loc?.at(-1) || 'Field'}: ${item.msg}`).join(' · ');
  return `The advisory service returned an error (${error.response.status}). Please review your information and try again.`;
}

const csrfHeaders = { 'X-AgriVision-Request': 'same-origin' };

export async function registerAccount(email, password) {
  const { data } = await api.post('/api/auth/register', { email, password }, { headers: csrfHeaders });
  return data.user;
}

export async function loginAccount(email, password) {
  const { data } = await api.post('/api/auth/login', { email, password }, { headers: csrfHeaders });
  return data.user;
}

export async function logoutAccount() {
  const { data } = await api.post('/api/auth/logout', {}, { headers: csrfHeaders });
  return data;
}

export async function requestCurrentAccount() {
  const { data } = await api.get('/api/auth/me');
  return data.user;
}

export async function requestMyFarms() {
  const { data } = await api.get('/api/farms');
  return data.items;
}

export async function registerFarm(farm_id) {
  const { data } = await api.post('/api/farms', { farm_id }, { headers: csrfHeaders });
  return data;
}

export async function exitFarmSession() {
  const { data } = await api.post('/api/farms/session/exit', {}, { headers: csrfHeaders });
  return data;
}

export async function requestAdvisory(payload) {
  const { data } = await api.post('/api/advisory', payload, { headers: csrfHeaders });
  return data;
}

export async function requestFarmObservations(farmId, limit = 20, skip = 0) {
  const { data } = await api.get(`/api/farms/${encodeURIComponent(farmId)}/observations`, { params: { limit, skip } });
  return data;
}

export async function requestFarmAdvisories(farmId, limit = 20, skip = 0) {
  const { data } = await api.get(`/api/farms/${encodeURIComponent(farmId)}/advisories`, { params: { limit, skip } });
  return data;
}

async function requestAllPages(requestPage, farmId) {
  const pageSize = 100;
  const items = [];
  let total = Infinity;
  while (items.length < total) {
    const page = await requestPage(farmId, pageSize, items.length);
    items.push(...(page.items || []));
    total = Number.isFinite(page.total) ? page.total : items.length;
    if (!(page.items || []).length) break;
  }
  return items;
}

export function requestAllFarmObservations(farmId) {
  return requestAllPages(requestFarmObservations, farmId);
}

export function requestAllFarmAdvisories(farmId) {
  return requestAllPages(requestFarmAdvisories, farmId);
}

export async function updateFarmProfile(farmId, profile) {
  const { data } = await api.put(`/api/farms/${encodeURIComponent(farmId)}/profile`, profile, { headers: csrfHeaders });
  return data;
}

export async function requestFarmWeather(farmId, latitude, longitude) {
  const { data } = await api.get(`/api/farms/${encodeURIComponent(farmId)}/weather`, { params: { latitude, longitude } });
  return data;
}

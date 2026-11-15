import { beforeEach, describe, expect, it, vi } from 'vitest';

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), config: null }));

vi.mock('axios', () => ({
  default: {
    create: vi.fn((config) => {
      http.config = config;
      return { get: http.get, post: http.post, put: http.put };
    }),
  },
}));

import { api, registerAccount, loginAccount, logoutAccount, requestCurrentAccount, requestMyFarms, registerFarm, requestAdvisory, requestFarmAdvisories, requestFarmObservations, requestFarmWeather, updateFarmProfile, requestAllFarmObservations } from './api.js';

describe('farm API client', () => {
  beforeEach(() => {
    http.get.mockReset();
    http.post.mockReset();
    http.put.mockReset();
  });

  it('uses browser-managed credentials without storing or returning a raw token', async () => {
    http.post.mockResolvedValue({ data: { farm_id: 'farm-123', registered: true } });

    const result = await registerFarm('farm-123');

    expect(api.defaults?.withCredentials ?? http.config.withCredentials).toBe(true);
    expect(http.post).toHaveBeenCalledWith(
      '/api/farms',
      { farm_id: 'farm-123' },
      { headers: { 'X-AgriVision-Request': 'same-origin' } },
    );
    expect(result).toEqual({ farm_id: 'farm-123', registered: true });
    expect(JSON.stringify(result)).not.toMatch(/token/i);
  });

  it('preserves the assessment request body and adds the CSRF request header', async () => {
    const payload = { farm_id: 'farm-123', crop_name: 'maize' };
    http.post.mockResolvedValue({ data: { status: 'completed' } });

    await requestAdvisory(payload);

    expect(http.post).toHaveBeenCalledWith(
      '/api/advisory',
      payload,
      { headers: { 'X-AgriVision-Request': 'same-origin' } },
    );
  });

  it('requests both history resources with a bounded-list default', async () => {
    http.get.mockResolvedValue({ data: { items: [] } });

    await requestFarmObservations('farm/123');
    await requestFarmAdvisories('farm-123', 12);

    expect(http.get).toHaveBeenNthCalledWith(
      1,
      '/api/farms/farm%2F123/observations',
      { params: { limit: 20, skip: 0 } },
    );
    expect(http.get).toHaveBeenNthCalledWith(
      2,
      '/api/farms/farm-123/advisories',
      { params: { limit: 12, skip: 0 } },
    );
  });

  it('loads every bounded history page so counts and comparisons are complete', async () => {
    const first = Array.from({ length: 100 }, (_, index) => ({ id: index }));
    http.get.mockResolvedValueOnce({ data: { items: first, total: 101 } })
      .mockResolvedValueOnce({ data: { items: [{ id: 100 }], total: 101 } });
    const records = await requestAllFarmObservations('farm-123');
    expect(records).toHaveLength(101);
    expect(http.get).toHaveBeenNthCalledWith(1, '/api/farms/farm-123/observations', { params: { limit: 100, skip: 0 } });
    expect(http.get).toHaveBeenNthCalledWith(2, '/api/farms/farm-123/observations', { params: { limit: 100, skip: 100 } });
  });

  it('uses authenticated farm IDs for profile writes and independent weather reads', async () => {
    http.put.mockResolvedValue({ data: { farm_id: 'farm-123', crop_name: 'Rice' } });
    http.get.mockResolvedValue({ data: { source: 'Open-Meteo' } });
    await updateFarmProfile('farm-123', { crop_name: 'Rice' });
    await requestFarmWeather('farm-123', 12, 77);
    expect(http.put).toHaveBeenCalledWith('/api/farms/farm-123/profile', { crop_name: 'Rice' }, { headers: { 'X-AgriVision-Request': 'same-origin' } });
    expect(http.get).toHaveBeenCalledWith('/api/farms/farm-123/weather', { params: { latitude: 12, longitude: 77 } });
  });
});

describe('account API client', () => {
  beforeEach(() => { http.get.mockReset(); http.post.mockReset(); });

  it('uses same-origin POSTs for account mutations and cookies for session identity', async () => {
    http.post.mockResolvedValue({ data: { user: { user_id: 'user-1', email: 'farmer@example.com' } } });
    http.get.mockResolvedValueOnce({ data: { user: { user_id: 'user-1', email: 'farmer@example.com' } } })
      .mockResolvedValueOnce({ data: { items: [{ farm_id: 'farm-1' }] } });

    await registerAccount('farmer@example.com', 'a secure password');
    await loginAccount('farmer@example.com', 'a secure password');
    await logoutAccount();
    await requestCurrentAccount();
    await requestMyFarms();

    expect(http.post).toHaveBeenNthCalledWith(1, '/api/auth/register', { email: 'farmer@example.com', password: 'a secure password' }, { headers: { 'X-AgriVision-Request': 'same-origin' } });
    expect(http.post).toHaveBeenNthCalledWith(2, '/api/auth/login', { email: 'farmer@example.com', password: 'a secure password' }, { headers: { 'X-AgriVision-Request': 'same-origin' } });
    expect(http.post).toHaveBeenNthCalledWith(3, '/api/auth/logout', {}, { headers: { 'X-AgriVision-Request': 'same-origin' } });
    expect(http.get).toHaveBeenNthCalledWith(1, '/api/auth/me');
    expect(http.get).toHaveBeenNthCalledWith(2, '/api/farms');
  });
});

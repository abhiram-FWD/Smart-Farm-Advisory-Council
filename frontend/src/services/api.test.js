import { beforeEach, describe, expect, it, vi } from 'vitest';

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), config: null }));

vi.mock('axios', () => ({
  default: {
    create: vi.fn((config) => {
      http.config = config;
      return { get: http.get, post: http.post };
    }),
  },
}));

import { api, registerFarm, requestAdvisory, requestFarmAdvisories, requestFarmObservations } from './api.js';

describe('farm API client', () => {
  beforeEach(() => {
    http.get.mockReset();
    http.post.mockReset();
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
      { params: { limit: 20 } },
    );
    expect(http.get).toHaveBeenNthCalledWith(
      2,
      '/api/farms/farm-123/advisories',
      { params: { limit: 12 } },
    );
  });
});

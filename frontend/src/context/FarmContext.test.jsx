import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const { requests } = vi.hoisted(() => ({ requests: { advisories: vi.fn(), observations: vi.fn(), account: vi.fn(), farms: vi.fn() } }));
vi.mock('../services/api.js', () => ({
  requestCurrentAccount: requests.account,
  requestMyFarms: requests.farms,
  requestAllFarmAdvisories: requests.advisories,
  requestAllFarmObservations: requests.observations,
}));

import { FarmProvider, useFarm } from './FarmContext.jsx';

function Probe() {
  const { farm, advisory, farmObservations, selectFarm } = useFarm();
  return <div><span>{farm.farm_id}</span><span>{farm.crop_name}</span><span>{advisory?.label || 'empty advisory'}</span><span>{farmObservations[0]?.observation?.crop_name || 'empty observations'}</span><button onClick={() => selectFarm('farm-b')}>Select B</button></div>;
}

function AccountProbe() {
  const { farm, farms, credentialFarmId } = useFarm();
  return <div><span>{farm.farm_id || 'no selected farm'}</span><span>{credentialFarmId || 'no selected credential'}</span><span>{farms.length} farms</span></div>;
}

describe('selected farm data flow', () => {
  beforeEach(() => {
    localStorage.clear();
    requests.account.mockReset();
    requests.farms.mockReset();
    localStorage.setItem('agri-vision-farm', JSON.stringify({ farm_id: 'farm-a', crop_name: 'Wheat' }));
    localStorage.setItem('agri-vision-credential-farm', 'farm-a');
    localStorage.setItem('agri-vision-farm-profiles', JSON.stringify({
      'farm-a': { farm_id: 'farm-a', crop_name: 'Wheat' },
      'farm-b': { farm_id: 'farm-b', crop_name: 'Rice' },
    }));
    requests.advisories.mockImplementation((farmId) => Promise.resolve([{ advisory: { label: `Advisory ${farmId}` } }]));
    requests.observations.mockImplementation((farmId) => Promise.resolve([{ observation: { crop_name: farmId === 'farm-a' ? 'Wheat' : 'Rice' } }]));
  });

  it('clears previous farm data and fetches history for the newly selected farm', async () => {
    render(<FarmProvider><Probe /></FarmProvider>);
    expect(await screen.findByText('Advisory farm-a')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Select B' }));
    await waitFor(() => expect(screen.getByText('Advisory farm-b')).toBeInTheDocument());
    expect(screen.getByText('farm-b')).toBeInTheDocument();
    expect(screen.getAllByText('Rice')).toHaveLength(2);
    expect(screen.queryByText('Advisory farm-a')).not.toBeInTheDocument();
    expect(requests.advisories).toHaveBeenLastCalledWith('farm-b');
    expect(requests.observations).toHaveBeenLastCalledWith('farm-b');
  });

  it('replaces a deleted selected farm with the current owned farm and removes the stale browser entry', async () => {
    localStorage.setItem('agri-vision-account', JSON.stringify({ user_id: 'user-1', email: 'farmer@example.com' }));
    requests.account.mockResolvedValue({ user_id: 'user-1', email: 'farmer@example.com' });
    requests.farms.mockResolvedValue([{ farm_id: 'farm-b', profile: { crop_name: 'Rice' } }]);
    render(<FarmProvider><AccountProbe /></FarmProvider>);

    expect(await screen.findAllByText('farm-b')).toHaveLength(2);
    expect(screen.getByText('1 farms')).toBeInTheDocument();
    expect(localStorage.getItem('agri-vision-farm')).toContain('farm-b');
    expect(localStorage.getItem('agri-vision-credential-farm')).toBe('farm-b');
    expect(JSON.parse(localStorage.getItem('agri-vision-farm-profiles'))).not.toHaveProperty('farm-a');
  });

  it('clears stale selection when the authenticated user has no farms', async () => {
    localStorage.setItem('agri-vision-account', JSON.stringify({ user_id: 'user-1', email: 'farmer@example.com' }));
    requests.account.mockResolvedValue({ user_id: 'user-1', email: 'farmer@example.com' });
    requests.farms.mockResolvedValue([]);
    render(<FarmProvider><AccountProbe /></FarmProvider>);

    expect(await screen.findByText('no selected farm')).toBeInTheDocument();
    expect(screen.getByText('no selected credential')).toBeInTheDocument();
    expect(screen.getByText('0 farms')).toBeInTheDocument();
    expect(localStorage.getItem('agri-vision-farm')).toBeNull();
    expect(localStorage.getItem('agri-vision-credential-farm')).toBeNull();
    expect(JSON.parse(localStorage.getItem('agri-vision-farm-profiles'))).not.toHaveProperty('farm-a');
  });
});

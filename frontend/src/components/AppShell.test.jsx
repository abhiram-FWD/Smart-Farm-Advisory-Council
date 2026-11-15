import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';

const { mocks } = vi.hoisted(() => ({
  mocks: {
    state: { farm: { farm_id: 'farm-preserved' }, demoMode: true, setDemoMode: vi.fn(), setCredentialFarmId: vi.fn(), selectFarm: vi.fn(), setAccount: vi.fn(), setFarms: vi.fn() },
    exitFarmSession: vi.fn(),
    registerFarm: vi.fn(),
    requestMyFarms: vi.fn(),
  },
}));

vi.mock('../context/FarmContext.jsx', () => ({ useFarm: () => mocks.state }));
vi.mock('../services/api.js', () => ({ exitFarmSession: mocks.exitFarmSession, logoutAccount: vi.fn(), registerFarm: mocks.registerFarm, requestMyFarms: mocks.requestMyFarms }));

import AppShell from './AppShell.jsx';

describe('Exit Demo', () => {
  beforeEach(() => {
    mocks.exitFarmSession.mockReset().mockResolvedValue({ session_ended: true });
    mocks.registerFarm.mockReset();
    mocks.requestMyFarms.mockReset();
    mocks.state = { farm: { farm_id: 'farm-preserved' }, demoMode: true, setDemoMode: vi.fn(), setCredentialFarmId: vi.fn(), selectFarm: vi.fn(), setAccount: vi.fn(), setFarms: vi.fn() };
  });

  it('expires access, clears local session state, and replaces the route with landing', async () => {
    function Location() { return <output>{useLocation().pathname}</output>; }
    render(<MemoryRouter initialEntries={['/dashboard']}><AppShell><p>Dashboard</p></AppShell><Location /></MemoryRouter>);

    fireEvent.click(screen.getAllByRole('button', { name: 'Exit demo' })[0]);

    await waitFor(() => expect(screen.getByText('/')).toBeInTheDocument());
    expect(mocks.exitFarmSession).toHaveBeenCalledOnce();
    expect(mocks.state.setCredentialFarmId).toHaveBeenCalledWith(null);
    expect(mocks.state.setDemoMode).toHaveBeenCalledWith(false);
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
  });

  it('routes Add farm to assessment without registering a farm', async () => {
    mocks.state.account = { user_id: 'user-1', email: 'farmer@example.com' };
    mocks.state.farms = [];
    mocks.state.farm = { farm_id: '' };
    function Location() { return <output>{useLocation().pathname}</output>; }
    render(<MemoryRouter initialEntries={['/dashboard']}><AppShell><p>Dashboard</p></AppShell><Location /></MemoryRouter>);

    expect(screen.getByText('No farm added')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Add farm' }));

    await waitFor(() => expect(screen.getByText('/assessment')).toBeInTheDocument());
    expect(mocks.registerFarm).not.toHaveBeenCalled();
    expect(mocks.requestMyFarms).not.toHaveBeenCalled();
  });
});

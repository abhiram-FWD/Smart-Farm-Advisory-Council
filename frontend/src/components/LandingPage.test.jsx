import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';

const { state } = vi.hoisted(() => ({ state: { account: null } }));
vi.mock('../context/FarmContext.jsx', () => ({ useFarm: () => state }));
import LandingPage from './LandingPage.jsx';

function CurrentPath() { return <output data-testid="path">{useLocation().pathname}</output>; }

describe('landing navigation', () => {
  beforeEach(() => { state.account = null; });
  it('sends public exploration to the sample demo and account actions to auth pages', () => {
    render(<MemoryRouter><LandingPage /><CurrentPath /></MemoryRouter>);
    fireEvent.click(screen.getByRole('link', { name: /Explore Agri Vision/ }));
    expect(screen.getByTestId('path')).toHaveTextContent('/demo');
    fireEvent.click(screen.getByRole('link', { name: /sample assessment/ }));
    expect(screen.getByTestId('path')).toHaveTextContent('/demo/advisory');
    fireEvent.click(screen.getByRole('link', { name: /Get started/ }));
    expect(screen.getByTestId('path')).toHaveTextContent('/signup');
  });

  it('sends a signed-in farmer to their real workspace', () => {
    state.account = { user_id: 'user-1', email: 'farmer@example.test' };
    render(<MemoryRouter><LandingPage /><CurrentPath /></MemoryRouter>);
    fireEvent.click(screen.getByRole('link', { name: /Explore Agri Vision/ }));
    expect(screen.getByTestId('path')).toHaveTextContent('/dashboard');
    fireEvent.click(screen.getByRole('link', { name: /Begin an assessment/ }));
    expect(screen.getByTestId('path')).toHaveTextContent('/assessment');
    fireEvent.click(screen.getByRole('link', { name: /My dashboard/ }));
    expect(screen.getByTestId('path')).toHaveTextContent('/dashboard');
  });
});

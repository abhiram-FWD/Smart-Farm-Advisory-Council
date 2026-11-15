import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import PublicDemo from './PublicDemo.jsx';

function CurrentPath() { return <output data-testid="path">{useLocation().pathname}</output>; }
function DemoRoutes() { return <><Routes><Route path="/demo" element={<PublicDemo />} /><Route path="/demo/:section" element={<PublicDemo />} /></Routes><CurrentPath /></>; }

describe('public illustrative demo', () => {
  it('presents sample-only read-only data and links to account creation', () => {
    render(<MemoryRouter initialEntries={['/demo']}><DemoRoutes /></MemoryRouter>);
    expect(screen.getByText(/Illustrative sample data only/)).toBeInTheDocument();
    expect(screen.getAllByText('Riverbend Demonstration Plot').length).toBeGreaterThan(0);
    expect(screen.getAllByRole('link', { name: /Create an account/ }).length).toBeGreaterThan(0);
    expect(document.querySelector('form')).toBeNull();
  });

  it('navigates among the eight sample sections without leaving the public demo', () => {
    render(<MemoryRouter initialEntries={['/demo']}><DemoRoutes /></MemoryRouter>);
    fireEvent.click(screen.getByRole('link', { name: 'Farm history' }));
    expect(screen.getByTestId('path')).toHaveTextContent('/demo/history');
    expect(screen.getByText('A record that grows over time.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('link', { name: 'Irrigation' }));
    expect(screen.getByTestId('path')).toHaveTextContent('/demo/irrigation');
    expect(screen.getByText('Water with context.')).toBeInTheDocument();
  });
});

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';

const { apiMocks } = vi.hoisted(() => ({
  apiMocks: {
    observations: vi.fn(),
    advisories: vi.fn(),
    errorMessage: vi.fn(),
    farmState: { farm: { farm_id: 'farm-browser-selected' }, advisory: null },
  },
}));

vi.mock('../context/FarmContext.jsx', () => ({
  useFarm: () => apiMocks.farmState,
}));

vi.mock('../services/api.js', () => ({
  requestFarmObservations: apiMocks.observations,
  requestFarmAdvisories: apiMocks.advisories,
  apiErrorMessage: apiMocks.errorMessage,
  registerFarm: vi.fn(),
  requestAdvisory: vi.fn(),
}));

import { HistoryPage, SoilPage, CropPage, IrrigationPage, AdvisoryPage, DashboardPage, WeatherPage } from './Pages.jsx';
import { MemoryRouter } from 'react-router-dom';

describe('Farm History page', () => {
  beforeEach(() => {
    apiMocks.observations.mockReset();
    apiMocks.advisories.mockReset();
    apiMocks.errorMessage.mockReset();
    apiMocks.errorMessage.mockReturnValue('History request failed.');
  });

  it('shows a loading state while both MongoDB requests are pending', async () => {
    let resolveObservations;
    let resolveAdvisories;
    apiMocks.observations.mockReturnValue(new Promise((resolve) => { resolveObservations = resolve; }));
    apiMocks.advisories.mockReturnValue(new Promise((resolve) => { resolveAdvisories = resolve; }));

    render(<HistoryPage />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading farm history from MongoDB');

    await act(async () => {
      resolveObservations({ items: [] });
      resolveAdvisories({ items: [] });
    });
  });

  it('shows an honest empty state when MongoDB returns no records', async () => {
    apiMocks.observations.mockResolvedValue({ items: [] });
    apiMocks.advisories.mockResolvedValue({ items: [] });

    render(<HistoryPage />);

    expect(await screen.findByText('No saved observations were found for this farm.')).toBeInTheDocument();
    expect(screen.getByText('No saved advisories were found for this farm.')).toBeInTheDocument();
  });

  it('renders only stored observation and advisory values', async () => {
    apiMocks.observations.mockResolvedValue({ items: [{
      observation_id: 'obs-1',
      created_at: '2026-01-02T03:04:00Z',
      observation: { crop_name: 'Rice', growth_stage: 'Flowering', soil_moisture: 28, symptoms: ['leaf spots'] },
    }] });
    apiMocks.advisories.mockResolvedValue({ items: [{
      advisory_id: 'adv-1',
      created_at: '2026-01-02T03:05:00Z',
      advisory: { weekly_action_list: ['Inspect drainage'], risk_alerts: [{ risk: 'Waterlogging', severity: 'moderate' }] },
    }] });

    render(<HistoryPage />);

    expect(await screen.findByText('Rice')).toBeInTheDocument();
    expect(screen.getByText('28')).toBeInTheDocument();
    expect(screen.getByText('Inspect drainage')).toBeInTheDocument();
    expect(screen.getByText('Waterlogging · moderate')).toBeInTheDocument();
  });

  it('shows a genuine service error', async () => {
    const failure = new Error('unavailable');
    failure.response = { status: 503 };
    apiMocks.observations.mockRejectedValue(failure);
    apiMocks.advisories.mockResolvedValue({ items: [] });

    render(<HistoryPage />);

    expect(await screen.findByRole('alert')).toHaveTextContent('History request failed.');
    expect(screen.getByRole('alert')).toHaveTextContent('History could not be loaded.');
  });

  it('shows a distinct access-denied state', async () => {
    const failure = new Error('credential unavailable');
    failure.response = { status: 401 };
    apiMocks.observations.mockRejectedValue(failure);
    apiMocks.advisories.mockResolvedValue({ items: [] });
    apiMocks.errorMessage.mockReturnValue('Farm access is unavailable in this browser.');

    render(<HistoryPage />);

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Farm access unavailable.'));
    expect(screen.getByRole('alert')).toHaveTextContent('Farm IDs alone do not grant access.');
  });
});

describe('agricultural interpretation labels', () => {
  beforeEach(() => {
    apiMocks.farmState = {
      farm: { farm_id: 'farm-test', crop_name: 'Rice', growth_stage: 'Flowering' },
      advisory: {
        status: 'completed',
        weekly_action_list: ['Review a soil test'],
        risk_alerts: [{
          risk: 'Soil moisture is below the preliminary rule threshold',
          classification: 'preliminary_rule_indicator',
          reported_by: ['Soil Agent'],
        }],
        agents: {
          soil: {
            soil_report: { moisture: 20, ph: 5, nitrogen: 10, phosphorus: 12, potassium: 14 },
            preliminary_rule_indicators: ['Soil moisture is below the preliminary rule threshold'],
            indicator_context: 'Preliminary rules are not diagnoses.',
            nutrient_interpretation_note: 'Units and soil test method were not supplied.',
            ai_identified_risks: ['Possible leaf issue'],
            recommendations: ['Review a soil test'],
          },
          irrigation: {
            recommended_action: 'Irrigation recommended',
            reason: 'Low soil moisture under the demo rule.',
            guidance_type: 'preliminary_demonstration_guidance',
            guidance_note: 'Not a farm-specific prescription. Consider crop stage and soil type.',
            soil_moisture: 20,
            expected_rainfall_mm: 0,
          },
        },
        watering_schedule: {
          recommended_action: 'Irrigation recommended',
          reason: 'Low soil moisture under the demo rule.',
          guidance_note: 'Not a farm-specific prescription. Consider crop stage and soil type.',
          soil_moisture: 20,
          expected_rainfall_mm: 0,
        },
        weather_summary: {},
      },
    };
  });

  it('separates measured values, preliminary indicators, AI interpretation and recommendations', () => {
    render(<MemoryRouter><SoilPage /></MemoryRouter>);

    expect(screen.getByText('MEASURED VALUES')).toBeInTheDocument();
    expect(screen.getByText('PRELIMINARY RULE INDICATORS')).toBeInTheDocument();
    expect(screen.getByText('AI-GENERATED INTERPRETATIONS')).toBeInTheDocument();
    expect(screen.getByText('ACTIONABLE RECOMMENDATIONS')).toBeInTheDocument();
    expect(screen.getByText(/Units and soil test method were not supplied/)).toBeInTheDocument();
  });

  it('shows unavailable measurements and empty interpretations without inventing values', () => {
    apiMocks.farmState = {
      farm: { farm_id: 'farm-test' },
      advisory: { agents: { soil: { soil_report: {} } } },
    };

    render(<MemoryRouter><SoilPage /></MemoryRouter>);

    expect(screen.getAllByText('—')).toHaveLength(5);
    expect(screen.getByText(/not supplied/i)).toBeInTheDocument();
    expect(screen.getByText('No relevant knowledge sources were returned.')).toBeInTheDocument();
  });

  it('shows source provenance and insufficient-evidence review states', () => {
    const source = {
      evidence_id: 'soil::section::0', title: 'SOIL MANAGEMENT GUIDE',
      filename: 'soil_management.txt', source: 'soil_management.txt',
      section: '2. SOIL MOISTURE', source_url: 'Unavailable',
    };
    apiMocks.farmState = {
      farm: { farm_id: 'farm-test', crop_name: 'Wheat' },
      advisory: { agents: { soil: {
        soil_report: {}, evidence_status: 'insufficient',
        expert_review_required: true,
        soil_health_summary: 'Insufficient relevant retrieved evidence.',
        evidence_sources: [], retrieved_sources: [source],
      } } },
    };
    const { unmount } = render(<MemoryRouter><SoilPage /></MemoryRouter>);
    expect(screen.getByRole('status')).toHaveTextContent(/Expert review is required/);
    expect(screen.getByText('Insufficient relevant retrieved evidence.')).toBeInTheDocument();
    unmount();

    apiMocks.farmState.advisory.agents.pest_disease = {
      crop_report: { crop_name: 'Wheat' }, expert_inspection_required: true,
      evidence_summary: 'Insufficient relevant crop-health evidence.',
      evidence_sources: [source],
    };
    render(<MemoryRouter><CropPage /></MemoryRouter>);
    expect(screen.getByText(/SOIL MANAGEMENT GUIDE/)).toBeInTheDocument();
    expect(screen.getByText(/2. SOIL MOISTURE/)).toBeInTheDocument();
    expect(screen.getByText(/Original reference unavailable/)).toBeInTheDocument();
  });

  it('renders legacy string findings with separate evidence metadata', () => {
    const source = {
      evidence_id: 'wheat::aphids::0', title: 'Wheat pest guide',
      filename: 'wheat_pests.txt', section: 'Aphids',
    };
    apiMocks.farmState = {
      farm: { farm_id: 'farm-test', crop_name: 'Wheat' },
      advisory: { agents: { pest_disease: {
        crop_report: { crop_name: 'Wheat' }, expert_inspection_required: false,
        possible_pest_risks: ['Possible Aphids'],
        pest_risk_evidence: [{ risk: 'Possible Aphids', evidence_status: 'source_supported_possible_risk', sources: [source] }],
        recommendations: ['Inspect affected leaves.'],
        recommendation_evidence: [{ text: 'Inspect affected leaves.', evidence_status: 'verbatim_source_excerpt', sources: [source] }],
      } } },
    };
    render(<MemoryRouter><CropPage /></MemoryRouter>);

    expect(screen.getByText('Possible Aphids')).toBeInTheDocument();
    expect(screen.getByText('Inspect affected leaves.')).toBeInTheDocument();
    expect(screen.getAllByText(/Evidence status:/).length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText(/Wheat pest guide/).length).toBeGreaterThan(0);
  });

  it('labels irrigation as preliminary demonstration guidance', () => {
    render(<MemoryRouter><IrrigationPage /></MemoryRouter>);

    expect(screen.getByText(/not a farm-specific prescription/i)).toBeInTheDocument();
    expect(screen.getByText('PRELIMINARY DEMONSTRATION GUIDANCE')).toBeInTheDocument();
    expect(screen.getByText(/crop stage and soil type/i)).toBeInTheDocument();
  });

  it('describes recommendations without claiming a seven-day schedule and keeps risks separate', () => {
    render(<MemoryRouter><AdvisoryPage /></MemoryRouter>);

    expect(screen.getByText(/not a verified seven-day schedule/i)).toBeInTheDocument();
    expect(screen.getByText('1 recommendations')).toBeInTheDocument();
    expect(screen.getByText(/Preliminary rule indicator - not a diagnosis/)).toBeInTheDocument();
    expect(screen.queryByText('Irrigation recommended')).not.toBeInTheDocument();
  });

  it('labels irrigation guidance as preliminary on the dashboard', () => {
    render(<MemoryRouter><DashboardPage /></MemoryRouter>);

    expect(screen.getByText('PRELIMINARY IRRIGATION GUIDANCE')).toBeInTheDocument();
    expect(screen.getByText(/not a farm-specific prescription/i)).toBeInTheDocument();
  });

  it('labels weather risks as preliminary project indicators, not crop-specific advice', () => {
    apiMocks.farmState.advisory.agents.weather = {
      forecast: { source: 'Isolated fixture', daily_forecast: { time: [] } },
      identified_risks: [{ risk: 'High temperature', severity: 'High', date: '2026-01-01' }],
      risk_interpretation_note: 'These thresholds are preliminary project indicators, not universal agricultural thresholds, not verified crop-specific warnings, and not professional agricultural advice.',
    };

    render(<MemoryRouter><WeatherPage /></MemoryRouter>);

    expect(screen.getByText('PRELIMINARY PROJECT INDICATORS')).toBeInTheDocument();
    expect(screen.getByText(/not universal agricultural thresholds, not verified crop-specific warnings, and not professional agricultural advice/i)).toBeInTheDocument();
    expect(screen.getByText(/High temperature - Preliminary project indicator - High/)).toBeInTheDocument();
  });

  it('distinguishes unavailable rainfall from zero and positive rainfall in the forecast chart', () => {
    apiMocks.farmState.advisory.agents.weather = {
      forecast: { source: 'Isolated fixture', daily_forecast: {
        time: ['2026-01-01', '2026-01-02', '2026-01-03'],
        precipitation_sum: [null, 0, 2.5],
      } },
      identified_risks: [],
    };

    const { container } = render(<MemoryRouter><WeatherPage /></MemoryRouter>);
    const rows = container.querySelectorAll('.forecast-row');

    expect(rows).toHaveLength(3);
    expect(rows[0].lastElementChild).toHaveTextContent('—');
    expect(rows[0].querySelector('.rain-track i')).toBeNull();
    expect(rows[1].lastElementChild).toHaveTextContent('0 mm');
    expect(rows[1].querySelector('.rain-track i')).toHaveStyle({ width: '0%' });
    expect(rows[2].lastElementChild).toHaveTextContent('2.5 mm');
    expect(rows[2].querySelector('.rain-track i')).toHaveStyle({ width: '100%' });
  });
});

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';

const { apiMocks } = vi.hoisted(() => ({
  apiMocks: {
    observations: vi.fn(),
    advisories: vi.fn(),
    observationsAll: vi.fn(),
    advisoriesAll: vi.fn(),
    errorMessage: vi.fn(),
    registerFarm: vi.fn(),
    registerAccount: vi.fn(),
    loginAccount: vi.fn(),
    requestMyFarms: vi.fn(),
    weather: vi.fn(),
    updateFarmProfile: vi.fn(),
    requestAdvisory: vi.fn(),
    exitFarmSession: vi.fn(),
    farmState: { farm: { farm_id: 'farm-browser-selected' }, advisory: null, setCredentialFarmId: vi.fn(), setDemoMode: vi.fn() },
  },
}));

vi.mock('../context/FarmContext.jsx', () => ({
  useFarm: () => apiMocks.farmState,
}));

vi.mock('../services/api.js', () => ({
  requestAllFarmObservations: apiMocks.observationsAll,
  requestAllFarmAdvisories: apiMocks.advisoriesAll,
  apiErrorMessage: apiMocks.errorMessage,
  registerFarm: apiMocks.registerFarm,
  registerAccount: apiMocks.registerAccount,
  loginAccount: apiMocks.loginAccount,
  requestMyFarms: apiMocks.requestMyFarms,
  requestFarmWeather: apiMocks.weather,
  updateFarmProfile: apiMocks.updateFarmProfile,
  exitFarmSession: apiMocks.exitFarmSession,
  requestAdvisory: apiMocks.requestAdvisory,
}));

import { HistoryPage, SoilPage, CropPage, IrrigationPage, AdvisoryPage, DashboardPage, WeatherPage, AuthPage, SettingsPage, AssessmentPage, FarmProfilePage } from './Pages.jsx';
import { MemoryRouter, useLocation } from 'react-router-dom';

describe('Farm History page', () => {
  beforeEach(() => {
    apiMocks.observations.mockReset();
    apiMocks.advisories.mockReset();
    apiMocks.observationsAll.mockReset();
    apiMocks.advisoriesAll.mockReset();
    apiMocks.errorMessage.mockReset();
    apiMocks.errorMessage.mockReturnValue('History request failed.');
  });

  it('shows a loading state while both MongoDB requests are pending', async () => {
    let resolveObservations;
    let resolveAdvisories;
    apiMocks.observationsAll.mockReturnValue(new Promise((resolve) => { resolveObservations = resolve; }));
    apiMocks.advisoriesAll.mockReturnValue(new Promise((resolve) => { resolveAdvisories = resolve; }));

    render(<HistoryPage />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading farm history');

    await act(async () => {
      resolveObservations([]);
      resolveAdvisories([]);
    });
  });

  it('shows an honest empty state when MongoDB returns no records', async () => {
    apiMocks.observationsAll.mockResolvedValue([]);
    apiMocks.advisoriesAll.mockResolvedValue([]);

    render(<HistoryPage />);

    expect(await screen.findByText(/No saved observations were found for this farm\./)).toBeInTheDocument();
    expect(screen.getByText('No saved advisories were found for this farm.')).toBeInTheDocument();
  });

  it('renders only stored observation and advisory values', async () => {
    apiMocks.observationsAll.mockResolvedValue([{
      observation_id: 'obs-1',
      created_at: '2026-01-02T03:04:00Z',
      observation: { crop_name: 'Rice', growth_stage: 'Flowering', soil_moisture: 28, symptoms: ['leaf spots'] },
    }]);
    apiMocks.advisoriesAll.mockResolvedValue([{
      advisory_id: 'adv-1',
      created_at: '2026-01-02T03:05:00Z',
      advisory: { weekly_action_list: ['Inspect drainage'], risk_alerts: [{ risk: 'Waterlogging', severity: 'moderate' }] },
    }]);

    render(<HistoryPage />);

    expect(await screen.findByText('Rice')).toBeInTheDocument();
    expect(screen.getByText('28')).toBeInTheDocument();
    expect(screen.getByText('Inspect drainage')).toBeInTheDocument();
    expect(screen.getByText('Waterlogging · moderate')).toBeInTheDocument();
  });

  it('compares comparable historical readings and shows the saved forecast period', async () => {
    apiMocks.observationsAll.mockResolvedValue([
      { observation_id: 'obs-new', created_at: '2026-02-02T00:00:00Z', observation: { assessment_id: 'a-new', crop_name: 'Rice', soil_moisture: 36, soil_ph: 6.5 } },
      { observation_id: 'obs-old', created_at: '2026-02-01T00:00:00Z', observation: { assessment_id: 'a-old', crop_name: 'Rice', soil_moisture: 30, soil_ph: 6.5 } },
    ]);
    apiMocks.advisoriesAll.mockResolvedValue([
      { advisory_id: 'adv-new', created_at: '2026-02-02T00:01:00Z', advisory: { assessment_id: 'a-new', agents: { weather: { forecast: { source: 'Stored provider', fetched_at: '2026-02-02T00:00:00Z', daily_forecast: { time: ['2026-02-03'], precipitation_sum: [2] } } } } } },
      { advisory_id: 'adv-old', created_at: '2026-02-01T00:01:00Z', advisory: { assessment_id: 'a-old' } },
    ]);

    render(<HistoryPage />);
    expect(await screen.findByText(/Change since previous recorded assessment/)).toHaveTextContent('Soil moisture 30 → 36 (+6)');
    expect(screen.getByText(/Historical weather forecast/)).toBeInTheDocument();
    expect(screen.getByText(/2026-02-03/)).toBeInTheDocument();
    expect(screen.getByText(/Stored provider/)).toBeInTheDocument();
  });

  it('shows a genuine service error', async () => {
    const failure = new Error('unavailable');
    failure.response = { status: 503 };
    apiMocks.observationsAll.mockRejectedValue(failure);
    apiMocks.advisoriesAll.mockResolvedValue([]);

    render(<HistoryPage />);

    expect(await screen.findByRole('alert')).toHaveTextContent('History request failed.');
    expect(screen.getByRole('alert')).toHaveTextContent('History could not be loaded.');
  });

  it('shows a distinct access-denied state', async () => {
    const failure = new Error('credential unavailable');
    failure.response = { status: 401 };
    apiMocks.observationsAll.mockRejectedValue(failure);
    apiMocks.advisoriesAll.mockResolvedValue([]);
    apiMocks.errorMessage.mockReturnValue('Farm access is unavailable in this browser.');

    render(<HistoryPage />);

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Farm access unavailable.'));
    expect(screen.getByRole('alert')).toHaveTextContent('Sign in again to view this farm’s history.');
  });
});

describe('Demo access and account registration UI', () => {
  beforeEach(() => {
    apiMocks.registerFarm.mockReset();
    apiMocks.registerAccount.mockReset();
    apiMocks.loginAccount.mockReset();
    apiMocks.requestMyFarms.mockReset();
    apiMocks.weather.mockReset();
    apiMocks.updateFarmProfile.mockReset();
    apiMocks.requestAdvisory.mockReset();
    apiMocks.exitFarmSession.mockReset();
    apiMocks.errorMessage.mockReturnValue('Farm access is unavailable in this browser.');
    apiMocks.farmState = {
      farm: { farm_id: 'farm-browser-selected' },
      advisory: null,
      setFarm: vi.fn(),
      setAdvisory: vi.fn(),
      setCredentialFarmId: vi.fn(),
      selectFarm: vi.fn(),
      clearFarmSelection: vi.fn(),
      setDemoMode: vi.fn(),
      setAccount: vi.fn(),
      setFarms: vi.fn(),
      farms: [],
    };
  });

  it('registers the selected farm with the backend before navigating to the dashboard', async () => {
    apiMocks.registerFarm.mockResolvedValue({ farm_id: 'farm-browser-selected', registered: true });
    function Location() { return <output>{useLocation().pathname}</output>; }
    render(<MemoryRouter initialEntries={['/login']}><AuthPage /><Location /></MemoryRouter>);

    screen.getByRole('button', { name: 'Continue with demo access' }).click();

    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('/dashboard'));
    expect(apiMocks.registerFarm).toHaveBeenCalledWith('farm-browser-selected');
    expect(apiMocks.farmState.setCredentialFarmId).toHaveBeenCalledWith('farm-browser-selected');
    expect(apiMocks.farmState.setDemoMode).toHaveBeenCalledWith(true);
  });

  it('shows a clear error and stays on login when backend demo access fails', async () => {
    apiMocks.registerFarm.mockRejectedValue(new Error('offline'));
    function Location() { return <output>{useLocation().pathname}</output>; }
    render(<MemoryRouter initialEntries={['/login']}><AuthPage /><Location /></MemoryRouter>);

    screen.getByRole('button', { name: 'Continue with demo access' }).click();

    expect(await screen.findByText('Farm access is unavailable in this browser.')).toBeInTheDocument();
    expect(screen.getByText('/login')).toBeInTheDocument();
    expect(apiMocks.farmState.setCredentialFarmId).not.toHaveBeenCalled();
  });

  it('validates missing registration fields without sending passwords', async () => {
    render(<MemoryRouter><AuthPage signup /></MemoryRouter>);

    screen.getByRole('button', { name: 'Create account' }).click();

    expect(await screen.findByRole('alert')).toHaveTextContent('Enter both your email address and password.');
    expect(apiMocks.registerAccount).not.toHaveBeenCalled();
  });

  it('submits login and routes to the selected owned farm', async () => {
    apiMocks.loginAccount.mockResolvedValue({ user_id: 'user-1', email: 'farmer@example.com' });
    apiMocks.requestMyFarms.mockResolvedValue([{ farm_id: 'farm-owned' }]);
    function Location() { return <output>{useLocation().pathname}</output>; }
    render(<MemoryRouter initialEntries={['/login']}><AuthPage /><Location /></MemoryRouter>);
    fireEvent.change(screen.getByLabelText('Email address'), { target: { value: 'farmer@example.com' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'a secure password' } });
    screen.getByRole('button', { name: 'Sign in' }).click();

    await waitFor(() => expect(screen.getByText('/dashboard')).toBeInTheDocument());
    expect(apiMocks.loginAccount).toHaveBeenCalledWith('farmer@example.com', 'a secure password');
    expect(apiMocks.farmState.selectFarm).toHaveBeenCalledWith('farm-owned');
  });

  it('lets an account with no farms reach Add Farm without silently registering one', async () => {
    apiMocks.loginAccount.mockResolvedValue({ user_id: 'user-1', email: 'farmer@example.com' });
    apiMocks.requestMyFarms.mockResolvedValue([]);
    apiMocks.farmState = { ...apiMocks.farmState, farm: { farm_id: 'deleted-farm' }, credentialFarmId: 'deleted-farm' };
    function Location() { return <output>{useLocation().pathname}</output>; }
    render(<MemoryRouter initialEntries={['/login']}><AuthPage /><Location /></MemoryRouter>);
    fireEvent.change(screen.getByLabelText('Email address'), { target: { value: 'farmer@example.com' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'a secure password' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    await waitFor(() => expect(screen.getByText('/dashboard')).toBeInTheDocument());
    expect(apiMocks.registerFarm).not.toHaveBeenCalled();
    expect(apiMocks.farmState.setFarms).toHaveBeenCalledWith([]);
    expect(apiMocks.farmState.clearFarmSelection).toHaveBeenCalledWith('deleted-farm');
  });

  it('registers an account and creates its first owned farm', async () => {
    apiMocks.registerAccount.mockResolvedValue({ user_id: 'user-1', email: 'farmer@example.com' });
    apiMocks.requestMyFarms.mockImplementation(async () => apiMocks.registerFarm.mock.calls.length ? [{ farm_id: apiMocks.registerFarm.mock.calls[0][0] }] : []);
    apiMocks.registerFarm.mockResolvedValue({ registered: true });
    render(<MemoryRouter><AuthPage signup /></MemoryRouter>);
    fireEvent.change(screen.getByLabelText('Email address'), { target: { value: 'farmer@example.com' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'a secure password' } });
    fireEvent.change(screen.getByLabelText('Confirm password'), { target: { value: 'a secure password' } });
    screen.getByRole('button', { name: 'Create account' }).click();

    await waitFor(() => expect(apiMocks.farmState.selectFarm).toHaveBeenCalledWith(expect.stringMatching(/^farm-/)));
    expect(apiMocks.registerAccount).toHaveBeenCalledWith('farmer@example.com', 'a secure password');
    expect(apiMocks.registerFarm).toHaveBeenCalledWith(expect.stringMatching(/^farm-/));
  });

  it('creates and selects an added farm only after its assessment is submitted', async () => {
    apiMocks.registerFarm.mockResolvedValue({ farm_id: 'farm-new', registered: true });
    apiMocks.updateFarmProfile.mockResolvedValue({ saved: true });
    apiMocks.requestAdvisory.mockResolvedValue({ status: 'completed', weekly_action_list: [] });
    apiMocks.requestMyFarms.mockResolvedValue([{ farm_id: 'farm-custom_01' }]);
    apiMocks.farmState = { ...apiMocks.farmState, farm: { farm_id: '' }, account: { user_id: 'user-1' }, credentialFarmId: null };
    function Location() { return <output>{useLocation().pathname}</output>; }
    render(<MemoryRouter initialEntries={[{ pathname: '/assessment', state: { createFarm: true, farmId: 'farm-new' } }]}><AssessmentPage /><Location /></MemoryRouter>);

    expect(screen.getByText('The farm will be registered when you submit this assessment.')).toBeInTheDocument();
    expect(apiMocks.registerFarm).not.toHaveBeenCalled();
    for (const [label, value] of [
      ['Latitude (−90 to 90)', '12.5'], ['Longitude (−180 to 180)', '77.2'],
      ['Soil moisture (%)', '35'], ['Soil pH', '6.5'], ['Nitrogen', '1'],
      ['Phosphorus', '2'], ['Potassium', '3'], ['Farm ID', 'farm-custom_01'], ['Crop name', 'Rice'], ['Growth stage', 'Flowering'],
      ['Soil type (optional)', 'Loam'],
    ]) fireEvent.change(screen.getByLabelText(label), { target: { value } });
    fireEvent.click(screen.getByRole('button', { name: /Generate advisory/ }));

    await waitFor(() => expect(screen.getByText('/dashboard')).toBeInTheDocument());
    expect(apiMocks.registerFarm).toHaveBeenCalledWith('farm-custom_01');
    expect(apiMocks.updateFarmProfile).toHaveBeenCalledWith('farm-custom_01', expect.objectContaining({ farm_id: 'farm-custom_01', crop_name: 'Rice', soil_type: 'Loam' }));
    expect(apiMocks.requestAdvisory).toHaveBeenCalledWith(expect.objectContaining({ farm_id: 'farm-custom_01', crop_name: 'Rice' }));
    expect(apiMocks.requestMyFarms).toHaveBeenCalledOnce();
    expect(apiMocks.farmState.setFarms).toHaveBeenCalledWith([{ farm_id: 'farm-custom_01' }]);
    expect(apiMocks.farmState.selectFarm).toHaveBeenCalledWith('farm-custom_01', expect.objectContaining({ crop_name: 'Rice', soil_type: 'Loam' }));
    expect(apiMocks.registerFarm.mock.invocationCallOrder[0]).toBeLessThan(apiMocks.updateFarmProfile.mock.invocationCallOrder[0]);
    expect(apiMocks.updateFarmProfile.mock.invocationCallOrder[0]).toBeLessThan(apiMocks.requestAdvisory.mock.invocationCallOrder[0]);
  });

  it('saves a selected new farm profile using that farm ID', async () => {
    apiMocks.farmState = { ...apiMocks.farmState, farm: { farm_id: 'farm-new', crop_name: 'Rice' }, account: { user_id: 'user-1' }, credentialFarmId: 'farm-new', farms: [{ farm_id: 'farm-new' }] };
    render(<MemoryRouter><FarmProfilePage /></MemoryRouter>);
    fireEvent.click(screen.getByRole('button', { name: 'Save farm profile' }));
    await waitFor(() => expect(apiMocks.updateFarmProfile).toHaveBeenCalledWith('farm-new', expect.objectContaining({ crop_name: 'Rice' })));
  });

  it('offers the Add Farm workflow instead of an unusable profile form when no farm exists', async () => {
    apiMocks.farmState = { ...apiMocks.farmState, farm: { farm_id: '' }, account: { user_id: 'user-1' }, farms: [] };
    function Location() { return <output>{useLocation().pathname}</output>; }
    render(<MemoryRouter initialEntries={['/farm']}><FarmProfilePage /><Location /></MemoryRouter>);
    expect(screen.getByText(/Create a farm with your first assessment/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Save farm profile' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Add farm' }));

    await waitFor(() => expect(screen.getByText('/assessment')).toBeInTheDocument());
    expect(apiMocks.registerFarm).not.toHaveBeenCalled();
  });
});

describe('agricultural interpretation labels', () => {
  beforeEach(() => {
    apiMocks.weather.mockResolvedValue({ source: 'Open-Meteo', location: { latitude: 12, longitude: 77 }, daily_forecast: { time: [] } });
    apiMocks.farmState = {
      farm: { farm_id: 'farm-test', crop_name: 'Rice', growth_stage: 'Flowering', latitude: 12, longitude: 77 },
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
            next_steps: ['Record the soil-test method and repeat the same measurement.'],
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
          schedule: [{ day: 'Days 2–3', action: 'Recheck moisture after rainfall.' }],
          soil_moisture: 20,
          expected_rainfall_mm: 0,
        },
        weather_summary: {},
      },
    };
  });

  it('shows soil readings, possible issues and useful next actions', () => {
    render(<MemoryRouter><SoilPage /></MemoryRouter>);

    expect(screen.getByText('Measurements')).toBeInTheDocument();
    expect(screen.getByText('Possible soil issues')).toBeInTheDocument();
    expect(screen.getByText('What to do')).toBeInTheDocument();
    expect(screen.getByText(/Units and soil test method were not supplied/)).toBeInTheDocument();
  });

  it('shows unavailable measurements and empty interpretations without inventing values', () => {
    apiMocks.farmState = {
      farm: { farm_id: 'farm-test' },
      advisory: { agents: { soil: { soil_report: {} } } },
    };

    render(<MemoryRouter><SoilPage /></MemoryRouter>);

    expect(screen.getAllByText('—')).toHaveLength(5);
    expect(screen.getByText(/soil-test units and method/i)).toBeInTheDocument();
    expect(screen.queryByText('No relevant knowledge sources were returned.')).not.toBeInTheDocument();
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
    expect(screen.queryByText(/Original reference unavailable/)).not.toBeInTheDocument();
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
    expect(screen.getAllByText(/Wheat pest guide/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Wheat pest guide/).length).toBeGreaterThan(0);
  });

  it('shows an irrigation action and a practical watering check schedule', () => {
    render(<MemoryRouter><IrrigationPage /></MemoryRouter>);

    expect(screen.getByText('Watering plan')).toBeInTheDocument();
    expect(screen.getByText('This week')).toBeInTheDocument();
    expect(screen.getByText(/Days 2–3/)).toBeInTheDocument();
  });

  it('shows the seven-day plan while keeping findings separate from actions', () => {
    apiMocks.farmState.advisory.weekly_action_plan = [{ day: 'Today', action: 'Check the soil', priority: 'high' }];
    apiMocks.farmState.advisory.agents.irrigation = { recommended_action: 'Irrigation recommended' };
    render(<MemoryRouter><AdvisoryPage /></MemoryRouter>);

    expect(screen.getByText('Your seven-day farm plan')).toBeInTheDocument();
    expect(screen.getByText('Actions for the next seven days')).toBeInTheDocument();
    expect(screen.getByText('Check the soil')).toBeInTheDocument();
    expect(screen.getByText('AI-generated guidance based on available farm data and agricultural sources. Actual results may vary; consult a local agricultural expert before major decisions.')).toHaveClass('ai-notice');
  });

  it('shows a concise watering summary on the dashboard', () => {
    render(<MemoryRouter><DashboardPage /></MemoryRouter>);

    expect(screen.getByText('Irrigation recommended')).toBeInTheDocument();
    expect(screen.getByText(/View watering plan/)).toBeInTheDocument();
  });

  it('labels weather risks as preliminary project indicators, not crop-specific advice', () => {
    apiMocks.farmState.advisory.agents.weather = {
      forecast: { source: 'Isolated fixture', daily_forecast: { time: [] } },
      identified_risks: [{ risk: 'High temperature', severity: 'High', date: '2026-01-01' }],
      risk_interpretation_note: 'These thresholds are preliminary project indicators, not universal agricultural thresholds, not verified crop-specific warnings, and not professional agricultural advice.',
    };

    render(<MemoryRouter><WeatherPage /></MemoryRouter>);

    expect(screen.getByText('Potential risks')).toBeInTheDocument();
    expect(screen.getByText(/High temperature/)).toBeInTheDocument();
  });

  it('formats weather timestamps and separates impact, risks and actions', async () => {
    apiMocks.farmState.advisory.agents.weather = {
      weather_summary: 'Hot weather may increase water loss for this crop.',
      identified_risks: [{ risk: 'High temperature', date: '2026-11-15', impact: 'Heat may stress the crop.', recommended_action: 'Check root-zone moisture early.' }],
    };
    apiMocks.weather.mockResolvedValue({ source: 'Open-Meteo', current_conditions: { time: '2026-11-15T17:45', temperature_2m: 31 }, daily_forecast: { time: [] } });
    render(<MemoryRouter><WeatherPage /></MemoryRouter>);

    expect(await screen.findByText(/15 November 2026/)).toBeInTheDocument();
    expect(screen.getByText('31').parentElement).toHaveTextContent('31°C');
    expect(screen.getByText('Weather impact')).toBeInTheDocument();
    expect(screen.getByText('Potential risks')).toBeInTheDocument();
    expect(screen.getByText('Recommended actions')).toBeInTheDocument();
    expect(screen.getByText('Check root-zone moisture early.')).toBeInTheDocument();
  });

  it('distinguishes unavailable rainfall from zero and positive rainfall in the forecast chart', async () => {
    apiMocks.farmState = { farm: { farm_id: 'farm-weather', latitude: 12, longitude: 77 }, advisory: null };
    apiMocks.weather.mockResolvedValue({
      source: 'Open-Meteo', location: { latitude: 12, longitude: 77 }, daily_forecast: {
        time: ['2026-01-01', '2026-01-02', '2026-01-03'],
        precipitation_sum: [null, 0, 2.5],
      },
    });

    const { container } = render(<MemoryRouter><WeatherPage /></MemoryRouter>);
    expect(await screen.findByText(/Current forecast - Open-Meteo/)).toBeInTheDocument();
    const rows = container.querySelectorAll('.forecast-row');

    expect(rows).toHaveLength(3);
    expect(rows[0].lastElementChild).toHaveTextContent('-');
    expect(rows[0].querySelector('.rain-track i')).toBeNull();
    expect(rows[1].lastElementChild).toHaveTextContent('0 mm');
    expect(rows[1].querySelector('.rain-track i')).toHaveStyle({ width: '0%' });
    expect(rows[2].lastElementChild).toHaveTextContent('2.5 mm');
    expect(rows[2].querySelector('.rain-track i')).toHaveStyle({ width: '100%' });
  });

  it('loads weather for the selected farm even before any assessment', async () => {
    apiMocks.farmState = { farm: { farm_id: 'farm-weather', latitude: 12, longitude: 77 }, advisory: null };
    apiMocks.weather.mockResolvedValue({ source: 'Open-Meteo', location: { latitude: 12, longitude: 77 }, daily_forecast: { time: ['2026-01-01'], temperature_2m_max: [30], temperature_2m_min: [20], precipitation_sum: [0] } });
    render(<MemoryRouter><WeatherPage /></MemoryRouter>);
    expect(await screen.findByText(/Current forecast - Open-Meteo/)).toBeInTheDocument();
    expect(apiMocks.weather).toHaveBeenCalledWith('farm-weather', 12, 77);
  });

  it('does not present a saved assessment forecast as live after a provider failure', async () => {
    apiMocks.farmState = { farm: { farm_id: 'farm-weather', latitude: 12, longitude: 77 }, advisory: { agents: { weather: { forecast: { source: 'Saved Open-Meteo snapshot', daily_forecast: { time: ['2026-01-01'] } }, identified_risks: [] } } }, farmAdvisories: [{ created_at: '2026-01-01T12:00:00Z' }] };
    apiMocks.weather.mockRejectedValue(new Error('network unavailable'));
    apiMocks.errorMessage.mockReturnValue('Weather is temporarily unavailable.');
    render(<MemoryRouter><WeatherPage /></MemoryRouter>);
    expect(await screen.findByRole('alert')).toHaveTextContent('Weather is temporarily unavailable.');
    expect(screen.getByText('Live forecast unavailable')).toBeInTheDocument();
    expect(screen.getByText(/Weather saved with assessment/)).toBeInTheDocument();
  });

  it('shows history entries in chronological order', async () => {
    apiMocks.observationsAll.mockResolvedValue([
      { observation_id: 'obs-new', created_at: '2026-01-03T10:00:00Z', observation: { assessment_id: 'assess-new', crop_name: 'Rice', growth_stage: 'Flowering', soil_moisture: 24 } },
      { observation_id: 'obs-old', created_at: '2026-01-01T10:00:00Z', observation: { assessment_id: 'assess-old', crop_name: 'Rice', growth_stage: 'Tillering', soil_moisture: 32 } },
    ]);
    apiMocks.advisoriesAll.mockResolvedValue([
      { advisory_id: 'adv-new', created_at: '2026-01-03T10:01:00Z', advisory: { assessment_id: 'assess-new', agents: { pest_disease: { crop_report: { crop_name: 'Rice', growth_stage: 'Flowering' } } }, weekly_action_list: ['Inspect crop'] } },
      { advisory_id: 'adv-old', created_at: '2026-01-01T10:01:00Z', advisory: { assessment_id: 'assess-old', status: 'partial', history_context: { previous_observations_count: 12, observations_supplied_to_agents: 10 }, agent_failures: [{ agent: 'weather', message: 'Weather output was unavailable.' }], agents: { soil: { agent: 'Soil Agent', status: 'partial', quality_status: 'degraded' }, pest_disease: { crop_report: { crop_name: 'Rice', growth_stage: 'Tillering' } } }, weekly_action_list: ['Check field'] } },
    ]);
    const { container } = render(<HistoryPage />);
    await screen.findByText('Check field');
    const records = [...container.querySelectorAll('.history-record-list > .history-record')];
    expect(records).toHaveLength(2);
    expect(records[0]).toHaveTextContent('Tillering');
    expect(records[1]).toHaveTextContent('Flowering');
    expect(records[0]).toHaveTextContent('Weekly advisory status: partial');
    expect(records[0]).toHaveTextContent('12; supplied to the agents: 10');
    expect(screen.getByText(/Soil Agent: partial, degraded analysis/i)).toBeInTheDocument();
    expect(screen.getByText(/Weather output was unavailable/i)).toBeInTheDocument();
  });

  it('does not offer a local toggle to enable demo access in Settings', () => {
    apiMocks.farmState = { farm: { farm_id: 'farm-settings' }, advisory: null, demoMode: false, setAdvisory: vi.fn(), account: null };
    render(<MemoryRouter><SettingsPage /></MemoryRouter>);
    expect(screen.queryByRole('button', { name: /enable demo access/i })).not.toBeInTheDocument();
    expect(screen.getByText(/must be established through the backend from the Login page/i)).toBeInTheDocument();
  });

  it('labels partial advisories and identifies failed agents while retaining actions', () => {
    apiMocks.farmState = {
      advisory: {
        status: 'partial',
        agent_failures: [{ agent: 'weather', message: 'Weather output was unavailable.' }],
        weekly_action_list: ['Inspect soil', 'Recheck before irrigating'],
        agents: { weather: { status: 'failed', error: 'Weather output was unavailable.' }, soil: { status: 'completed' }, irrigation: { status: 'completed', recommended_action: 'Recheck before irrigating' } },
      },
    };
    render(<MemoryRouter><AdvisoryPage /></MemoryRouter>);
    expect(screen.getByRole('status')).toHaveTextContent('Some advice is unavailable');
    expect(screen.getByRole('status')).toHaveTextContent('Weather');
    expect(screen.getAllByText('Recheck before irrigating').length).toBeGreaterThan(0);
  });

  it('does not display a stale partial warning when all latest farm agents succeeded', () => {
    apiMocks.farmState = {
      farm: { farm_id: 'farm-latest' },
      farmAdvisories: [], farmObservations: [],
      advisory: {
        status: 'partial',
        agent_failures: [{ agent: 'weather', message: 'Old weather failure.' }],
        agents: {
          weather: { status: 'completed', forecast: { daily_forecast: {} } },
          soil: { status: 'completed' },
          pest_disease: { status: 'success' },
          irrigation: { status: 'completed' },
        },
      },
    };
    render(<MemoryRouter><DashboardPage /></MemoryRouter>);
    expect(screen.queryByText(/completed partially/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Old weather failure/)).not.toBeInTheDocument();
  });

  it('distinguishes a degraded agent result from an unavailable agent', () => {
    apiMocks.farmState = {
      advisory: {
        status: 'partial',
        agent_failures: [],
        agent_degradations: [{ agent: 'Soil Agent', reason: 'provider_error' }],
        agents: { soil: { status: 'completed', quality_status: 'degraded' } },
      },
    };
    render(<MemoryRouter><AdvisoryPage /></MemoryRouter>);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.queryByText(/Unavailable agents/)).not.toBeInTheDocument();
  });
});

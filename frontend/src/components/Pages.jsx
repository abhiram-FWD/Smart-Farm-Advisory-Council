import { useEffect, useMemo, useState } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { useFarm } from '../context/FarmContext.jsx';
import { apiErrorMessage, loginAccount, registerAccount, registerFarm, requestAdvisory, requestAllFarmAdvisories, requestAllFarmObservations, requestFarmWeather, requestMyFarms, updateFarmProfile } from '../services/api.js';
import { AiNotice, Card, EmptyState, List, Meter, PageTitle, Sources } from './Primitives.jsx';
import { daysSincePlanting, growthStages } from '../utils/cropLifecycle.js';

function AdvisoryEmpty() { return <EmptyState>Generate an assessment to see recommendations based on this farm’s current soil, crop and forecast information.</EmptyState>; }
function sourceNames(sources = []) { return [...new Set(sources.map((source) => { const value = typeof source === 'string' ? source : source.title && source.title !== 'Unavailable' ? source.title : source.source || source.filename || 'Agricultural guide'; return String(value).replace(/\\/g, '/').split('/').pop().replace(/\.txt$/i, '').replaceAll('_', ' '); }))].join(', '); }
function agentLabel(value) {
  return ({ weather: 'Weather Agent', soil: 'Soil Agent', pest_disease: 'Pest and Disease Agent', irrigation: 'Irrigation Planner' })[value] || value;
}
function failedAgentMessages(advisory) {
  const failures = advisory?.agent_failures || [];
  return ['weather', 'soil', 'pest_disease', 'irrigation']
    .filter((name) => advisory?.agents?.[name]?.status === 'failed')
    .map((name) => {
      return agentLabel(name).replace(' Agent', '');
    });
}
function FarmDetails({ farm }) { const hasCoordinates = farm.latitude != null && farm.longitude != null && farm.latitude !== '' && farm.longitude !== ''; return <div className="farm-details"><div><span>Farm ID</span><strong>{farm.farm_id || 'Not set'}</strong></div><div><span>Location and coordinates</span><strong>{hasCoordinates ? `${farm.latitude}, ${farm.longitude}` : 'Not provided'}</strong></div><div><span>Crop and variety</span><strong>{[farm.crop_name, farm.crop_variety].filter(Boolean).join(' · ') || 'Not provided'}</strong></div><div><span>Growth stage</span><strong>{farm.growth_stage || 'Not provided'}{farm.growth_stage ? ' · farmer-reported' : ''}</strong></div><div><span>Planting date</span><strong>{farm.planting_date || 'Not recorded'}</strong></div><div><span>Field area</span><strong>{farm.area ? `${farm.area} ${farm.area_unit || ''}`.trim() : 'Not provided'}</strong></div></div>; }

export function DashboardPage() {
  const { advisory, farm, farmAdvisories = [], farmObservations = [], farmDataLoading, farmDataError } = useFarm();
  const latestObservation = farmObservations[0];
  const savedObservation = latestObservation?.observation || {};
  const snapshot = advisory?.assessment_snapshot || savedObservation;
  if (farmDataLoading) return <><PageTitle eyebrow="FARM OVERVIEW" title="Welcome to your farm." /><p className="loading-note" role="status">Loading this farm’s saved assessments…</p></>;
  if (farmDataError && !advisory) return <><PageTitle eyebrow="FARM OVERVIEW" title="Welcome to your farm." /><FarmDetails farm={farm} /><p className="message error-message" role="alert">{farmDataError}</p></>;
  if (!advisory) return <><PageTitle eyebrow="FARM OVERVIEW" title="Your farm" action={<Link className="button" to="/assessment">New assessment</Link>} /><FarmDetails farm={{ ...farm, crop_name: farm.crop_name || savedObservation.crop_name, growth_stage: farm.growth_stage || savedObservation.growth_stage }} /><div className="overview-grid"><Card title="Crop"><p>{farm.crop_name || savedObservation.crop_name || 'Not recorded'}{(farm.growth_stage || savedObservation.growth_stage) ? ` · ${farm.growth_stage || savedObservation.growth_stage}` : ''}</p>{farm.planting_date && <p>{daysSincePlanting(farm.planting_date) ?? '—'} days since planting</p>}</Card><Card title={latestObservation ? 'Latest measurements' : 'Start here'}>{latestObservation ? <div className="measure-grid"><Meter label="Soil moisture" value={savedObservation.soil_moisture} suffix="%"/><Meter label="Soil pH" value={savedObservation.soil_ph}/><Meter label="Nitrogen" value={savedObservation.nitrogen}/><Meter label="Phosphorus" value={savedObservation.phosphorus}/><Meter label="Potassium" value={savedObservation.potassium}/></div> : <><p>Record field conditions to get a farm plan.</p><Link className="button" to="/assessment">New assessment</Link></>}</Card><Card title="Farm history"><p>{farmObservations.length} observations · {farmAdvisories.length} advisories</p><Link className="inline-link" to="/history">View history ↗</Link></Card></div></>;
  const agents = advisory.agents || {};
  const soil = agents.soil || {};
  const crop = agents.pest_disease || {};
  const risks = advisory.risk_alerts || [];
  const actions = advisory.weekly_action_plan || advisory.weekly_action_list || [];
  return <><PageTitle eyebrow="FARM OVERVIEW" title="Your farm" description={crop.crop_report?.crop_name || farm.crop_name || 'Latest assessment'} action={<Link className="button" to="/advisory">View seven-day plan ↗</Link>} />
    {farmDataError && <p className="message error-message" role="alert">{farmDataError}</p>}
    {failedAgentMessages(advisory).length > 0 && <p className="message error-message" role="status">This assessment completed partially. Unavailable agents: {failedAgentMessages(advisory).join('; ')}.</p>}
    <FarmDetails farm={{ ...farm, crop_name: crop.crop_report?.crop_name || farm.crop_name, growth_stage: crop.crop_report?.growth_stage || farm.growth_stage }} />
    <div className="overview-grid"><Card title="Soil measurements"><div className="measure-grid"><Meter label="Moisture" value={soil.soil_report?.moisture ?? snapshot.soil_moisture} suffix="%"/><Meter label="pH" value={soil.soil_report?.ph ?? snapshot.soil_ph}/><Meter label="Nitrogen" value={soil.soil_report?.nitrogen ?? snapshot.nitrogen}/><Meter label="Phosphorus" value={soil.soil_report?.phosphorus ?? snapshot.phosphorus}/><Meter label="Potassium" value={soil.soil_report?.potassium ?? snapshot.potassium}/></div><Link className="inline-link" to="/soil">Soil risks and actions ↗</Link></Card>
      <Card title="Top risks"><List items={risks.slice(0, 4)} empty="No likely risks identified."/><Link className="inline-link" to="/crop">Crop health ↗</Link></Card>
      <Card title="Next actions"><List items={actions.slice(0, 4)} evidenceItems={advisory.weekly_action_evidence}/><Link className="inline-link" to="/advisory">Full seven-day plan ↗</Link></Card>
      <Card title={agents.irrigation?.recommended_action || 'Watering plan'}><p>{agents.irrigation?.reason || 'Check soil moisture and rainfall before watering.'}</p><Link className="inline-link" to="/irrigation">View watering plan ↗</Link></Card>
      <Card title="Weather"><p>{advisory.weather_summary?.source || agents.weather?.forecast?.source || 'Forecast unavailable'} · Rain next 3 days: {advisory.weather_summary?.expected_rainfall_next_3_days_mm ?? '—'} mm</p><Link className="inline-link" to="/weather">Forecast and risks ↗</Link></Card>
      <Card title="Farm history"><p>{farmObservations.length} readings · {farmAdvisories.length} saved plans</p><Link className="inline-link" to="/history">View history ↗</Link></Card>
    </div>
    <AiNotice />
  </>;
}

export function FarmProfilePage() {
  const { farm, setFarm, account, credentialFarmId, farms } = useFarm();
  const navigate = useNavigate();
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function submit(e) { e.preventDefault(); setSaved(false); setError(''); setBusy(true); const data = new FormData(e.currentTarget); const areaValue = data.get('area'); const profile = { latitude: data.get('latitude') === '' ? null : Number(data.get('latitude')), longitude: data.get('longitude') === '' ? null : Number(data.get('longitude')), crop_name: String(data.get('crop_name') || '').trim(), crop_variety: String(data.get('crop_variety') || '').trim(), growth_stage: String(data.get('growth_stage') || '').trim(), growth_stage_source: 'farmer_reported', planting_date: String(data.get('planting_date') || ''), area: areaValue === '' ? null : Number(areaValue), area_unit: String(data.get('area_unit') || ''), soil_type: String(data.get('soil_type') || ''), irrigation_method: String(data.get('irrigation_method') || '') }; try { if (account || credentialFarmId) await updateFarmProfile(farm.farm_id, profile); setFarm({ ...profile, farm_id: farm.farm_id }); setSaved(true); } catch (requestError) { setError(apiErrorMessage(requestError)); } finally { setBusy(false); } }
  return <><PageTitle eyebrow="YOUR FARM" title="Farm profile" description="Farm details are saved with this farm’s history." />
    {account && farms.length === 0 ? <div className="empty-state"><span className="empty-mark">01</span><h2>No farm added yet</h2><p>Create a farm with your first assessment.</p><button className="button" onClick={() => navigate('/assessment', { state: { createFarm: true, farmId: `farm-${crypto.randomUUID()}` } })}>Add farm</button></div> : <>
    <form key={farm.farm_id} className="form-card profile-form" onSubmit={submit}><label>Farm ID<input name="farm_id" required minLength="1" defaultValue={farm.farm_id} readOnly /></label><p className="field-help">Farm profile details are saved for the selected farm and reused by its weather and assessments.</p><div className="form-grid"><label>Latitude<input type="number" name="latitude" min="-90" max="90" step="any" defaultValue={farm.latitude ?? ''} placeholder="e.g. 18.5204" /></label><label>Longitude<input type="number" name="longitude" min="-180" max="180" step="any" defaultValue={farm.longitude ?? ''} placeholder="e.g. 73.8567" /></label><label>Crop name<input name="crop_name" defaultValue={farm.crop_name} placeholder="e.g. Wheat" /></label><label>Variety (optional)<input name="crop_variety" defaultValue={farm.crop_variety} /></label><label>Planting date<input type="date" name="planting_date" defaultValue={farm.planting_date} /></label><label>Current growth stage<select name="growth_stage" defaultValue={farm.growth_stage || ''}><option value="">Select if known</option>{growthStages(farm.crop_name).map((stage) => <option key={stage}>{stage}</option>)}{farm.growth_stage && !growthStages(farm.crop_name).includes(farm.growth_stage) && <option>{farm.growth_stage}</option>}</select><small>Farmer-reported. Stages are not advanced automatically.</small></label><label>Field area (optional)<input type="number" min="0" step="any" name="area" defaultValue={farm.area ?? ''} /></label><label>Area unit<input name="area_unit" defaultValue={farm.area_unit} placeholder="e.g. acres" /></label><label>Soil type (optional)<input name="soil_type" defaultValue={farm.soil_type} /></label><label>Irrigation method (optional)<input name="irrigation_method" defaultValue={farm.irrigation_method} /></label></div><div className="form-actions"><button className="button" disabled={busy}>{busy ? 'Saving…' : 'Save farm profile'}</button>{saved && <span className="success-text" role="status">Farm profile saved.</span>}</div>{error && <p className="message error-message" role="alert">{error}</p>}</form>
    <Card title="Current farm identity"><FarmDetails farm={farm} /></Card></>}
  </>;
}

const blank = { latitude: '', longitude: '', soil_moisture: '', soil_ph: '', nitrogen: '', phosphorus: '', potassium: '', crop_name: '', growth_stage: '', symptoms: '' };
export function AssessmentPage() {
  const { farm, setFarm, setAdvisory, refreshFarmData, credentialFarmId, setCredentialFarmId, account, setFarms, selectFarm } = useFarm();
  const location = useLocation();
  const navigate = useNavigate();
  const createFarm = Boolean(location.state?.createFarm);
  const assessmentFarm = useMemo(() => createFarm ? { farm_id: location.state.farmId, latitude: '', longitude: '', crop_name: '', crop_variety: '', growth_stage: '', planting_date: '', area: null, area_unit: '', soil_type: '', irrigation_method: '' } : farm, [farm, createFarm, location.state]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const initial = useMemo(() => ({ ...blank, latitude: assessmentFarm.latitude, longitude: assessmentFarm.longitude, crop_name: assessmentFarm.crop_name, growth_stage: assessmentFarm.growth_stage }), [assessmentFarm]);
  async function submit(e) {
    e.preventDefault(); setBusy(true); setError(''); setMessage('');
    const form = new FormData(e.currentTarget);
    const areaValue = form.get('area');
    const payload = { farm_id: String(createFarm ? form.get('farm_id') : assessmentFarm.farm_id).trim(), latitude: Number(form.get('latitude')), longitude: Number(form.get('longitude')), soil_moisture: Number(form.get('soil_moisture')), soil_ph: Number(form.get('soil_ph')), nitrogen: Number(form.get('nitrogen')), phosphorus: Number(form.get('phosphorus')), potassium: Number(form.get('potassium')), crop_name: String(form.get('crop_name')).trim(), growth_stage: String(form.get('growth_stage')).trim(), soil_type: String(form.get('soil_type') || '').trim(), symptoms: String(form.get('symptoms') || '').split(',').map((s) => s.trim()).filter(Boolean) };
    const profile = { ...assessmentFarm, ...payload, crop_variety: String(form.get('crop_variety') || '').trim(), planting_date: String(form.get('planting_date') || ''), area: areaValue === '' ? null : Number(areaValue), area_unit: String(form.get('area_unit') || '').trim(), irrigation_method: String(form.get('irrigation_method') || ''), growth_stage_source: 'farmer_reported' };
    try {
      if (!createFarm && credentialFarmId && credentialFarmId !== payload.farm_id) {
        throw new Error('This browser has access to a different farm. Restore that farm ID to continue; credentials are not switched automatically.');
      }
      if (createFarm) {
        try {
          await registerFarm(payload.farm_id);
          setFarms((current) => [...current.filter((item) => item.farm_id !== payload.farm_id), { farm_id: payload.farm_id, profile }]);
        } catch (registrationError) {
          if (registrationError.response?.status !== 409) throw registrationError;
          const ownedFarms = await requestMyFarms();
          if (!ownedFarms.some((item) => item.farm_id === payload.farm_id)) throw registrationError;
          setFarms(ownedFarms);
        }
        selectFarm(payload.farm_id, profile);
        navigate('/assessment', { replace: true, state: { createFarm: false } });
      } else if (!account) {
        const registration = await registerFarm(payload.farm_id);
        setCredentialFarmId(registration.farm_id);
      }
      await updateFarmProfile(payload.farm_id, profile);
      const data = await requestAdvisory(payload);
      if (!['completed', 'partial', 'completed_with_memory_warning'].includes(data.status)) throw new Error(data.error || 'The advisory could not be completed.');
      if (createFarm) {
        const ownedFarms = await requestMyFarms();
        setFarms(ownedFarms);
        selectFarm(payload.farm_id, profile);
        navigate('/dashboard', { replace: true, state: null });
      } else {
        setAdvisory(data); setFarm(profile);
        if (data.status === 'completed' || data.status === 'partial') await refreshFarmData?.(payload.farm_id);
        setMessage(data.status === 'completed_with_memory_warning' ? data.memory_warning : data.status === 'partial' ? 'Assessment saved. Some advice may be unavailable.' : 'Assessment saved.');
      }
    } catch (e2) { setError(e2.message && !e2.response ? e2.message : apiErrorMessage(e2)); }
    finally { setBusy(false); }
  }
  return <><PageTitle eyebrow="NEW ASSESSMENT" title="Record field conditions" description="Enter current measurements and crop signs to get a farm plan." />
    <form key={assessmentFarm.farm_id} className="form-card assessment-form" onSubmit={submit}><div className="form-section"><span className="eyebrow">01 · LOCATION</span><div className="form-grid"><label>Latitude (−90 to 90)<input name="latitude" type="number" required min="-90" max="90" step="any" defaultValue={initial.latitude} placeholder="e.g. 18.5204" /></label><label>Longitude (−180 to 180)<input name="longitude" type="number" required min="-180" max="180" step="any" defaultValue={initial.longitude} placeholder="e.g. 73.8567" /></label></div></div>
      <div className="form-section"><span className="eyebrow">02 · SOIL MEASUREMENTS</span><p className="field-help">Enter your measured values. Nutrient units depend on your soil test report.</p><div className="form-grid three"><label>Soil moisture (%)<input name="soil_moisture" type="number" required min="0" step="any" defaultValue="" /></label><label>Soil pH<input name="soil_ph" type="number" required min="0" max="14" step="any" defaultValue="" /></label><label>Nitrogen<input name="nitrogen" type="number" required min="0" step="any" defaultValue="" /></label><label>Phosphorus<input name="phosphorus" type="number" required min="0" step="any" defaultValue="" /></label><label>Potassium<input name="potassium" type="number" required min="0" step="any" defaultValue="" /></label></div></div>
      <div className="form-section"><span className="eyebrow">03 · CROP OBSERVATIONS</span><div className="form-grid">{createFarm && <label>Farm ID<input name="farm_id" required minLength="1" maxLength="64" pattern="[A-Za-z0-9][A-Za-z0-9_-]{0,63}" title="Use 1–64 letters, numbers, hyphens or underscores; start with a letter or number." defaultValue={assessmentFarm.farm_id} /></label>}<label>Crop name<input name="crop_name" required minLength="1" defaultValue={initial.crop_name} placeholder="e.g. Rice" /></label><label>Growth stage<input name="growth_stage" required minLength="1" defaultValue={initial.growth_stage} placeholder="e.g. Flowering" /></label><label>Crop variety (optional)<input name="crop_variety" defaultValue={assessmentFarm.crop_variety || ''} /></label><label>Planting date (optional)<input name="planting_date" type="date" defaultValue={assessmentFarm.planting_date || ''} /></label><label>Field area (optional)<input name="area" type="number" min="0" step="any" defaultValue={assessmentFarm.area ?? ''} /></label><label>Area unit<input name="area_unit" defaultValue={assessmentFarm.area_unit || ''} placeholder="e.g. acres" /></label><label>Soil type (optional)<input name="soil_type" defaultValue={assessmentFarm.soil_type || ''} /></label><label>Irrigation method (optional)<input name="irrigation_method" defaultValue={assessmentFarm.irrigation_method || ''} /></label><label className="full-width">Current symptoms <span className="optional-label">Optional</span><input name="symptoms" placeholder="Separate symptoms with commas" /></label></div></div>
      <div className="form-submit-row"><div><strong>Farm ID</strong><span>{createFarm ? 'Enter the farm ID above.' : assessmentFarm.farm_id}</span><small>{createFarm ? 'The farm will be registered when you submit this assessment.' : 'This ID stays the same across assessments in this browser.'}</small></div><button className="button" disabled={busy}>{busy ? <><span className="spinner"/> Coordinating agents…</> : <>Generate advisory <span aria-hidden="true">↗</span></>}</button></div>
      {busy && <p className="loading-note" role="status">Checking weather and preparing your farm plan…</p>}
      {error && <div className="message error-message" role="alert">{error}</div>}{message && <div className="message success-message" role="status">{message} <Link to="/advisory">View the advisory ↗</Link></div>}
    </form>
  </>;
}

export function WeatherPage() {
  const { advisory, farm, farmAdvisories = [] } = useFarm();
  const [liveForecast, setLiveForecast] = useState(null);
  const [loading, setLoading] = useState(false);
  const [weatherError, setWeatherError] = useState('');
  useEffect(() => {
    let active = true;
    if ([farm.latitude, farm.longitude].some((coordinate) => coordinate == null || coordinate === '')) { setLiveForecast(null); setWeatherError('Add coordinates to this farm profile to load its weather forecast.'); setLoading(false); return undefined; }
    setLoading(true); setWeatherError(''); setLiveForecast(null);
    requestFarmWeather(farm.farm_id, farm.latitude, farm.longitude).then((data) => { if (active) setLiveForecast(data); }).catch((error) => { if (active) setWeatherError(apiErrorMessage(error)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [farm.farm_id, farm.latitude, farm.longitude]);
  const result = advisory?.agents?.weather || {};
  const forecast = liveForecast || {};
  const daily = forecast.daily_forecast || {};
  const savedForecast = result.forecast || {};
  const savedDaily = savedForecast.daily_forecast || {};
  const assessmentDate = farmAdvisories[0]?.created_at;
  const rain = daily.precipitation_sum;
  const liveRainTotal = Array.isArray(rain) && rain.length >= 3 && rain.slice(0, 3).every((value) => typeof value === 'number' && Number.isFinite(value) && value >= 0)
    ? rain.slice(0, 3).reduce((total, value) => total + value, 0)
    : null;
  const current = forecast.current_conditions;
  const hasDailyForecast = Array.isArray(daily.time) && daily.time.length > 0;
  const assessmentLabel = assessmentDate ? ` - ${formatWeatherTimestamp(assessmentDate)}` : '';
  const risks = result.identified_risks || [];
  return <><PageTitle eyebrow="WEATHER" title="Forecast and field risks" description={forecast.source ? `Current forecast - ${forecast.source}` : 'Live forecast unavailable'} />
    {loading && <p className="loading-note" role="status">Loading forecast for {farm.farm_id}...</p>}
    {weatherError && <p className="message error-message" role="alert">{weatherError}</p>}
    <div className="overview-grid">
      {current && <Card title={formatWeatherTimestamp(current.time) || 'Current conditions'}><div className="metric-grid"><div><small>Temperature</small><strong>{current.temperature_2m ?? current.temperature ?? '-'}<i>{String.fromCharCode(176)}C</i></strong></div><div><small>Humidity</small><strong>{current.relative_humidity_2m ?? current.relative_humidity ?? '-'}<i>%</i></strong></div><div><small>Rain</small><strong>{current.precipitation ?? '-'}<i> mm</i></strong></div><div><small>Wind</small><strong>{current.wind_speed_10m ?? current.wind_speed ?? '-'}<i> km/h</i></strong></div></div></Card>}
      {liveRainTotal != null && <Card title="Rain expected - next 3 days"><strong className="large-value">{liveRainTotal} <i>mm</i></strong></Card>}
      {hasDailyForecast && <Card className="wide-card" title="Daily forecast - temperature and rain"><ForecastChart daily={daily} /></Card>}
      {(result.weather_summary || risks.length > 0) && <Card className="wide-card" title="Farm impact this week"><div className="weather-impact-grid">
        <section><strong>Weather impact</strong><p>{result.weather_summary || 'Forecast conditions may affect field work and crop water needs. Check the daily forecast below.'}</p></section>
        <section><strong>Potential risks</strong>{risks.length ? <ul className="result-list">{risks.map((risk, index) => <li key={`${risk.risk}-${risk.date}-${index}`}><b>{risk.risk}</b>{risk.date && <span> - {risk.date}</span>}<p>Impact: {risk.impact || 'Check field conditions against this forecast.'}</p>{risk.priority && <small className="small-note">{risk.priority} priority</small>}{risk.sources?.length > 0 && <small className="list-source">Source: {sourceNames(risk.sources)}</small>}</li>)}</ul> : <p className="muted">No specific weather risks identified.</p>}</section>
        <section><strong>Recommended actions</strong>{risks.length ? <ul className="result-list">{risks.map((risk, index) => <li key={`${risk.risk}-${risk.date}-${index}`}>{risk.recommended_action || `Check ${String(risk.risk || 'weather').toLowerCase()} conditions in the field.`}{risk.sources?.length > 0 && <small className="list-source">Source: {sourceNames(risk.sources)}</small>}</li>)}</ul> : <p className="muted">Review the forecast each day and adjust field work to actual conditions.</p>}</section>
      </div></Card>}
      {savedForecast.source && <Card className="wide-card" title={`Weather saved with assessment${assessmentLabel}`}><ForecastChart daily={savedDaily} /></Card>}
      {!loading && !weatherError && !current && !hasDailyForecast && !savedForecast.source && !risks.length && <p className="muted">Weather data is not available for this farm yet.</p>}
    </div>
    {advisory && <AiNotice />}
  </>;
}
function formatWeatherTimestamp(value) {
  if (!value) return '';
  const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/);
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(String(value));
  if (!match || hasTimezone) {
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString(undefined, { day: 'numeric', month: 'long', year: 'numeric', hour: 'numeric', minute: '2-digit' });
  }
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]), Number(match[4] || 0), Number(match[5] || 0));
  const dateLabel = date.toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' });
  return match[4] ? `${dateLabel} ${String.fromCharCode(183)} ${date.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })}` : dateLabel;
}
function ForecastChart({ daily }) {
  if (!daily.time?.length) return <p className="muted">No daily forecast values are available.</p>;
  const rain = Array.isArray(daily.precipitation_sum) ? daily.precipitation_sum : [];
  const validRain = rain.filter((value) => typeof value === 'number' && Number.isFinite(value) && value >= 0);
  const max = Math.max(1, ...validRain);
  return <div className="forecast-list">{daily.time.map((date, i) => {
    const rainfall = rain[i];
    const rainfallAvailable = typeof rainfall === 'number' && Number.isFinite(rainfall) && rainfall >= 0;
    const barWidth = rainfallAvailable && rainfall > 0 ? (rainfall / max) * 100 : 0;
    return <div className="forecast-row" key={`${date}-${i}`}><span>{new Date(`${date}T12:00:00`).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}</span><strong>{daily.temperature_2m_min?.[i] ?? '-'}{String.fromCharCode(176)}C / {daily.temperature_2m_max?.[i] ?? '-'}{String.fromCharCode(176)}C</strong><div className="rain-track">{rainfallAvailable && <i style={{ width: `${barWidth}%` }} />}</div><span>{rainfallAvailable ? `${rainfall} mm` : '-'}</span></div>;
  })}</div>;
}

export function SoilPage() {
  const { advisory } = useFarm(); if (!advisory) return <><PageTitle eyebrow="SOIL HEALTH" title="Understand what's beneath." /><AdvisoryEmpty /></>;
  const agent = advisory.agents?.soil || {}; const soil = agent.soil_report || advisory.assessment_snapshot || {};
  const crop = soil.crop_name || advisory.assessment_snapshot?.crop_name || 'selected crop';
  return <><PageTitle eyebrow="SOIL HEALTH" title="Soil readings and actions" description={`For ${crop}. Check values alongside field conditions.`} />
    <div className="overview-grid">
      <Card className="wide-card" title="Measurements"><div className="measure-grid"><Meter label="Soil moisture" value={soil.moisture ?? soil.soil_moisture} suffix="%"/><Meter label="pH" value={soil.ph ?? soil.soil_ph}/><Meter label="Nitrogen" value={soil.nitrogen}/><Meter label="Phosphorus" value={soil.phosphorus}/><Meter label="Potassium" value={soil.potassium}/></div><p className="small-note">{agent.nutrient_interpretation_note || 'N, P and K need soil-test units and method before a deficiency can be assessed.'}</p></Card>
      <Card title="Possible soil issues"><List items={[...(agent.rule_indicator_details || []), ...(agent.ai_risk_evidence || [])]} empty="No clear soil issue was identified from these readings."/><p>{agent.soil_health_summary}</p>{agent.retrieval_conflict && <p className="small-note">Guides disagree. Confirm with a local soil adviser before making changes.</p>}</Card>
      <Card title="What to do"><List items={agent.recommendation_evidence?.length ? agent.recommendation_evidence : agent.recommendations} evidenceItems={agent.recommendation_evidence} empty="Retest soil if crop growth or field conditions raise concern."/></Card>
      {agent.evidence_sources?.length > 0 && <Card title="Guides"><Sources agent={agent}/></Card>}
    </div><AiNotice /></>;
}

export function CropPage() {
  const { advisory, farm } = useFarm(); if (!advisory) return <><PageTitle eyebrow="CROP HEALTH" title="Read the signs carefully." /><AdvisoryEmpty /></>;
  const agent = advisory.agents?.pest_disease || {}; const snapshot = advisory.assessment_snapshot || {}; const report = agent.crop_report || snapshot;
  const cropName = report.crop_name || farm.crop_name || 'Crop not recorded';
  const risks = agent.risk_details?.length ? agent.risk_details : [...(agent.possible_pest_risks || []), ...(agent.possible_disease_risks || [])];
  return <><PageTitle eyebrow="CROP HEALTH" title="Crop risks and signs" description={`${cropName}${report.growth_stage ? ` · ${report.growth_stage}` : ''}`} />
    {report.symptoms?.length > 0 && <p className="small-note">Reported signs: {report.symptoms.join(', ')}</p>}
    <div className="overview-grid"><Card title="Pest and disease risks"><List items={risks} evidenceItems={[...(agent.pest_risk_evidence || []), ...(agent.disease_risk_evidence || [])]} empty={agent.evidence_summary || 'No likely issue identified. Continue checking plants for changes.'}/>{agent.retrieval_conflict && <p className="small-note">Guides disagree. Ask a local crop adviser before treating.</p>}</Card>
      <Card title="Prevention and next steps"><List items={agent.recommendation_evidence?.length ? agent.recommendation_evidence : agent.recommendations} evidenceItems={agent.recommendation_evidence} empty="Inspect affected plants and seek local advice if signs spread."/></Card>
      {(agent.evidence_sources?.length || agent.retrieved_sources?.length) > 0 && <Card title="Agricultural guides"><Sources agent={agent}/></Card>}</div><AiNotice /></>;
}

export function IrrigationPage() {
  const { advisory, farm } = useFarm(); if (!advisory) return <><PageTitle eyebrow="IRRIGATION PLANNER" title="Water with context." /><AdvisoryEmpty /></>;
  const irrigation = advisory.watering_schedule || advisory.agents?.irrigation || {};
  const snapshot = advisory.assessment_snapshot || {};
  const moisture = irrigation.soil_moisture ?? snapshot.soil_moisture;
  const expectedRain = irrigation.expected_rainfall_mm ?? advisory.weather_summary?.expected_rainfall_next_3_days_mm;
  const recentRain = irrigation.context_inputs?.recent_rainfall_mm ?? advisory.weather_summary?.recent_observed_rainfall?.precipitation_mm;
  const rainDate = irrigation.context_inputs?.recent_rainfall_date ?? advisory.weather_summary?.recent_observed_rainfall?.date;
  const schedule = irrigation.schedule || [];
  return <><PageTitle eyebrow="IRRIGATION" title="Watering plan" description={`${snapshot.crop_name || farm.crop_name || 'Selected crop'}${snapshot.growth_stage ? ` · ${snapshot.growth_stage}` : ''}`} />
    <div className="overview-grid"><Card className="wide-card" title={irrigation.recommended_action || 'Check field moisture'}><p className="large-paragraph">{irrigation.reason || 'Check soil at root depth and compare with local rainfall before watering.'}</p><div className="measure-grid"><Meter label="Soil moisture" value={moisture} suffix="%"/><Meter label="Rain forecast · 3 days" value={expectedRain} suffix=" mm"/><Meter label="Recent rain" value={recentRain} suffix=" mm"/></div></Card>
      <Card className="wide-card" title="This week"><List items={schedule} empty="Check the root zone today, after rainfall, and before each watering."/></Card>
      <Card title="Why this decision"><ul className="result-list">{(irrigation.decision_factors || []).map((factor) => <li key={factor.label}><strong>{factor.label}:</strong> {factor.detail}</li>)}</ul><p>No water quantity is estimated without local crop and irrigation-system data.</p>{irrigation.evidence_sources?.length > 0 && <Sources agent={irrigation}/>}</Card></div><AiNotice /></>;
}

export function AdvisoryPage() {
  const { advisory } = useFarm(); if (!advisory) return <><PageTitle eyebrow="FARM ADVISORY" title="Recommendations for consideration." /><AdvisoryEmpty /></>;
  const risks = advisory.risk_alerts || [];
  const unavailable = failedAgentMessages(advisory);
  return <><PageTitle eyebrow="FARM ADVISORY" title="Your seven-day farm plan" description="Priority risks and practical actions from the latest farm assessment." />
    {unavailable.length > 0 && <p className="message" role="status">Some advice is unavailable: {unavailable.join(', ')}.</p>}
    <div className="overview-grid"><Card className="wide-card" title="Priority risks">{risks.length ? <div className="risk-list">{risks.map((risk, i) => <div className="risk-item" key={`${risk.risk}-${i}`}><span className="risk-mark">!</span><div><strong>{risk.risk}</strong>{risk.priority && <small className="small-note">{risk.priority} priority</small>}{risk.impact && <p>{risk.impact}</p>}{risk.recommended_action && <p><strong>Action:</strong> {risk.recommended_action}</p>}{(risk.evidence_sources?.length || risk.sources?.length) > 0 && <small>Sources: {sourceNames(risk.evidence_sources?.length ? risk.evidence_sources : risk.sources)}</small>}</div></div>)}</div> : <p className="muted">No likely risks were identified from this assessment.</p>}</Card>
      <Card className="wide-card" title="Actions for the next seven days"><List items={advisory.weekly_action_plan} empty="No weekly actions are available."/></Card>
      {advisory.weekly_action_list?.length > 0 && <Card className="wide-card" title="Recommendations and sources"><List items={advisory.weekly_action_list} evidenceItems={advisory.weekly_action_evidence}/></Card>}
    </div><AiNotice /></>;
}

export function HistoryPage() {
  const { farm } = useFarm();
  const [observations, setObservations] = useState([]);
  const [advisories, setAdvisories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [accessDenied, setAccessDenied] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    setAccessDenied(false);
    setObservations([]);
    setAdvisories([]);

    Promise.all([
      requestAllFarmObservations(farm.farm_id),
      requestAllFarmAdvisories(farm.farm_id),
    ]).then(([observationData, advisoryData]) => {
      if (!active) return;
      setObservations(Array.isArray(observationData) ? observationData : observationData.items || []);
      setAdvisories(Array.isArray(advisoryData) ? advisoryData : advisoryData.items || []);
    }).catch((requestError) => {
      if (!active) return;
      const status = requestError.response?.status;
      setAccessDenied([401, 403, 404].includes(status));
      setError(apiErrorMessage(requestError));
    }).finally(() => {
      if (active) setLoading(false);
    });

    return () => { active = false; };
  }, [farm.farm_id]);

  return <><PageTitle eyebrow="FARM HISTORY" title="Your farm, over time." description="Stored observations and advisories for the selected farm." />
    {loading && <div className="message info-message" role="status">Loading farm history…</div>}
    {!loading && error && <div className="message error-message" role="alert"><strong>{accessDenied ? 'Farm access unavailable.' : 'History could not be loaded.'}</strong><p>{error}</p>{accessDenied && <p>Sign in again to view this farm’s history.</p>}</div>}
    {!loading && !error && <HistoryTimeline observations={observations} advisories={advisories} />}
  </>;
}

function HistoryTimeline({ observations, advisories }) {
  const usedObservationIds = new Set();
  const entries = advisories.map((record) => {
    const assessmentId = record.advisory?.assessment_id;
    const observationRecord = observations.find((item) => item.observation?.assessment_id === assessmentId);
    if (observationRecord) usedObservationIds.add(observationRecord.observation_id);
    return { key: record.advisory_id, timestamp: record.created_at, record, observationRecord, kind: 'assessment' };
  });
  observations.filter((record) => !usedObservationIds.has(record.observation_id)).forEach((record) => {
    entries.push({ key: record.observation_id, timestamp: record.created_at, record, kind: 'observation' });
  });
  entries.sort((left, right) => new Date(left.timestamp || 0) - new Date(right.timestamp || 0));
  let previousMeasurements = null;
  const withChanges = entries.map((entry) => {
    const observation = entry.observationRecord?.observation || entry.record?.advisory?.assessment_snapshot || entry.record?.observation;
    const changes = [];
    if (observation && previousMeasurements) {
      for (const field of ['soil_moisture', 'soil_ph']) {
        const before = previousMeasurements[field];
        const after = observation[field];
        if (typeof before === 'number' && Number.isFinite(before) && typeof after === 'number' && Number.isFinite(after)) {
          changes.push(`${field === 'soil_ph' ? 'Soil pH' : 'Soil moisture'} ${before} → ${after} (${after - before > 0 ? '+' : ''}${Number((after - before).toFixed(2))})`);
        }
      }
    }
    if (observation) previousMeasurements = observation;
    return { ...entry, changes };
  });
  return <div className="overview-grid"><Card className="wide-card" eyebrow="CHRONOLOGICAL FARM TIMELINE" title={`${observations.length} observations / ${advisories.length} advisories`}>
    {withChanges.length === 0 ? <><p className="muted">No saved observations were found for this farm. Submit a New Assessment to start tracking crop readings and advisory history.</p><p className="muted">No saved advisories were found for this farm.</p></> : <div className="history-record-list">{withChanges.map((entry) => <article className="history-record" key={entry.key}><HistoryTimestamp value={entry.timestamp} />{entry.changes.length > 0 && <p className="small-note">Change since previous recorded assessment: {entry.changes.join('; ')}</p>}{entry.kind === 'assessment' ? <><ObservationRecord record={entry.observationRecord || { observation: entry.record.advisory?.assessment_snapshot }} showTimestamp={false} /><AdvisoryRecord record={entry.record} showTimestamp={false} /></> : <ObservationRecord record={entry.record} showTimestamp={false} />}</article>)}</div>}
  </Card></div>;
}

function HistoryTimestamp({ value }) {
  if (!value) return null;
  const timestamp = new Date(value);
  return <p className="subtle-line">{Number.isNaN(timestamp.getTime()) ? value : timestamp.toLocaleString()}</p>;
}

function ObservationRecord({ record, showTimestamp = true }) {
  const observation = record.observation || {};
  const fields = [
    ['Crop', observation.crop_name],
    ['Growth stage', observation.growth_stage],
    ['Soil moisture', observation.soil_moisture],
    ['Soil pH', observation.soil_ph],
    ['Nitrogen', observation.nitrogen],
    ['Phosphorus', observation.phosphorus],
    ['Potassium', observation.potassium],
    ['Symptoms', Array.isArray(observation.symptoms) ? observation.symptoms.join(', ') : observation.symptoms],
  ].filter(([, value]) => value !== undefined && value !== null && value !== '');

  return <article className="history-record">{showTimestamp && <HistoryTimestamp value={record.created_at} />}
    <div className="farm-details history-measures">{fields.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>
  </article>;
}

function AdvisoryRecord({ record, showTimestamp = true }) {
  const advisory = record.advisory || {};
  const agents = advisory.agents || {};
  const report = agents.pest_disease?.crop_report || {};
  const actions = Array.isArray(advisory.weekly_action_list) ? advisory.weekly_action_list : [];
  const risks = Array.isArray(advisory.risk_alerts) ? advisory.risk_alerts : [];
  const agentOutcomes = Object.entries(agents).map(([name, agent]) =>
    `${agent?.agent || name}: ${agent?.status || 'status unavailable'}${agent?.quality_status ? `, ${agent.quality_status} analysis` : ''}${agent?.llm_status && agent.llm_status !== 'not_called' ? `, AI ${agent.llm_status.replaceAll('_', ' ')}` : ''}`,
  );

  return <article className="history-record">{showTimestamp && <HistoryTimestamp value={record.created_at} />}
    {(report.crop_name || report.growth_stage) && <p>{[report.crop_name, report.growth_stage].filter(Boolean).join(' · ')}</p>}
    {advisory.status && <p><strong>Weekly advisory status:</strong> {advisory.status.replaceAll('_', ' ')}</p>}
    {advisory.history_context && <p className="small-note">Previous observations at this assessment: {advisory.history_context.previous_observations_count ?? 'count unavailable'}; supplied to the agents: {advisory.history_context.observations_supplied_to_agents ?? 'count unavailable'}.</p>}
    {agentOutcomes.length > 0 && <><strong>Agent outcomes</strong><List items={agentOutcomes} /></>}
    {(advisory.agent_failures || []).map((item, index) => <p className="message error-message" key={`failure-${index}`}>{item.agent}: {item.message}</p>)}
    {(advisory.agent_degradations || []).map((item, index) => <p className="message" key={`degradation-${index}`}>{item.agent}: {item.reason?.replaceAll('_', ' ') || item.message}</p>)}
    {risks.length > 0 && <><strong>Risk alerts</strong><div className="risk-list">{risks.map((risk, index) => <div className="risk-item" key={`${risk.risk}-${index}`}><div><strong>{[risk.risk, risk.severity, risk.date].filter(Boolean).join(' · ')}</strong>{risk.classification === 'preliminary_rule_indicator' && <small className="small-note">Preliminary indicator</small>}{risk.evidence_status && <small className="small-note">Evidence status: {risk.evidence_status.replaceAll('_', ' ')}</small>}{risk.priority && <small className="small-note">Priority: {risk.priority}</small>}{risk.impact && <p>{risk.impact}</p>}{risk.recommended_action && <p><strong>Action:</strong> {risk.recommended_action}</p>}{(risk.evidence_sources?.length || risk.sources?.length) > 0 && <small>Sources: {[...new Set(sourceNames(risk.evidence_sources?.length ? risk.evidence_sources : risk.sources).split(', '))].join(', ')}</small>}</div></div>)}</div></>}
    {agents.weather && <section><strong>Historical weather forecast</strong><p>Assessment snapshot from {agents.weather.forecast?.fetched_at || advisory.weather_summary?.fetched_at || record.created_at || 'an unrecorded fetch time'} · {agents.weather.forecast?.source || advisory.weather_summary?.source || 'Provider unavailable'}{agents.weather.forecast?.location ? ` · ${agents.weather.forecast.location.latitude}, ${agents.weather.forecast.location.longitude}` : ''}</p><HistoricalForecast forecast={agents.weather.forecast || {}} />{(agents.weather.identified_risks || []).map((risk) => <p key={risk.risk}>{risk.risk}</p>)}</section>}
    {agents.soil && <section><strong>Soil findings</strong><p>{agents.soil.soil_health_summary || 'No soil interpretation returned.'}</p><List items={[...(agents.soil.ai_identified_risks || []), ...(agents.soil.preliminary_rule_indicators || [])]} /></section>}
    {agents.pest_disease && <section><strong>Crop health findings</strong><p>{agents.pest_disease.evidence_summary || 'No crop health interpretation returned.'}</p><List items={[...(agents.pest_disease.possible_pest_risks || []), ...(agents.pest_disease.possible_disease_risks || [])]} evidenceItems={[...(agents.pest_disease.pest_risk_evidence || []), ...(agents.pest_disease.disease_risk_evidence || [])]} /></section>}
    {agents.irrigation && <section><strong>Irrigation recommendation</strong><p>{agents.irrigation.recommended_action || agents.irrigation.reason || 'No irrigation recommendation returned.'}</p><p>{agents.irrigation.guidance_note || ''}</p></section>}
    {actions.length > 0 && <><strong>Weekly advisory actions</strong><List items={actions} evidenceItems={advisory.weekly_action_evidence} /></>}
    {actions.length === 0 && risks.length === 0 && !report.crop_name && !report.growth_stage && !agents.weather && !agents.soil && !agents.pest_disease && !agents.irrigation && <p className="muted">This stored advisory has no displayable finding fields.</p>}
    <AiNotice />
  </article>;
}

function HistoricalForecast({ forecast }) {
  const daily = forecast.daily_forecast || {};
  const dates = Array.isArray(daily.time) ? daily.time : [];
  if (!dates.length) return <p>No historical forecast period was saved with this assessment.</p>;
  const fields = [
    ['High °C', daily.temperature_2m_max],
    ['Low °C', daily.temperature_2m_min],
    ['Rain mm', daily.precipitation_sum],
    ['Rain chance %', daily.precipitation_probability_max],
  ];
  return <div className="farm-details">{dates.map((date, index) => <div key={`${date}-${index}`}><span>{date}</span><strong>{fields.map(([label, values]) => Array.isArray(values) && values[index] != null ? `${label}: ${values[index]}` : null).filter(Boolean).join(' · ') || 'Forecast values unavailable'}</strong></div>)}</div>;
}

export function SettingsPage() {
  const { farm, advisory, demoMode, setAdvisory, account } = useFarm();
  const [dark, setDark] = useState(() => localStorage.getItem('agri-vision-theme') === 'dark');
  useEffect(() => { document.documentElement.dataset.theme = dark ? 'dark' : 'light'; }, [dark]);
  function toggle() { const value = !dark; setDark(value); localStorage.setItem('agri-vision-theme', value ? 'dark' : 'light'); document.documentElement.dataset.theme = value ? 'dark' : 'light'; }
  return <><PageTitle eyebrow="PREFERENCES" title="Settings" description="Application preferences and current farm details." /><div className="overview-grid"><Card eyebrow="SELECTED FARM" title="Farm identity"><FarmDetails farm={farm}/><Link className="inline-link" to="/farm">Edit farm profile ↗</Link></Card><Card eyebrow="APPEARANCE" title="Display"><label className="toggle-row"><span>Dark theme</span><input type="checkbox" checked={dark} onChange={toggle}/></label><p className="field-help">Theme preference is saved in this browser.</p></Card><Card eyebrow={account ? "ACCOUNT ACCESS" : "DEMO ACCESS"} title="Session"><p>{account ? `Signed in as ${account.email}. Your farms are scoped to this account.` : demoMode ? 'Demo mode is active. No account is authenticated.' : 'You are browsing without an authenticated account.'}</p>{!account && <p className="field-help">Demo access must be established through the backend from the Login page. This setting cannot enable or grant farm access.</p>}</Card><Card eyebrow="LOCAL DATA" title="Latest advisory"><p>The latest backend response is cached in this browser for convenience. MongoDB remains the source for persistent farm memory.</p>{advisory && <button className="text-button danger-text" onClick={() => setAdvisory(null)}>Clear latest advisory from this browser</button>}</Card><Card className="wide-card" eyebrow="ABOUT THIS APPLICATION" title="Agri Vision"><p>Smart Farm Advisory Council · Frontend build 1.0</p><Link className="inline-link" to="/about">About the platform ↗</Link></Card></div></>;
}

export function AboutPage() {
  return <div className="public-about"><Link className="inline-link" to="/">← Back to home</Link><PageTitle eyebrow="ABOUT AGRI VISION" title="Technology should help us understand nature better." description="Agri Vision is a Smart Farm Advisory Council that combines specialised agent analysis with agricultural knowledge retrieval and farm-history context."/><div className="overview-grid">{[['Five agents','Weather, soil, crop health and irrigation specialists contribute to a unified advisory managed by the Advisory Manager.'],['Knowledge retrieval','The pest and disease agent retrieves crop-specific references from a ChromaDB agricultural knowledge base.'],['Farm memory','MongoDB stores observations and advisories by farm ID. Previous observations are shared with the Soil and Crop Health agents.'],['Grounded advice','The platform reports possible risks and practical recommendations, with expert inspection guidance where needed.']].map(([title, copy]) => <Card key={title} title={title}><p>{copy}</p></Card>)}</div></div>;
}

export function AuthPage({ signup = false }) {
  const { farm, setCredentialFarmId, selectFarm, clearFarmSelection, setDemoMode, setAccount, setFarms, account, accountLoading, credentialFarmId } = useFarm();
  const navigate = useNavigate();
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setNotice('');
    const form = new FormData(e.currentTarget);
    const email = String(form.get('email') || '').trim();
    const password = String(form.get('password') || '');
    if (!email || !password) { setNotice('Enter both your email address and password.'); return; }
    if (signup && password !== String(form.get('confirm-password') || '')) { setNotice('The passwords do not match.'); return; }
    setBusy(true);
    try {
      const user = signup ? await registerAccount(email, password) : await loginAccount(email, password);
      setAccount(user);
      const ownedFarms = await requestMyFarms();
      if (ownedFarms.length) {
        const staleFarmIds = [credentialFarmId, farm?.farm_id].filter((farmId) => farmId && !ownedFarms.some((item) => item.farm_id === farmId));
        if (staleFarmIds.length) clearFarmSelection(staleFarmIds);
      }
      const selectedFarm = ownedFarms.find((item) => item.farm_id === credentialFarmId)
        || ownedFarms.find((item) => item.farm_id === farm?.farm_id)
        || ownedFarms[0];
      if (!selectedFarm && !signup) {
        setFarms([]);
        clearFarmSelection(credentialFarmId || farm?.farm_id);
        setDemoMode(false);
        navigate('/dashboard', { replace: true });
        return;
      }
      if (!selectedFarm) {
        const farmId = `farm-${crypto.randomUUID()}`;
        await registerFarm(farmId);
        const refreshedFarms = await requestMyFarms();
        const createdFarm = refreshedFarms.find((item) => item.farm_id === farmId);
        if (!createdFarm) throw new Error('Your account is ready, but a farm could not be loaded. Please try again.');
        setFarms(refreshedFarms);
        if (createdFarm.profile) selectFarm(createdFarm.farm_id, createdFarm.profile);
        else selectFarm(createdFarm.farm_id);
        setDemoMode(false);
        navigate('/dashboard', { replace: true });
        return;
      }
      setFarms(ownedFarms);
      if (selectedFarm.profile) selectFarm(selectedFarm.farm_id, selectedFarm.profile);
      else selectFarm(selectedFarm.farm_id);
      setDemoMode(false);
      navigate('/dashboard', { replace: true });
    } catch (error) {
      setNotice(error.message && !error.response ? error.message : apiErrorMessage(error));
    } finally { setBusy(false); }
  }
  async function demo() {
    setBusy(true); setNotice('');
    try {
      const registration = await registerFarm(farm.farm_id);
      setCredentialFarmId(registration.farm_id);
      setDemoMode(true);
      navigate('/dashboard', { replace: true });
    } catch (error) {
      setNotice(apiErrorMessage(error));
    } finally { setBusy(false); }
  }
  if (account && !accountLoading) return <Navigate to="/dashboard" replace />;
  return <div className="auth-page"><div className="auth-aside" style={{ backgroundImage: 'linear-gradient(0deg, rgba(21,42,33,.45), rgba(21,42,33,.12)), url(/images/terraced-farms.webp)' }}><Link className="auth-wordmark" to="/"><span>AGRI</span> VISION</Link><p>Every field has a story.<br/>Every season has a lesson.</p><span className="eyebrow">SMART FARM ADVISORY COUNCIL</span></div><div className="auth-main"><div className="auth-form-wrap"><Link className="inline-link" to="/">← Back to Agri Vision</Link><span className="eyebrow">{signup ? 'FARMER REGISTRATION' : 'WELCOME BACK'}</span><h1>{signup ? 'Create your account.' : 'Good to have you here.'}</h1><p>{signup ? 'Register securely to manage one or more farms.' : 'Sign in to continue to your farm workspace.'}</p><form onSubmit={submit} className="auth-form" noValidate><label>Email address<input name="email" type="email" autoComplete="email" required placeholder="you@example.com" /></label><label>Password<input name="password" type="password" autoComplete={signup ? 'new-password' : 'current-password'} required minLength={8} maxLength={72} placeholder="At least 8 characters" /></label>{signup && <label>Confirm password<input name="confirm-password" type="password" autoComplete="new-password" required placeholder="Re-enter your password" /></label>}<button className="button" disabled={busy}>{busy ? <><span className="spinner"/> {signup ? 'Creating account…' : 'Signing in…'}</> : signup ? 'Create account' : 'Sign in'}</button></form>{notice && <p className="message error-message" role="alert">{notice}</p>}<div className="auth-divider"><span>OR</span></div><button type="button" className="button button-outline demo-button" onClick={demo} disabled={busy}>{busy ? 'Connecting…' : 'Continue with demo access'}</button><p className="small-note">Demo access does not create or authenticate an account.</p><p className="auth-switch">{signup ? 'Already have an account?' : 'New to Agri Vision?'} <Link to={signup ? '/login' : '/signup'}>{signup ? 'Login' : 'Create an account'}</Link></p></div></div></div>;
}

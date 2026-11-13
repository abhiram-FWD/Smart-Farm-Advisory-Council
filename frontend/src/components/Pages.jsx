import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useFarm } from '../context/FarmContext.jsx';
import { apiErrorMessage, registerFarm, requestAdvisory, requestFarmAdvisories, requestFarmObservations } from '../services/api.js';
import { Card, EmptyState, List, Meter, PageTitle, Sources } from './Primitives.jsx';

function AdvisoryEmpty() { return <EmptyState>Generate an assessment to see recommendations based on this farm’s current soil, crop and forecast information.</EmptyState>; }
function sourceNames(sources = []) { return sources.map((source) => typeof source === 'string' ? source : source.title && source.title !== 'Unavailable' ? source.title : source.filename || source.source || 'Source unavailable').join(', '); }
function isWeatherIndicator(risk) { return risk?.reported_by?.includes('Weather Agent'); }
function FarmDetails({ farm }) { return <div className="farm-details"><div><span>Farm ID</span><strong>{farm.farm_id || 'Not set'}</strong></div><div><span>Coordinates</span><strong>{farm.latitude && farm.longitude ? `${farm.latitude}, ${farm.longitude}` : 'Not provided'}</strong></div><div><span>Crop</span><strong>{farm.crop_name || 'Not provided'}</strong></div><div><span>Growth stage</span><strong>{farm.growth_stage || 'Not provided'}</strong></div></div>; }

export function DashboardPage() {
  const { advisory, farm } = useFarm();
  if (!advisory) return <><PageTitle eyebrow="FARM OVERVIEW" title="Welcome to your farm." description="A considered view of your latest farm advisory will live here." /><FarmDetails farm={farm} /><AdvisoryEmpty /></>;
  const agents = advisory.agents || {};
  const soil = agents.soil || {};
  const crop = agents.pest_disease || {};
  const weather = agents.weather?.forecast || {};
  const forecast = weather.daily_forecast || {};
  const risks = advisory.risk_alerts || [];
  const actions = advisory.weekly_action_list || [];
  return <><PageTitle eyebrow="FARM OVERVIEW" title="Welcome to your farm." description={`Your latest assessment for ${crop.crop_report?.crop_name || agents.irrigation?.crop || farm.crop_name || 'this farm'}.`} action={<Link className="button" to="/advisory">View farm advisory <span>↗</span></Link>} />
    <FarmDetails farm={{ ...farm, crop_name: crop.crop_report?.crop_name || farm.crop_name, growth_stage: crop.crop_report?.growth_stage || farm.growth_stage }} />
    <div className="overview-grid"><Card eyebrow="LATEST READING" title="Soil snapshot"><div className="metric-grid"><div><small>Moisture</small><strong>{soil.soil_report?.moisture ?? '—'}<i>%</i></strong></div><div><small>pH</small><strong>{soil.soil_report?.ph ?? '—'}</strong></div><div><small>Nitrogen</small><strong>{soil.soil_report?.nitrogen ?? '—'}</strong></div></div><Link className="inline-link" to="/soil">Explore soil health ↗</Link></Card>
      <Card eyebrow="FORECAST" title={weather.source || 'Weather summary'}><p>{forecast.time?.length ? `${forecast.time.length} forecast days available.` : 'Forecast details are available in the weather view.'}</p><p className="subtle-line">Expected rainfall (3 days): {advisory.weather_summary?.expected_rainfall_next_3_days_mm ?? '—'} mm</p><Link className="inline-link" to="/weather">Explore weather ↗</Link></Card>
      <Card eyebrow="CROP HEALTH" title="Reported risks"><p>{crop.evidence_summary || 'Review the possible risks and recommendations reported by the crop agent.'}</p><Link className="inline-link" to="/crop">Review crop insights ↗</Link></Card>
      <Card eyebrow="PRELIMINARY IRRIGATION GUIDANCE" title={agents.irrigation?.recommended_action || 'No guidance returned'}><p>{agents.irrigation?.guidance_note || 'This is preliminary demonstration guidance, not a farm-specific irrigation prescription.'}</p><Link className="inline-link" to="/irrigation">Review irrigation ↗</Link></Card>
      <Card eyebrow={`RISK ALERTS · ${risks.length}`} title="Reported findings">{risks.length ? <List items={risks.map((r) => `${r.risk}${r.classification === 'preliminary_rule_indicator' ? ' - preliminary indicator' : ''}${isWeatherIndicator(r) ? ' - preliminary weather project indicator (not a universal agricultural threshold, not a verified crop-specific warning, and not professional advice)' : ''}${r.severity ? ` · ${r.severity}` : ''}${r.date ? ` · ${r.date}` : ''}`)} /> : <p className="muted">No risk alerts were returned in the latest advisory.</p>}</Card>
      <Card eyebrow={`RECOMMENDATIONS · ${actions.length}`} title="For consideration"><List items={actions.slice(0, 5)} evidenceItems={advisory.weekly_action_evidence} /><Link className="inline-link" to="/advisory">See all recommendations ↗</Link></Card>
    </div>
    <p className="memory-note">{advisory.historical_context_available ? `Prior farm context was supplied to the Soil and Pest and Disease agents. The backend reports ${advisory.memory?.previous_observations_count ?? 'an unspecified number of'} previous observations.` : 'No previous farm context was available to this assessment.'}</p>
  </>;
}

export function FarmProfilePage() {
  const { farm, setFarm } = useFarm();
  const [saved, setSaved] = useState(false);
  function submit(e) { e.preventDefault(); const data = new FormData(e.currentTarget); setFarm(Object.fromEntries(data.entries())); setSaved(true); }
  return <><PageTitle eyebrow="YOUR FARM" title="Farm profile" description="Keep a stable farm identity so repeat assessments use the same farm history." />
    <form className="form-card profile-form" onSubmit={submit}><label>Farm ID<input name="farm_id" required minLength="1" defaultValue={farm.farm_id} /></label><p className="field-help">This ID is sent with each assessment and is saved in this browser. This demo supports one active farm credential; changing the ID does not transfer history access, and access will not be switched automatically.</p><div className="form-grid"><label>Latitude<input type="number" name="latitude" min="-90" max="90" step="any" defaultValue={farm.latitude} placeholder="e.g. 18.5204" /></label><label>Longitude<input type="number" name="longitude" min="-180" max="180" step="any" defaultValue={farm.longitude} placeholder="e.g. 73.8567" /></label><label>Crop name<input name="crop_name" defaultValue={farm.crop_name} placeholder="e.g. Wheat" /></label><label>Growth stage<input name="growth_stage" defaultValue={farm.growth_stage} placeholder="e.g. Tillering" /></label></div><div className="form-actions"><button className="button">Save farm profile</button>{saved && <span className="success-text" role="status">Farm profile saved.</span>}</div></form>
    <Card title="Current farm identity"><FarmDetails farm={farm} /></Card></>;
}

const blank = { latitude: '', longitude: '', soil_moisture: '', soil_ph: '', nitrogen: '', phosphorus: '', potassium: '', crop_name: '', growth_stage: '', symptoms: '' };
export function AssessmentPage() {
  const { farm, setFarm, setAdvisory, credentialFarmId, setCredentialFarmId } = useFarm();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const initial = useMemo(() => ({ ...blank, latitude: farm.latitude, longitude: farm.longitude, crop_name: farm.crop_name, growth_stage: farm.growth_stage }), [farm]);
  async function submit(e) {
    e.preventDefault(); setBusy(true); setError(''); setMessage('');
    const form = new FormData(e.currentTarget);
    const payload = { farm_id: farm.farm_id, latitude: Number(form.get('latitude')), longitude: Number(form.get('longitude')), soil_moisture: Number(form.get('soil_moisture')), soil_ph: Number(form.get('soil_ph')), nitrogen: Number(form.get('nitrogen')), phosphorus: Number(form.get('phosphorus')), potassium: Number(form.get('potassium')), crop_name: String(form.get('crop_name')).trim(), growth_stage: String(form.get('growth_stage')).trim(), symptoms: String(form.get('symptoms') || '').split(',').map((s) => s.trim()).filter(Boolean) };
    try {
      if (credentialFarmId && credentialFarmId !== payload.farm_id) {
        throw new Error('This browser has access to a different farm. Restore that farm ID to continue; credentials are not switched automatically.');
      }
      const registration = await registerFarm(payload.farm_id);
      setCredentialFarmId(registration.farm_id);
      const data = await requestAdvisory(payload);
      if (!['completed', 'completed_with_memory_warning'].includes(data.status)) throw new Error(data.error || 'The advisory could not be completed.');
      setAdvisory(data); setFarm((current) => ({ ...current, latitude: payload.latitude, longitude: payload.longitude, crop_name: payload.crop_name, growth_stage: payload.growth_stage }));
      setMessage(data.status === 'completed_with_memory_warning' ? data.memory_warning : 'Advisory generated and saved. The same farm ID is ready for your next assessment.');
    } catch (e2) { setError(e2.message && !e2.response ? e2.message : apiErrorMessage(e2)); }
    finally { setBusy(false); }
  }
  return <><PageTitle eyebrow="FARM ASSESSMENT" title="Take a reading." description="Share the current conditions. The advisory council will consider weather, soil and crop health together." />
    <form className="form-card assessment-form" onSubmit={submit}><div className="form-section"><span className="eyebrow">01 · LOCATION</span><div className="form-grid"><label>Latitude (−90 to 90)<input name="latitude" type="number" required min="-90" max="90" step="any" defaultValue={initial.latitude} placeholder="e.g. 18.5204" /></label><label>Longitude (−180 to 180)<input name="longitude" type="number" required min="-180" max="180" step="any" defaultValue={initial.longitude} placeholder="e.g. 73.8567" /></label></div></div>
      <div className="form-section"><span className="eyebrow">02 · SOIL MEASUREMENTS</span><p className="field-help">Enter your measured values. Nutrient units depend on your soil test report.</p><div className="form-grid three"><label>Soil moisture (%)<input name="soil_moisture" type="number" required min="0" step="any" defaultValue="" /></label><label>Soil pH<input name="soil_ph" type="number" required min="0" max="14" step="any" defaultValue="" /></label><label>Nitrogen<input name="nitrogen" type="number" required min="0" step="any" defaultValue="" /></label><label>Phosphorus<input name="phosphorus" type="number" required min="0" step="any" defaultValue="" /></label><label>Potassium<input name="potassium" type="number" required min="0" step="any" defaultValue="" /></label></div></div>
      <div className="form-section"><span className="eyebrow">03 · CROP OBSERVATIONS</span><div className="form-grid"><label>Crop name<input name="crop_name" required minLength="1" defaultValue={initial.crop_name} placeholder="e.g. Rice" /></label><label>Growth stage<input name="growth_stage" required minLength="1" defaultValue={initial.growth_stage} placeholder="e.g. Flowering" /></label><label className="full-width">Current symptoms <span className="optional-label">Optional</span><input name="symptoms" placeholder="Separate symptoms with commas" /></label></div></div>
      <div className="form-submit-row"><div><strong>Farm ID</strong><span>{farm.farm_id}</span><small>This ID stays the same across assessments in this browser.</small></div><button className="button" disabled={busy}>{busy ? <><span className="spinner"/> Coordinating agents…</> : <>Generate advisory <span>↗</span></>}</button></div>
      {busy && <p className="loading-note" role="status">The Weather, Soil and Pest and Disease agents are analysing your inputs. Irrigation planning follows the forecast.</p>}
      {error && <div className="message error-message" role="alert">{error}</div>}{message && <div className="message success-message" role="status">{message} <Link to="/advisory">View the advisory ↗</Link></div>}
    </form>
  </>;
}

export function WeatherPage() {
  const { advisory } = useFarm(); if (!advisory) return <><PageTitle eyebrow="WEATHER INSIGHTS" title="Forecast, in context." /><AdvisoryEmpty /></>;
  const result = advisory.agents?.weather || {}; const forecast = result.forecast || {}; const daily = forecast.daily_forecast || {};
  const riskNote = result.risk_interpretation_note || 'Weather thresholds are preliminary project indicators, not universal agricultural thresholds, not verified crop-specific warnings, and not professional agricultural advice.';
  return <><PageTitle eyebrow="WEATHER INSIGHTS" title="Forecast, in context." description={`${forecast.source || 'Weather provider'} - ${daily.time?.length || 0} forecast days`} /><div className="overview-grid"><Card eyebrow="FORECAST SOURCE" title={forecast.source || 'Weather'}><p>{result.forecast?.note || 'Daily forecast details provided by the weather agent.'}</p><p className="subtle-line">Location: {forecast.location?.latitude ?? '\u2014'}, {forecast.location?.longitude ?? '\u2014'}</p></Card><Card eyebrow="THREE-DAY TOTAL" title="Expected rainfall"><strong className="large-value">{advisory.weather_summary?.expected_rainfall_next_3_days_mm ?? '\u2014'} <i>mm</i></strong></Card><Card className="wide-card" eyebrow="DAILY FORECAST" title="Temperature and rainfall"><ForecastChart daily={daily} /></Card><Card className="wide-card" eyebrow="PRELIMINARY PROJECT INDICATORS" title="Weather risk alerts"><p className="small-note">{riskNote}</p><List items={result.identified_risks?.map((r) => `${r.risk} - Preliminary project indicator - ${r.severity || 'Unspecified'}${r.date ? ` - ${r.date}` : ''}`)} /></Card></div></>;
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
    return <div className="forecast-row" key={`${date}-${i}`}><span>{new Date(`${date}T12:00:00`).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}</span><strong>{daily.temperature_2m_min?.[i] ?? '—'}° / {daily.temperature_2m_max?.[i] ?? '—'}°</strong><div className="rain-track">{rainfallAvailable && <i style={{ width: `${barWidth}%` }} />}</div><span>{rainfallAvailable ? `${rainfall} mm` : '—'}</span></div>;
  })}</div>;
}

export function SoilPage() {
  const { advisory } = useFarm(); if (!advisory) return <><PageTitle eyebrow="SOIL HEALTH" title="Understand what's beneath." /><AdvisoryEmpty /></>;
  const agent = advisory.agents?.soil || {}; const soil = agent.soil_report || {};
  return <><PageTitle eyebrow="SOIL HEALTH" title="Understand what's beneath." description="Submitted measurements and preliminary rule indicators; interpretation needs measurement and farm context." />{agent.expert_review_required && <p className="message" role="status">Expert review is required because retrieved evidence is insufficient, conflicting, or could not support a validated interpretation.</p>}<div className="overview-grid"><Card className="wide-card" eyebrow="MEASURED VALUES" title="Soil report"><div className="measure-grid"><Meter label="Moisture" value={soil.moisture} suffix="%"/><Meter label="pH" value={soil.ph}/><Meter label="Nitrogen" value={soil.nitrogen}/><Meter label="Phosphorus" value={soil.phosphorus}/><Meter label="Potassium" value={soil.potassium}/></div><p className="small-note">Nutrient values are shown as submitted. {agent.nutrient_interpretation_note || 'Nutrient units and soil-test method were not supplied; crop requirements and regional recommendations are also needed for interpretation.'}</p></Card><Card eyebrow="PRELIMINARY RULE INDICATORS" title="Not diagnoses"><p className="small-note">{agent.indicator_context || 'Moisture and pH rules are preliminary; interpretation depends on measurement method, crop, soil and local conditions.'}</p><List items={agent.preliminary_rule_indicators || agent.identified_risks}/></Card><Card eyebrow="AI-GENERATED INTERPRETATIONS" title="Source-linked statements"><p>Evidence status: {agent.evidence_status || 'Unavailable'}</p><p>{agent.soil_health_summary || 'Insufficient evidence for a soil interpretation.'}</p><List items={agent.ai_identified_risks} evidenceItems={agent.ai_risk_evidence}/></Card><Card eyebrow="ACTIONABLE RECOMMENDATIONS" title="For consideration"><List items={agent.recommendations} evidenceItems={agent.recommendation_evidence}/></Card><Card className="wide-card" eyebrow="RETRIEVED KNOWLEDGE" title="Sources"><Sources agent={agent}/><p className="small-note">Recommendations may require soil testing and local expert review.</p></Card></div></>;
}

export function CropPage() {
  const { advisory } = useFarm(); if (!advisory) return <><PageTitle eyebrow="CROP HEALTH" title="Read the signs carefully." /><AdvisoryEmpty /></>;
  const agent = advisory.agents?.pest_disease || {}; const report = agent.crop_report || {};
  return <><PageTitle eyebrow="CROP HEALTH" title="Read the signs carefully." description="Possible risks are evidence-linked indications, not confirmed diagnoses." />{agent.expert_inspection_required && <p className="message" role="status">Expert inspection is required because evidence is insufficient, conflicting, or could not support a validated finding.</p>}<div className="farm-details"><div><span>Crop</span><strong>{report.crop_name || advisory.agents?.irrigation?.crop || '—'}</strong></div><div><span>Growth stage</span><strong>{report.growth_stage || '—'}</strong></div><div><span>Symptoms reported</span><strong>{report.symptoms?.length ? report.symptoms.join(', ') : 'None supplied'}</strong></div><div><span>Expert inspection</span><strong>{agent.expert_inspection_required ? 'Required' : 'Not flagged'}</strong></div></div><div className="overview-grid"><Card eyebrow="POSSIBLE PEST RISKS" title="Source-supported possibilities"><List items={agent.possible_pest_risks} evidenceItems={agent.pest_risk_evidence}/></Card><Card eyebrow="POSSIBLE DISEASE RISKS" title="Source-supported possibilities"><List items={agent.possible_disease_risks} evidenceItems={agent.disease_risk_evidence}/></Card><Card className="wide-card" eyebrow="EVIDENCE SUMMARY" title="What the agent found"><p>Evidence status: {agent.evidence_status || 'Unavailable'}</p><p>{agent.evidence_summary || 'Insufficient evidence for a crop-health finding.'}</p></Card><Card eyebrow="RECOMMENDATIONS" title="Source-linked next steps"><List items={agent.recommendations} evidenceItems={agent.recommendation_evidence}/></Card><Card eyebrow="RETRIEVED KNOWLEDGE" title="Sources"><Sources agent={agent}/></Card></div></>;
}

export function IrrigationPage() {
  const { advisory } = useFarm(); if (!advisory) return <><PageTitle eyebrow="IRRIGATION PLANNER" title="Water with context." /><AdvisoryEmpty /></>;
  const irrigation = advisory.watering_schedule || advisory.agents?.irrigation || {};
  return <><PageTitle eyebrow="IRRIGATION PLANNER" title="Water with context." description="Preliminary demonstration guidance only. This is not a farm-specific irrigation prescription." /><div className="overview-grid"><Card className="wide-card" eyebrow="PRELIMINARY DEMONSTRATION GUIDANCE" title={irrigation.recommended_action || 'No guidance returned'}><p className="large-paragraph">{irrigation.reason || 'No reason was returned.'}</p><p className="small-note">{irrigation.guidance_note || 'A reliable decision needs crop growth stage, soil type, actual recent rainfall, crop water demand and local conditions.'}</p></Card><Card eyebrow="CURRENT MOISTURE" title="Soil context"><strong className="large-value">{irrigation.soil_moisture ?? '—'}<i>%</i></strong></Card><Card eyebrow="FORECAST DATA" title="Expected rainfall (next three days)"><strong className="large-value">{irrigation.expected_rainfall_mm ?? advisory.weather_summary?.expected_rainfall_next_3_days_mm ?? '—'}<i> mm</i></strong></Card></div><p className="small-note">Forecast rainfall is not actual recent rainfall received. No water quantity, duration or schedule is provided.</p></>;
}

export function AdvisoryPage() {
  const { advisory } = useFarm(); if (!advisory) return <><PageTitle eyebrow="FARM ADVISORY" title="Recommendations for consideration." /><AdvisoryEmpty /></>;
  return <><PageTitle eyebrow="FARM ADVISORY" title="Recommendations for consideration." description={advisory.weekly_action_list_note || "Current agent recommendations and reported risks; this is not a verified seven-day schedule."} />{advisory.expert_review_required && <p className="message" role="status">Expert review is required for one or more soil or crop-health findings.</p>}<div className="overview-grid"><Card className="wide-card" eyebrow="ACTIONABLE RECOMMENDATIONS" title={`${advisory.weekly_action_list?.length || 0} recommendations`}><List items={advisory.weekly_action_list} evidenceItems={advisory.weekly_action_evidence}/></Card><Card eyebrow="REPORTED RISKS AND INDICATORS" title={`${advisory.risk_alerts?.length || 0} findings`}>{advisory.risk_alerts?.length ? <div className="risk-list">{advisory.risk_alerts.map((risk, i) => <div className="risk-item" key={`${risk.risk}-${risk.date}-${i}`}><span className="risk-mark">!</span><div><strong>{risk.risk}</strong>{risk.classification === 'preliminary_rule_indicator' && <small className="small-note">Preliminary rule indicator - not a diagnosis</small>}{isWeatherIndicator(risk) && <small className="small-note">Preliminary weather project indicator - not a universal agricultural threshold, not a verified crop-specific warning, and not professional agricultural advice.</small>}{risk.evidence_status && <small className="small-note">Evidence status: {risk.evidence_status}</small>}<p>{[risk.severity, risk.date, risk.reported_by?.join(', ')].filter(Boolean).join(' · ')}</p>{(risk.evidence_sources?.length || risk.sources?.length) > 0 && <small>Sources: {sourceNames(risk.evidence_sources?.length ? risk.evidence_sources : risk.sources)}</small>}</div></div>)}</div> : <p className="muted">No risk alerts were returned.</p>}</Card><Card eyebrow="COORDINATION" title="How this advisory came together"><p>{advisory.coordination || 'Agent coordination'}</p><p>{advisory.historical_context_available ? 'Historical farm context was available to relevant agents.' : 'No historical farm context was available to this assessment.'}</p></Card><Card eyebrow="MEMORY" title="Persistence status"><p>{advisory.memory?.advisory_saved ? 'This advisory was saved by the backend.' : advisory.status === 'completed_with_memory_warning' ? advisory.memory_warning : 'Backend memory metadata was not included.'}</p><p className="subtle-line">Previous observations: {advisory.memory?.previous_observations_count ?? 'not reported'}</p></Card></div></>;
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
      requestFarmObservations(farm.farm_id),
      requestFarmAdvisories(farm.farm_id),
    ]).then(([observationData, advisoryData]) => {
      if (!active) return;
      setObservations(observationData.items || []);
      setAdvisories(advisoryData.items || []);
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
    {loading && <div className="message info-message" role="status">Loading farm history from MongoDB…</div>}
    {!loading && error && <div className="message error-message" role="alert"><strong>{accessDenied ? 'Farm access unavailable.' : 'History could not be loaded.'}</strong><p>{error}</p>{accessDenied && <p>Farm access is tied to this browser’s secure cookie. Farm IDs alone do not grant access. This demo supports one active farm credential at a time; it will not switch credentials automatically.</p>}</div>}
    {!loading && !error && <div className="overview-grid">
      <Card className="wide-card" eyebrow="OBSERVATIONS" title={`${observations.length} stored records`}>
        {observations.length === 0 ? <p className="muted">No saved observations were found for this farm.</p> : <div className="history-record-list">{observations.map((record) => <ObservationRecord key={record.observation_id} record={record} />)}</div>}
      </Card>
      <Card className="wide-card" eyebrow="ADVISORIES" title={`${advisories.length} stored records`}>
        {advisories.length === 0 ? <p className="muted">No saved advisories were found for this farm.</p> : <div className="history-record-list">{advisories.map((record) => <AdvisoryRecord key={record.advisory_id} record={record} />)}</div>}
      </Card>
    </div>}
  </>;
}

function HistoryTimestamp({ value }) {
  if (!value) return null;
  const timestamp = new Date(value);
  return <p className="subtle-line">{Number.isNaN(timestamp.getTime()) ? value : timestamp.toLocaleString()}</p>;
}

function ObservationRecord({ record }) {
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

  return <article className="history-record"><HistoryTimestamp value={record.created_at} />
    <div className="farm-details history-measures">{fields.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>
  </article>;
}

function AdvisoryRecord({ record }) {
  const advisory = record.advisory || {};
  const report = advisory.agents?.pest_disease?.crop_report || {};
  const actions = Array.isArray(advisory.weekly_action_list) ? advisory.weekly_action_list : [];
  const risks = Array.isArray(advisory.risk_alerts) ? advisory.risk_alerts : [];

  return <article className="history-record"><HistoryTimestamp value={record.created_at} />
    {(report.crop_name || report.growth_stage) && <p>{[report.crop_name, report.growth_stage].filter(Boolean).join(' · ')}</p>}
    {actions.length > 0 && <><strong>Weekly actions</strong><List items={actions} evidenceItems={advisory.weekly_action_evidence} /></>}
    {risks.length > 0 && <><strong>Risk alerts</strong><div className="risk-list">{risks.map((risk, index) => <div className="risk-item" key={`${risk.risk}-${index}`}><div><strong>{[risk.risk, risk.severity, risk.date].filter(Boolean).join(' · ')}</strong>{risk.evidence_status && <small className="small-note">Evidence status: {risk.evidence_status}</small>}{(risk.evidence_sources?.length || risk.sources?.length) > 0 && <small>Sources: {sourceNames(risk.evidence_sources?.length ? risk.evidence_sources : risk.sources)}</small>}</div></div>)}</div></>}
    {actions.length === 0 && risks.length === 0 && !report.crop_name && !report.growth_stage && <p className="muted">This stored advisory has no displayable action or risk fields.</p>}
  </article>;
}

export function SettingsPage() {
  const { farm, advisory, demoMode, setDemoMode, setAdvisory } = useFarm();
  const [dark, setDark] = useState(() => localStorage.getItem('agri-vision-theme') === 'dark');
  useEffect(() => { document.documentElement.dataset.theme = dark ? 'dark' : 'light'; }, [dark]);
  function toggle() { const value = !dark; setDark(value); localStorage.setItem('agri-vision-theme', value ? 'dark' : 'light'); document.documentElement.dataset.theme = value ? 'dark' : 'light'; }
  return <><PageTitle eyebrow="PREFERENCES" title="Settings" description="Application preferences and current demo farm details." /><div className="overview-grid"><Card eyebrow="SELECTED FARM" title="Farm identity"><FarmDetails farm={farm}/><Link className="inline-link" to="/farm">Edit farm profile ↗</Link></Card><Card eyebrow="APPEARANCE" title="Display"><label className="toggle-row"><span>Dark theme</span><input type="checkbox" checked={dark} onChange={toggle}/></label><p className="field-help">Theme preference is saved in this browser.</p></Card><Card eyebrow="DEMO ACCESS" title="Session"><p>{demoMode ? 'Demo mode is active. No account is authenticated.' : 'You are browsing without an authenticated account.'}</p><button className="button button-outline" onClick={() => setDemoMode(!demoMode)}>{demoMode ? 'Exit demo access' : 'Enable demo access'}</button></Card><Card eyebrow="LOCAL DATA" title="Latest advisory"><p>The latest backend response is cached in this browser for convenience. MongoDB remains the source for persistent farm memory.</p>{advisory && <button className="text-button danger-text" onClick={() => setAdvisory(null)}>Clear latest advisory from this browser</button>}</Card><Card className="wide-card" eyebrow="ABOUT THIS APPLICATION" title="Agri Vision"><p>Smart Farm Advisory Council · Frontend build 1.0</p><Link className="inline-link" to="/about">About the platform ↗</Link></Card></div></>;
}

export function AboutPage() {
  return <div className="public-about"><Link className="inline-link" to="/">← Back to home</Link><PageTitle eyebrow="ABOUT AGRI VISION" title="Technology should help us understand nature better." description="Agri Vision is a Smart Farm Advisory Council that combines specialised agent analysis with agricultural knowledge retrieval and farm-history context."/><div className="overview-grid">{[['Five agents','Weather, soil, crop health and irrigation specialists contribute to a unified advisory managed by the Advisory Manager.'],['Knowledge retrieval','The pest and disease agent retrieves crop-specific references from a ChromaDB agricultural knowledge base.'],['Farm memory','MongoDB stores observations and advisories by farm ID. Previous observations are shared with the Soil and Crop Health agents.'],['Grounded advice','The platform reports possible risks and practical recommendations, with expert inspection guidance where needed.']].map(([title, copy]) => <Card key={title} title={title}><p>{copy}</p></Card>)}</div></div>;
}

export function AuthPage({ signup = false }) {
  const { setDemoMode } = useFarm(); const navigate = useNavigate(); const [notice, setNotice] = useState('');
  function submit(e) {
    e.preventDefault();
    if (signup) {
      const data = new FormData(e.currentTarget);
      if (data.get('password') !== data.get('confirm-password')) { setNotice('The passwords do not match. Please check both fields.'); return; }
    }
    setNotice(signup ? 'Account registration is not connected to this backend. You can use demo access without creating or storing an account.' : 'Authentication is not connected to this backend. Demo access is available without creating or storing an account.');
  }
  function demo() { setDemoMode(true); navigate('/dashboard'); }
  return <div className="auth-page"><div className="auth-aside" style={{ backgroundImage: 'linear-gradient(0deg, rgba(21,42,33,.45), rgba(21,42,33,.12)), url(/images/terraced-farms.webp)' }}><Link className="auth-wordmark" to="/"><span>AGRI</span> VISION</Link><p>Every field has a story.<br/>Every season has a lesson.</p><span className="eyebrow">SMART FARM ADVISORY COUNCIL</span></div><div className="auth-main"><div className="auth-form-wrap"><Link className="inline-link" to="/">← Back to Agri Vision</Link><span className="eyebrow">{signup ? 'FARMER REGISTRATION' : 'WELCOME BACK'}</span><h1>{signup ? 'Start with your farm.' : 'Good to have you here.'}</h1><p>{signup ? 'Create a profile to explore the platform.' : 'Sign in to continue to your farm workspace.'}</p><form onSubmit={submit} className="auth-form"><label>Email address<input name="email" type="email" autoComplete="email" required placeholder="you@example.com" /></label><label>Password<input name="password" type="password" autoComplete={signup ? 'new-password' : 'current-password'} required minLength={8} placeholder="At least 8 characters" /></label>{signup && <label>Confirm password<input name="confirm-password" type="password" required minLength={8} placeholder="Re-enter your password" /></label>}<button className="button">{signup ? 'Create account' : 'Sign in'}</button></form>{notice && <p className="message info-message" role="status">{notice}</p>}<div className="auth-divider"><span>OR</span></div><button className="button button-outline demo-button" onClick={demo}>Continue with demo access</button><p className="small-note">Demo access is not authentication. Passwords are not sent or saved.</p><p className="auth-switch">{signup ? 'Already registered?' : 'New to Agri Vision?'} <Link to={signup ? '/login' : '/signup'}>{signup ? 'Login' : 'Create a profile'}</Link></p></div></div></div>;
}

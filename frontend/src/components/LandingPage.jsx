import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Wordmark } from './AppShell.jsx';
import { useFarm } from '../context/FarmContext.jsx';

const slides = [
  ['/images/paddy-fields.webp', 'Paddy fields', 'Water and soil, working together'],
  ['/images/wheat-fields.webp', 'Wheat fields', 'A season shaped by careful observation'],
  ['/images/terraced-farms.webp', 'Terraced farmland', 'Cultivated landscapes, seen clearly'],
  ['/images/healthy-crops.webp', 'Healthy crops', 'Small signs can guide better care'],
  ['/images/aerial-farmland.webp', 'Agricultural fields', 'Every field has its own pattern'],
];

function Slideshow() {
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const [failed, setFailed] = useState({});
  useEffect(() => {
    if (paused || window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return undefined;
    const timer = window.setInterval(() => setIndex((current) => (current + 1) % slides.length), 4500);
    return () => window.clearInterval(timer);
  }, [paused]);
  const step = (delta) => setIndex((current) => {
    for (let offset = 1; offset <= slides.length; offset += 1) {
      const candidate = (current + delta * offset + slides.length * 2) % slides.length;
      if (!failed[candidate]) return candidate;
    }
    return current;
  });
  return <div className="slideshow" onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)} onFocus={() => setPaused(true)} onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) setPaused(false); }} aria-label="Agricultural photography slideshow">
    {slides.map(([src, title], i) => !failed[i] && <img key={src} className={`slide-image ${i === index ? 'visible' : ''}`} src={src} alt={title} onError={() => { setFailed((old) => ({ ...old, [i]: true })); if (i === index) step(1); }} />)}
    {slides.every((_, i) => failed[i]) && <div className="slide-fallback" role="status">Field imagery is temporarily unavailable.</div>}
    <div className="slide-shade" />
    <div className="slide-caption"><span className="eyebrow">FIELD NOTES · 0{index + 1}</span><strong>{slides[index][2]}</strong></div>
    <div className="slide-controls"><button aria-label="Previous image" onClick={() => step(-1)}>←</button><div className="slide-dots">{slides.map((item, i) => <button key={item[0]} disabled={failed[i]} aria-label={`Show ${item[1]}`} aria-current={index === i} onClick={() => setIndex(i)} />)}</div><button aria-label="Next image" onClick={() => step(1)}>→</button></div>
  </div>;
}

const agents = [
  ['01', 'Weather Agent', 'Reads forecast conditions and surfaces weather-related risks.'],
  ['02', 'Soil Agent', 'Interprets moisture, pH and nutrient readings alongside farm context.'],
  ['03', 'Pest and Disease Retrieval Agent', 'Compares reported symptoms with agricultural knowledge sources.'],
  ['04', 'Irrigation Planner', 'Combines soil moisture with expected rainfall to suggest an action.'],
  ['05', 'Advisory Manager', 'Coordinates agent results into a farm-level weekly advisory.'],
];

export default function LandingPage() {
  const { account } = useFarm();
  const dashboardTarget = account ? '/dashboard' : '/demo';
  const assessmentTarget = account ? '/assessment' : '/demo/advisory';
  const signupTarget = account ? '/dashboard' : '/signup';
  const loginTarget = account ? '/dashboard' : '/login';
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  useEffect(() => { const onScroll = () => setScrolled(window.scrollY > 30); window.addEventListener('scroll', onScroll); return () => window.removeEventListener('scroll', onScroll); }, []);
  return <div className="landing">
    <header className={`landing-nav ${scrolled ? 'scrolled' : ''}`}><Wordmark light />
      <button className="mobile-menu-toggle" aria-expanded={menuOpen} aria-label="Toggle navigation" onClick={() => setMenuOpen(!menuOpen)}>☰</button>
      <nav className={menuOpen ? 'open' : ''}><a href="#home" onClick={() => setMenuOpen(false)}>Home</a><a href="#features" onClick={() => setMenuOpen(false)}>Features</a><a href="#how-it-works" onClick={() => setMenuOpen(false)}>How it works</a><a href="#about" onClick={() => setMenuOpen(false)}>About</a><Link to={loginTarget}>Login</Link><Link className="nav-cta" to={signupTarget}>{account ? 'My dashboard' : 'Get started'} <span>↗</span></Link></nav>
    </header>
    <section id="home" className="hero" style={{ backgroundImage: 'linear-gradient(90deg, rgba(15,35,27,.30), rgba(15,35,27,.08)), url(/images/hero-farmland.webp)' }}>
      <div className="hero-panel"><div className="hero-copy"><span className="eyebrow">SMART FARM ADVISORY COUNCIL</span><div className="hero-brand">AGRI VISION</div><h1>A better understanding of your farm begins here.</h1><p className="hero-description">Intelligent agricultural insights, guided by weather, soil and crop intelligence.</p><div className="hero-actions"><Link className="button" to={dashboardTarget}>Explore Agri Vision <span>↗</span></Link><a className="button button-outline" href="#how-it-works">Discover how it works</a></div><p className="hero-note">Every field has a story. Every season has a lesson.</p></div><Slideshow /></div>
      <div className="hero-coordinate">A more considered view of your farm <span>↓</span></div>
    </section>
    <section className="intro section-wrap" id="about"><div className="intro-label"><div className="intro-label-heading"><span className="eyebrow">A CLEARER VIEW</span><span className="intro-rule" /></div><figure className="intro-image"><img src="/images/paddy-fields.webp" alt="Green rice fields growing in a cultivated farm landscape" /><figcaption><span>FIELD NOTES</span><span>Healthy soil · informed decisions</span></figcaption></figure></div><div><h2>Healthy soil. Informed decisions. <em>A stronger harvest.</em></h2><p>Agri Vision brings together farm observations, local weather forecasts and agricultural knowledge to help make sense of what a field may need. Five specialised agents work in coordination, with your farm’s history available as context for each new assessment.</p><Link className="inline-link" to="/about">Explore the approach <span>↗</span></Link></div></section>
    <section id="features" className="agents-section"><div className="section-wrap"><div className="section-heading"><div><span className="eyebrow">A COUNCIL OF SPECIALISTS</span><h2>Five perspectives.<br/><em>One considered advisory.</em></h2></div><p>Independent analysis is brought together only after each specialist has done its work.</p></div><div className="agent-grid">{agents.map(([num, name, copy]) => <article className="agent-card" key={name}><span className="agent-num">{num}</span><h3>{name}</h3><p>{copy}</p><span className="agent-mark">↗</span></article>)}</div></div></section>
    <section id="how-it-works" className="workflow section-wrap"><div className="workflow-heading"><span className="eyebrow">FROM OBSERVATION TO ACTION</span><h2>Listen to the land.<br/><em>Understand its needs.</em></h2><p>One assessment gives the advisory council a shared picture to work from.</p></div><ol className="workflow-steps">{[['Farm information','Measurements, crop stage, symptoms and location.'],['Parallel analysis','Weather, soil and crop health agents work together.'],['Knowledge + context','RAG evidence and prior farm observations inform review.'],['Irrigation planning','Soil moisture and forecast rainfall guide the plan.'],['Unified farm advisory','Risks, actions and evidence brought into one view.']].map(([title, copy], i) => <li key={title}><span className="workflow-index">0{i + 1}</span><div><h3>{title}</h3><p>{copy}</p></div>{i < 4 && <span className="workflow-arrow">↓</span>}</li>)}</ol></section>
    <section className="capabilities"><div className="section-wrap capability-inner"><div><span className="eyebrow">PRACTICAL INTELLIGENCE</span><h2>Everything connected.<br/><em>Nothing overstated.</em></h2><p>Recommendations are grounded in the information provided, forecast conditions, retrieved sources and the farm’s available history.</p></div><div className="capability-list">{['Weather forecasting','Soil and nutrient analysis','Crop health intelligence','Pest and disease knowledge retrieval','Irrigation recommendations','Weekly action lists and risk alerts','Persistent farm-history memory'].map((item, i) => <div key={item}><span>0{i + 1}</span>{item}<b>↗</b></div>)}</div></div></section>
    <section className="preview-section section-wrap"><div className="preview-heading"><span className="eyebrow">A SINGLE PLACE TO RETURN TO</span><h2>See the whole field<br/><em>in one view.</em></h2><p>Bring weather, soil, crop and irrigation insights into a clear weekly advisory.</p><Link className="button" to={dashboardTarget}>{account ? 'Open the dashboard' : 'Explore the sample demo'} <span>↗</span></Link></div><div className="preview-frame"><div className="preview-top"><span>AGRI VISION / OVERVIEW</span><span>ILLUSTRATIVE PREVIEW · NOT LIVE FARM DATA</span></div><div className="preview-body"><div><span className="eyebrow">LATEST ADVISORY</span><h3>Your field, considered from every angle.</h3><p>Weather · Soil · Crop health · Irrigation</p></div><div className="preview-metrics"><div><small>SOIL</small><strong>Analysis</strong><span>Moisture · pH · NPK</span></div><div><small>WEATHER</small><strong>Forecast</strong><span>Rainfall · Temperature</span></div><div><small>WEEKLY PLAN</small><strong>Actions</strong><span>Priorities and risks</span></div></div><div className="preview-actions"><span>WEEKLY ACTION LIST</span><i></i><i></i><i></i></div></div></div></section>
    <section className="closing-cta"><span className="eyebrow">BETTER INSIGHTS FOR EVERY GROWING SEASON</span><h2>Understand your farm<br/>a little better, each time.</h2><Link className="button button-light" to={assessmentTarget}>{account ? 'Begin an assessment' : 'Explore the sample assessment'} <span>↗</span></Link><p>Technology should help us understand nature better.</p></section>
    <footer className="landing-footer"><div><Wordmark /><p>Smart Farm Advisory Council</p></div><div className="footer-links"><a href="#features">Features</a><a href="#how-it-works">How it works</a><Link to="/about">About</Link><Link to={loginTarget}>Login</Link><Link to={dashboardTarget}>{account ? 'Dashboard' : 'Explore demo'}</Link></div><small>© {new Date().getFullYear()} Agri Vision</small></footer>
  </div>;
}

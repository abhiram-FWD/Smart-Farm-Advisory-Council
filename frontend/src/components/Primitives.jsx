import { Link } from 'react-router-dom';

function evidenceLabel(value) {
  const labels = {
    verbatim_source_excerpt: 'Quoted source passage',
    source_supported_possible_risk: 'Source-supported possibility',
    source_supported_possible_risks: 'Source-supported possibilities',
    source_excerpt: 'Source excerpt',
    preliminary_rule_indicator: 'Preliminary project indicator',
    insufficient: 'Insufficient evidence',
    conflicting: 'Conflicting sources',
  };
  return labels[value] || String(value || '').replaceAll('_', ' ');
}

function readableSources(sources = []) {
  const labels = sources.map((source) => {
    const title = sourceTitle(source);
    const section = typeof source === 'object' && source.section && source.section !== 'Unavailable' ? ` · ${source.section}` : '';
    return `${title}${section}`;
  });
  return [...new Set(labels)];
}

function sourceTitle(source) {
  if (typeof source === 'string') return source.replace(/\\/g, '/').split('/').pop().replace(/\.txt$/i, '').replaceAll('_', ' ');
  const title = source?.title;
  if (title && title !== 'Unavailable') return title;
  return String(source?.source || source?.filename || 'Agricultural guide').replace(/\\/g, '/').split('/').pop().replace(/\.txt$/i, '').replaceAll('_', ' ');
}

export function PageTitle({ eyebrow, title, description, action }) {
  return <div className="page-title-row"><div><span className="eyebrow">{eyebrow}</span><h1>{title}</h1>{description && <p>{description}</p>}</div>{action}</div>;
}

export function AiNotice() {
  return <p className="ai-notice">AI-generated guidance based on available farm data and agricultural sources. Actual results may vary; consult a local agricultural expert before major decisions.</p>;
}

export function EmptyState({ title = 'No assessment yet', children }) {
  return <div className="empty-state"><span className="empty-mark">AV</span><h2>{title}</h2><p>{children || 'Your latest advisory will appear here after you complete a farm assessment.'}</p><Link className="button" to="/assessment">Start an assessment <span>↗</span></Link></div>;
}

export function Card({ title, eyebrow, children, className = '' }) {
  return <section className={`data-card ${className}`}>{(title || eyebrow) && <div className="card-heading">{eyebrow && <span className="eyebrow">{eyebrow}</span>}{title && <h2>{title}</h2>}</div>}{children}</section>;
}

export function List({ items, evidenceItems = [], empty = 'No items were returned for this assessment.' }) {
  const values = Array.isArray(items) ? items : [];
  return values.length ? <ul className="result-list">{values.map((item, i) => {
    const text = typeof item === 'string' ? item : item?.risk || item?.recommendation || item?.text || item?.action || item?.name || JSON.stringify(item);
    const evidence = typeof item === 'object' && item ? item : evidenceItems.find((entry) =>
      entry?.text === text || entry?.risk === text || entry?.recommendation === text
    );
    const sources = evidence?.sources || evidence?.evidence_sources || [];
    return <li key={`${i}-${text}`}>{text}{evidence?.reported_symptoms?.length > 0 && <p>Possible link to: {evidence.reported_symptoms.join(', ')}</p>}{evidence?.why_relevant && <p>{evidence.why_relevant}</p>}{evidence?.impact && <p>Impact: {evidence.impact}</p>}{evidence?.symptoms_to_check?.length > 0 && <p>Check for: {evidence.symptoms_to_check.join(', ')}</p>}{evidence?.inspection_step && <p>Inspect: {evidence.inspection_step}</p>}{evidence?.recommended_action && <p><strong>Action:</strong> {evidence.recommended_action}</p>}{evidence?.priority && <small className="small-note">{evidence.priority} priority</small>}{evidence?.day && <small className="small-note">{evidence.day}</small>}{sources.length > 0 && <small className="list-source">Source: {readableSources(sources).join('; ')}</small>}</li>;
  })}</ul> : <p className="muted">{empty}</p>;
}

export function Sources({ agent }) {
  const sources = agent?.evidence_sources || agent?.retrieved_sources || [];
  const uniqueSources = [...new Map(sources.map((source, i) => {
    const key = typeof source === 'string' ? source : `${source.evidence_id || source.source || i}:${source.section || ''}`;
    return [key, source];
  })).values()];
  return uniqueSources.length ? <details className="source-details"><summary>Guidance based on agricultural knowledge sources - View sources</summary><div className="source-wrap">{uniqueSources.map((source, i) => {
    if (typeof source === 'string') return <span className="source-tag" key={`${source}-${i}`}>{sourceTitle(source)}</span>;
    const title = sourceTitle(source);
    const section = source.section && source.section !== 'Unavailable' ? ` · ${source.section}` : '';
    return <span className="source-tag" key={`${source.evidence_id || source.source || i}-${i}`}>
      {title}{section}
      {source.source_url !== 'Unavailable' && <small> · <a href={source.source_url} target="_blank" rel="noreferrer">Open source</a></small>}
    </span>;
  })}</div></details> : null;
}

export function Meter({ label, value, suffix = '' }) {
  const n = Number(value);
  return <div className="meter-row"><div><span>{label}</span><strong>{Number.isFinite(n) ? `${n}${suffix}` : '—'}</strong></div>{Number.isFinite(n) && <div className="meter-track"><span style={{ width: `${Math.max(0, Math.min(100, n))}%` }} /></div>}</div>;
}

import { Link } from 'react-router-dom';

export function PageTitle({ eyebrow, title, description, action }) {
  return <div className="page-title-row"><div><span className="eyebrow">{eyebrow}</span><h1>{title}</h1>{description && <p>{description}</p>}</div>{action}</div>;
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
    const text = typeof item === 'string' ? item : item?.risk || item?.recommendation || JSON.stringify(item);
    const evidence = typeof item === 'object' && item ? item : evidenceItems.find((entry) =>
      entry?.text === text || entry?.risk === text || entry?.recommendation === text
    );
    const sources = evidence?.sources || evidence?.evidence_sources || [];
    return <li key={`${i}-${text}`}>{text}{evidence?.evidence_status && <small className="small-note">Evidence status: {evidence.evidence_status}</small>}{sources.length > 0 && <small>Source: {sources.map((source) => { const title = typeof source === 'string' ? source : source.title && source.title !== 'Unavailable' ? source.title : source.filename || source.source || 'Source unavailable'; const section = typeof source === 'object' && source.section && source.section !== 'Unavailable' ? ` · ${source.section}` : ''; return `${title}${section}`; }).join('; ')}</small>}</li>;
  })}</ul> : <p className="muted">{empty}</p>;
}

export function Sources({ agent }) {
  const sources = agent?.evidence_sources || agent?.retrieved_sources || [];
  return <div className="source-wrap">{sources.length ? sources.map((source, i) => {
    if (typeof source === 'string') return <span className="source-tag" key={`${source}-${i}`}>{source}</span>;
    const title = source.title && source.title !== 'Unavailable' ? source.title : source.filename || source.source || 'Source title unavailable';
    const section = source.section && source.section !== 'Unavailable' ? ` · ${source.section}` : '';
    const filename = source.filename && source.filename !== title ? ` (${source.filename})` : '';
    return <span className="source-tag" key={`${source.evidence_id || source.source || i}-${i}`}>
      {title}{filename}{section}
      {source.source_url === 'Unavailable' && <small> · Original reference unavailable</small>}
    </span>;
  }) : <p className="muted">No relevant knowledge sources were returned.</p>}</div>;
}

export function Meter({ label, value, suffix = '' }) {
  const n = Number(value);
  return <div className="meter-row"><div><span>{label}</span><strong>{Number.isFinite(n) ? `${n}${suffix}` : '—'}</strong></div>{Number.isFinite(n) && <div className="meter-track"><span style={{ width: `${Math.max(0, Math.min(100, n))}%` }} /></div>}</div>;
}

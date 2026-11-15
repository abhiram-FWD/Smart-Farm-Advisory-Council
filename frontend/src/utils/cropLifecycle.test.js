import { describe, expect, it } from 'vitest';
import { compareMeasurements, compareRiskAlerts, daysSincePlanting, growthStages } from './cropLifecycle.js';

describe('crop lifecycle and observed comparisons', () => {
  it('uses crop-specific stages and does not apply wheat stages to rice', () => {
    expect(growthStages('wheat')).toContain('Crown root initiation');
    expect(growthStages('rice')).toContain('Panicle initiation');
    expect(growthStages('rice')).not.toContain('Crown root initiation');
    expect(growthStages('maize')).toContain('Tasseling');
    expect(growthStages('cotton')).toContain('Boll development');
    expect(growthStages('tomato')).toContain('Fruit development');
  });

  it('calculates days only from a valid past planting date', () => {
    expect(daysSincePlanting('2026-11-10', new Date('2026-11-14T12:00:00'))).toBe(4);
    expect(daysSincePlanting('2026-11-15', new Date('2026-11-14T12:00:00'))).toBeNull();
  });

  it('compares only available comparable actual measurements', () => {
    const rows = compareMeasurements(
      { observation: { soil_moisture: 20, soil_ph: null, nitrogen: 10 } },
      { observation: { soil_moisture: 25, soil_ph: 6, nitrogen: 12 } },
    );
    expect(rows).toEqual([
      { field: 'soil_moisture', previous: 20, latest: 25, change: 5 },
    ]);
  });

  it('reports resolved and newly observed risks without inventing causes', () => {
    expect(compareRiskAlerts(
      { risk_alerts: [{ risk: 'Old risk' }, { risk: 'Stable risk' }] },
      { risk_alerts: [{ risk: 'New risk' }, { risk: 'Stable risk' }] },
    )).toEqual({ resolved: ['old risk'], newlyDetected: ['new risk'], stable: ['stable risk'] });
  });
});

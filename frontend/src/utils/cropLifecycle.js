const STAGES = {
  wheat: ['Sowing', 'Germination', 'Crown root initiation', 'Tillering', 'Stem elongation', 'Booting', 'Heading', 'Flowering', 'Grain filling', 'Maturity'],
  rice: ['Nursery or establishment', 'Transplanting or direct seeding', 'Tillering', 'Panicle initiation', 'Booting', 'Flowering', 'Grain filling', 'Maturity'],
  maize: ['Sowing', 'Emergence', 'Vegetative growth', 'Tasseling', 'Silking', 'Grain filling', 'Maturity'],
  cotton: ['Sowing', 'Emergence', 'Vegetative growth', 'Squaring', 'Flowering', 'Boll development', 'Boll opening'],
  tomato: ['Sowing or transplanting', 'Vegetative growth', 'Flowering', 'Fruit development', 'Ripening', 'Harvest'],
};

export function growthStages(cropName) {
  return STAGES[String(cropName || '').trim().toLowerCase()] || ['Sowing or planting', 'Establishment', 'Vegetative growth', 'Flowering or reproductive stage', 'Filling or fruit development', 'Maturity or harvest'];
}

export function daysSincePlanting(plantingDate, now = new Date()) {
  if (!plantingDate) return null;
  const planted = new Date(`${plantingDate}T00:00:00`);
  if (Number.isNaN(planted.getTime()) || planted > now) return null;
  return Math.floor((new Date(now.getFullYear(), now.getMonth(), now.getDate()) - planted) / 86400000);
}

export function compareMeasurements(previous, latest) {
  // Nutrient units and test methods are not captured by the current assessment form.
  return ['soil_moisture', 'soil_ph']
    .flatMap((field) => {
      const oldValue = previous?.observation?.[field];
      const newValue = latest?.observation?.[field];
      if (![oldValue, newValue].every((value) => typeof value === 'number' && Number.isFinite(value))) return [];
      return [{ field, previous: oldValue, latest: newValue, change: newValue - oldValue }];
    });
}

export function compareRiskAlerts(previousAdvisory, latestAdvisory) {
  const previous = new Set((previousAdvisory?.risk_alerts || []).map((item) => item?.risk?.trim().toLowerCase()).filter(Boolean));
  const latest = new Set((latestAdvisory?.risk_alerts || []).map((item) => item?.risk?.trim().toLowerCase()).filter(Boolean));
  return {
    resolved: [...previous].filter((risk) => !latest.has(risk)),
    newlyDetected: [...latest].filter((risk) => !previous.has(risk)),
    stable: [...latest].filter((risk) => previous.has(risk)),
  };
}

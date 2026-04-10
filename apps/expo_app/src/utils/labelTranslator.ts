// Full lookup table of known rFactor 2 SVM parameter → Spanish translation.
// Keys are matched case-insensitively and with/without the "Setting" suffix.
const PARAM_LOOKUP: Record<string, string> = {
  // --- Wheel corners (FRONTLEFT / FRONTRIGHT / REARLEFT / REARRIGHT) ---
  CamberSetting: 'Caída',
  PressureSetting: 'Presión del Neumático',
  PackerSetting: 'Tope de Suspensión',
  SpringSetting: 'Dureza del Muelle',
  TenderSpringSetting: 'Muelle Auxiliar',
  TenderTravelSetting: 'Recorrido del Muelle Auxiliar',
  SpringRubberSetting: 'Goma del Muelle',
  RideHeightSetting: 'Altura de Rodadura',
  SlowBumpSetting: 'Amortiguador Compresión Lenta',
  FastBumpSetting: 'Amortiguador Compresión Rápida',
  SlowReboundSetting: 'Amortiguador Extensión Lenta',
  FastReboundSetting: 'Amortiguador Extensión Rápida',
  BrakeDiscSetting: 'Disco de Freno',
  BrakePadSetting: 'Pastilla de Freno',
  // --- Suspension ---
  FrontAntiSwaySetting: 'Barra Estabilizadora Delantera',
  RearAntiSwaySetting: 'Barra Estabilizadora Trasera',
  FrontToeInSetting: 'Convergencia Delantera',
  RearToeInSetting: 'Convergencia Trasera',
  FrontToeOffsetSetting: 'Offset de Convergencia Delantera',
  RearToeOffsetSetting: 'Offset de Convergencia Trasera',
  LeftCasterSetting: 'Avance Izquierdo',
  RightCasterSetting: 'Avance Derecho',
  FrontWheelTrackSetting: 'Vía Delantera',
  RearWheelTrackSetting: 'Vía Trasera',
  LeftTrackBarSetting: 'Barra Panhard Izquierda',
  RightTrackBarSetting: 'Barra Panhard Derecha',
  Front3rdSpringSetting: '3er Muelle Delantero',
  Rear3rdSpringSetting: '3er Muelle Trasero',
  Front3rdPackerSetting: 'Tope del 3er Muelle Delantero',
  Rear3rdPackerSetting: 'Tope del 3er Muelle Trasero',
  Front3rdTenderSpringSetting: 'Muelle Auxiliar 3er Delantero',
  Rear3rdTenderSpringSetting: 'Muelle Auxiliar 3er Trasero',
  Front3rdTenderTravelSetting: 'Recorrido Muelle Auxiliar 3er Delantero',
  Rear3rdTenderTravelSetting: 'Recorrido Muelle Auxiliar 3er Trasero',
  Front3rdSlowBumpSetting: 'Compresión Lenta 3er Muelle Delantero',
  Front3rdFastBumpSetting: 'Compresión Rápida 3er Muelle Delantero',
  Front3rdSlowReboundSetting: 'Extensión Lenta 3er Muelle Delantero',
  Front3rdFastReboundSetting: 'Extensión Rápida 3er Muelle Delantero',
  Rear3rdSlowBumpSetting: 'Compresión Lenta 3er Muelle Trasero',
  Rear3rdFastBumpSetting: 'Compresión Rápida 3er Muelle Trasero',
  Rear3rdSlowReboundSetting: 'Extensión Lenta 3er Muelle Trasero',
  Rear3rdFastReboundSetting: 'Extensión Rápida 3er Muelle Trasero',
  // --- Controls ---
  BrakePressureSetting: 'Presión de Frenada',
  RearBrakeSetting: 'Reparto de Frenada Trasero',
  SteerLockSetting: 'Ángulo de Bloqueo de Dirección',
  ABSSetting: 'Sistema ABS',
  TCSetting: 'Control de Tracción',
  AntilockBrakeSystemMapSetting: 'Mapa de ABS',
  TractionControlMapSetting: 'Mapa de Control de Tracción',
  TCSlipAngleMapSetting: 'Mapa de Ángulo de Deslizamiento TC',
  TCPowerCutMapSetting: 'Mapa de Corte de Potencia TC',
  HandbrakePressSetting: 'Presión del Freno de Mano',
  HandfrontbrakePressSetting: 'Presión del Freno de Mano Delantero',
  // --- Driveline ---
  DiffPowerSetting: 'Bloqueo del Diferencial en Aceleración',
  DiffCoastSetting: 'Bloqueo del Diferencial en Retención',
  DiffPreloadSetting: 'Precarga del Diferencial',
  DiffPumpSetting: 'Bomba del Diferencial',
  FinalDriveSetting: 'Relación de Transmisión Final',
  RearSplitSetting: 'Distribución de Tracción',
  RatioSetSetting: 'Conjunto de Relaciones',
  GearAutoUpShiftSetting: 'Cambio Automático Ascendente',
  GearAutoDownShiftSetting: 'Cambio Automático Descendente',
  ReverseSetting: 'Marcha Atrás',
  // --- Engine ---
  EngineBrakingMapSetting: 'Mapa de Freno Motor',
  EngineBoostSetting: 'Boost del Motor',
  EngineMixtureSetting: 'Mezcla del Motor',
  RevLimitSetting: 'Límite de Revoluciones',
  RegenerationMapSetting: 'Mapa de Regeneración',
  ElectricMotorMapSetting: 'Mapa del Motor Eléctrico',
  Push2PassMapSetting: 'Mapa Push-to-Pass',
  // --- General ---
  FuelSetting: 'Combustible',
  CGRearSetting: 'Centro de Gravedad Trasero',
  CGHeightSetting: 'Altura del Centro de Gravedad',
  CGRightSetting: 'Centro de Gravedad Derecho',
  WedgeSetting: 'Cuña (Peso en Cruz)',
  FrontTireCompoundSetting: 'Compuesto del Neumático Delantero',
  RearTireCompoundSetting: 'Compuesto del Neumático Trasero',
  NumPitstopsSetting: 'Número de Paradas en Boxes',
  Pitstop1Setting: '1ª Parada en Boxes',
  Pitstop2Setting: '2ª Parada en Boxes',
  Pitstop3Setting: '3ª Parada en Boxes',
  // --- Aerodynamics ---
  BrakeDuctSetting: 'Entrada de Aire del Freno Delantero',
  BrakeDuctRearSetting: 'Entrada de Aire del Freno Trasero',
  OilRadiatorSetting: 'Radiador de Aceite',
  WaterRadiatorSetting: 'Radiador de Agua',
  FWSetting: 'Alerón Delantero',
  RWSetting: 'Alerón Trasero',
  // --- Body / Fender ---
  FenderFlareSetting: 'Deflector de Guardabarros',
};

const SECTION_TRANSLATIONS: Record<string, string> = {
  FRONTLEFT: 'Delantera Izquierda',
  FRONTRIGHT: 'Delantera Derecha',
  REARLEFT: 'Trasera Izquierda',
  REARRIGHT: 'Trasera Derecha',
  FRONTWING: 'Alerón Delantero',
  REARWING: 'Alerón Trasero',
  SUSPENSION: 'Suspensión',
  CONTROLS: 'Controles',
  ENGINE: 'Motor',
  DRIVELINE: 'Transmisión',
  BODYAERO: 'Aerodinámica de Carrocería',
  GENERAL: 'General',
  BASIC: 'Básico',
  CHASSIS: 'Chasis',
  AERO: 'Aerodinámica',
  DRIVETRAIN: 'Transmisión',
  BRAKES: 'Frenos',
  TYRES: 'Neumáticos',
  TIRES: 'Neumáticos',
  FRONT: 'Delante',
  REAR: 'Detrás',
};

// Fallback: token-level translation for unknown parameters.
// Tokens that appear as synonyms (ride/height) — keep only one if both appear.
const TOKEN_TRANSLATIONS: Record<string, string> = {
  front: 'delantero',
  rear: 'trasero',
  left: 'izquierdo',
  right: 'derecho',
  spring: 'muelle',
  rate: 'tasa',
  ride: 'altura de rodadura',
  height: 'altura',
  damper: 'amortiguador',
  bump: 'compresión',
  rebound: 'extensión',
  arb: 'barra estabilizadora',
  anti: 'anti',
  roll: 'balanceo',
  brake: 'freno',
  bias: 'reparto',
  pressure: 'presión',
  toe: 'convergencia',
  camber: 'caída',
  caster: 'avance',
  wing: 'alerón',
  diff: 'diferencial',
  differential: 'diferencial',
  preload: 'precarga',
  fuel: 'combustible',
  engine: 'motor',
  cooling: 'refrigeración',
  radiator: 'radiador',
  clutch: 'embrague',
  gear: 'marcha',
  ratio: 'relación',
  setting: '', // stripped from fallback
  power: 'potencia',
  coast: 'retención',
  map: 'mapa',
  fast: 'rápida',
  slow: 'lenta',
  packer: 'tope',
  tender: 'auxiliar',
  travel: 'recorrido',
  rubber: 'goma',
  disc: 'disco',
  pad: 'pastilla',
  compound: 'compuesto',
  tyre: 'neumático',
  tire: 'neumático',
  track: 'vía',
  bar: 'barra',
  sway: 'estabilizadora',
  limit: 'límite',
  rev: 'revolución',
};

function humanize(raw: string): string {
  return raw
    .replace(/[_-]+/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/([A-Z]+)([A-Z][a-z])/g, '$1 $2')
    .replace(/\s+/g, ' ')
    .trim();
}

function titleCase(text: string): string {
  return text
    .split(' ')
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

function fallbackTranslate(raw: string): string {
  // Strip trailing "Setting"
  const stripped = raw.replace(/Setting$/i, '');
  const words = humanize(stripped).split(' ');
  const translated: string[] = [];
  const seenTranslations = new Set<string>();

  for (const w of words) {
    const lower = w.toLowerCase();
    const t = TOKEN_TRANSLATIONS[lower];
    if (t === '') continue; // explicitly stripped (e.g. "setting")
    const value = t ?? w;
    // De-duplicate: skip if this translated value is already present
    const normalised = value.toLowerCase();
    if (seenTranslations.has(normalised)) continue;
    seenTranslations.add(normalised);
    translated.push(value);
  }

  return titleCase(translated.join(' '));
}

export function toSpanishSectionName(section: string): string {
  const key = section.trim().toUpperCase();
  return SECTION_TRANSLATIONS[key] ?? titleCase(humanize(section));
}

export function toSpanishParameterName(parameter: string): string {
  if (!parameter.trim()) return parameter;

  // 1. Exact match in lookup table
  const exact = PARAM_LOOKUP[parameter];
  if (exact) return exact;

  // 2. Case-insensitive match
  const lower = parameter.toLowerCase();
  for (const [key, val] of Object.entries(PARAM_LOOKUP)) {
    if (key.toLowerCase() === lower) return val;
  }

  // 3. Try without trailing "Setting"
  const withoutSuffix = parameter.replace(/Setting$/i, '') + 'Setting';
  const suffixed = PARAM_LOOKUP[withoutSuffix];
  if (suffixed) return suffixed;

  // 4. Fallback: token-level translation with de-duplication
  return fallbackTranslate(parameter);
}

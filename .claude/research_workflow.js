export const meta = {
  name: 'town-research',
  description: 'Web-research real info for MA in-budget towns + their neighborhoods',
  phases: [{ title: 'Research', detail: 'one web-research agent per town' }],
}

const TOWN_SCHEMA = {
  type: 'object',
  required: ['geoid', 'why', 'vibe', 'neighborhoods', 'spots', 'confidence'],
  additionalProperties: false,
  properties: {
    geoid: { type: 'string', description: 'echo back the exact geoid given' },
    why: { type: 'string', description: '2-3 sentences: real, specific reasons someone wants to live here' },
    vibe: { type: 'string', description: 'short phrase capturing the feel (e.g. "gritty, revitalizing port city")' },
    best_side: { type: 'string', description: 'which part/side of town is most desirable and why (real)' },
    neighborhoods: {
      type: 'array',
      description: 'one entry per provided neighborhood name, with real character + a named cool spot',
      items: {
        type: 'object', required: ['name', 'blurb'], additionalProperties: false,
        properties: { name: { type: 'string' }, blurb: { type: 'string', description: '1-2 sentences, concrete & real' } },
      },
    },
    spots: { type: 'array', items: { type: 'string' }, description: 'real named local places: parks, restaurants, landmarks, culture' },
    schools_note: { type: 'string', description: 'qualitative public-school reputation (brief, sourced)' },
    safety_note: { type: 'string', description: 'general safety reputation / which areas (brief, sourced)' },
    market_note: { type: 'string', description: 'recent development / housing-market dynamics worth knowing' },
    sources: { type: 'array', items: { type: 'string' }, description: 'URLs you actually used' },
    confidence: { type: 'string', enum: ['high', 'med', 'low'] },
  },
}

let A = args
if (typeof A === 'string') { try { A = JSON.parse(A) } catch (e) { A = null } }
let towns = (A && A.towns) || A || []
if (!Array.isArray(towns)) towns = []
log(`Researching ${towns.length} towns`)
if (!towns.length) return { results: [], error: 'no towns in args' }

function prompt(t) {
  const hoods = (t.hoods || []).join(', ')
  return `You are researching the Massachusetts town/city of **${t.name}** (${t.county} County) for a first-time homebuyer with a $400-600k budget who cares about appreciation and being a landlord. A typical home there is about $${Math.round((t.price||0)/1000)}k.

Use the **WebSearch** tool (load it via ToolSearch with query "select:WebSearch" if it isn't already available, and WebFetch similarly) to find REAL, current, specific information. Run a few targeted searches (e.g. "${t.name} MA best neighborhoods", "${t.name} MA things to do", "${t.name} MA schools reputation", "${t.name} MA real estate market 2025 2026", "is ${t.name} MA safe").

Fill the structured object:
- why: the genuine, specific draws of living in ${t.name} (name real employers, attractions, transit, character — not generic filler).
- vibe: a short honest phrase.
- best_side: which part/side of ${t.name} is most desirable and why (north/south/a named district), per what you find.
- neighborhoods: one entry for EACH of these areas with real character + a named local spot: ${hoods || '(use the most notable neighborhoods you find)'}.
- spots: 5-10 REAL named places (parks, restaurants, breweries, museums, landmarks).
- schools_note, safety_note, market_note: brief, concrete, sourced.
- sources: the URLs you actually used.
- confidence: high/med/low based on how much solid info you found.

CRITICAL: Only state things you can verify from the search results. If you cannot verify something, keep that field brief or leave it empty — do NOT invent names, statistics, or claims. Set geoid to exactly "${t.geoid}". Be concise and concrete.`
}

const results = await pipeline(
  towns,
  (t) => agent(prompt(t), { label: `research:${t.name}`, phase: 'Research', schema: TOWN_SCHEMA })
    .then(r => (r ? { ...r, geoid: t.geoid, name: t.name } : null)),
)

const ok = results.filter(Boolean)
log(`Got ${ok.length}/${towns.length} town research records`)
return { results: ok }

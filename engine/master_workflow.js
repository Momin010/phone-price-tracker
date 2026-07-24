export const meta = {
  name: 'phone-screen-extract',
  description: 'Classify + adversarially verify iPhone X+ screen prices from pre-scraped site data',
  phases: [
    { title: 'Classify', detail: 'per-site: label each product (part vs service, model, grade, keep?)' },
    { title: 'Verify', detail: 'adversarial skeptic re-checks every kept row' },
    { title: 'Synthesize', detail: 'dedupe + coverage report' },
  ],
}

// args = { file: "/abs/path/prepass.json", domains: [{domain, country}] }
// Agents read their slice from the file (Read tool) so prices stay verbatim;
// we re-join authoritative price/url from the same file after the run.
const A = typeof args === 'string' ? JSON.parse(args) : (args || {})
const FILE = A.file || '/tmp/prepass30.json'

// ---- what Art actually wants (shared context for every agent) ----
const SPEC = `
CLIENT REQUIREMENT (Art, sells/buys phone-screen PARTS):
- Wants iPhone DISPLAY/SCREEN parts, models iPhone X and UP.
- "X and up" = iPhone X, XR, XS, XS Max, and any numbered iPhone 11,12,13,14,15,16,17 or higher (incl. Pro / Pro Max / Plus / mini / e variants). EXCLUDE iPhone 8 and older, and ALL iPhone SE (old screen tech).
- Wants BARE SCREEN PARTS you can buy/ship (LCD / OLED / display assembly).
- Grade matters: ORIGINAL / OEM / genuine / pulled vs AFTERMARKET (copy / incell / soft-oled / compatible). Capture both but label grade correctly.
- NOT wanted (drop these): repair SERVICES ("display reparatur/repair/vaihto" = labor, not a part), whole phones, cases, tools, adhesives, batteries, back glass, cameras, protectors, frames-only.
- A screen part price is realistically ~10–600 in local currency (EUR/PLN/etc). Treat 0, or absurd values (>~1500 EUR-equivalent, or a whole-phone price like 5000) as NOT a valid screen-part price.
`

const CLASSIFY_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['rows'],
  properties: {
    rows: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['name', 'url', 'model', 'is_iphone_x_plus', 'item_type', 'grade', 'price', 'currency', 'keep', 'reason'],
        properties: {
          name: { type: 'string' },
          url: { type: ['string', 'null'] },
          model: { type: ['string', 'null'], description: 'normalized e.g. "iPhone 15 Pro" or null' },
          is_iphone_x_plus: { type: 'boolean' },
          item_type: { type: 'string', enum: ['bare_screen_part', 'repair_service', 'accessory', 'phone', 'other'] },
          grade: { type: 'string', enum: ['original', 'aftermarket', 'unknown'] },
          price: { type: ['number', 'null'] },
          currency: { type: ['string', 'null'] },
          keep: { type: 'boolean', description: 'true only if bare_screen_part AND iPhone X+ AND plausible price' },
          reason: { type: 'string' },
        },
      },
    },
  },
}

const VERIFY_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['verified', 'dropped'],
  properties: {
    verified: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['name', 'url', 'model', 'grade', 'price', 'currency', 'confidence', 'reason'],
        properties: {
          name: { type: 'string' },
          url: { type: ['string', 'null'] },
          model: { type: 'string' },
          grade: { type: 'string', enum: ['original', 'aftermarket', 'unknown'] },
          price: { type: 'number' },
          currency: { type: ['string', 'null'] },
          confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
          reason: { type: 'string' },
        },
      },
    },
    dropped: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['name', 'reason'],
        properties: { name: { type: 'string' }, reason: { type: 'string' } },
      },
    },
  },
}

function classifyPrompt(d, file) {
  return `${SPEC}

You are classifying scraped product candidates from the shop "${d.domain}" (country: ${d.country}).

STEP 1 — Load the data: use the Read tool on the file "${file}". It contains a JSON array of site objects.
Find the ONE object whose "domain" == "${d.domain}" and take its "products" array. If that site has no
products (empty array), return {"rows": []}.

STEP 2 — For EACH product, decide: normalized model, is it iPhone X+?, item_type, grade, and whether to KEEP
it (keep = bare_screen_part AND iPhone X+ AND plausible screen-part price). Product names may be in any European
language (fr/de/nl/it/pl/es/pt) — interpret them. Copy each product's "url", "price", "currency" VERBATIM from
the file into your row (do not alter numbers). Return one row per product.`
}

function verifyPrompt(domain, rows) {
  return `${SPEC}

You are an ADVERSARIAL VERIFIER. Another agent marked the rows below (from shop "${domain}") as keepers.
Your job is to REFUTE mistakes. Be skeptical; default to dropping anything that is not clearly a genuine
iPhone X+ BARE SCREEN PART with a plausible price. Drop repair services, accessories, phones, wrong/older
models, and implausible prices (0, whole-phone prices, absurd values). For survivors, assign confidence and
normalize model + grade. Return verified survivors and a dropped list with reasons.

ROWS TO VERIFY (JSON):
${JSON.stringify(rows, null, 1)}`
}

// ---- derive the site list from the pre-pass file (unless passed explicitly) ----
const BOOTSTRAP_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['domains'],
  properties: {
    domains: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false, required: ['domain', 'country'],
        properties: { domain: { type: 'string' }, country: { type: ['string', 'null'] } },
      },
    },
  },
}
let domains = A.domains
if (!domains) {
  log(`bootstrapping site list from ${FILE}`)
  const b = await agent(
    `Use the Read tool on the file "${FILE}". It is a JSON array of site objects, each with "domain",
"country", and a "products" array. Return {"domains": [...]} listing every site that has AT LEAST ONE
product with a non-null "price". Skip sites with no priced products. Return domain + country only.`,
    { label: 'bootstrap:site-list', phase: 'Classify', schema: BOOTSTRAP_SCHEMA, agentType: 'general-purpose' }
  )
  domains = b.domains || []
  log(`${domains.length} sites have priced products`)
}

// ---- pipeline: classify -> verify, per site, no barrier ----
const perSite = await pipeline(
  domains,
  (d) =>
    agent(classifyPrompt(d, FILE), {
      label: `classify:${d.domain}`, phase: 'Classify', schema: CLASSIFY_SCHEMA,
      agentType: 'general-purpose',
    }).then((c) => ({ classified: c, domain: d.domain, country: d.country })),
  (prev, d) => {
    const keep = (prev?.classified?.rows || []).filter((r) => r.keep && r.price != null)
    const preDropped = (prev?.classified?.rows || []).filter((r) => !r.keep).map((r) => ({ name: r.name, reason: r.reason || 'not kept' }))
    if (!keep.length) return { domain: d.domain, country: d.country, verified: [], dropped: preDropped }
    return agent(verifyPrompt(d.domain, keep), {
      label: `verify:${d.domain}`, phase: 'Verify', schema: VERIFY_SCHEMA,
    }).then((v) => ({
      domain: d.domain, country: d.country,
      verified: v?.verified || [],
      dropped: [...preDropped, ...(v?.dropped || [])],
      verify_failed: !v,
    }))
  }
)

// ---- synthesize (deterministic) ----
phase('Synthesize')
const clean = perSite.filter(Boolean)
const allVerified = clean.flatMap((s) =>
  (s.verified || []).map((r) => ({ ...r, domain: s.domain, country: s.country }))
)
// dedupe by url (fallback domain+model+grade)
const seen = new Set()
const deduped = []
for (const r of allVerified) {
  const k = r.url || `${r.domain}|${r.model}|${r.grade}`
  if (seen.has(k)) continue
  seen.add(k); deduped.push(r)
}
const summary = {
  sites_in: domains.length,
  sites_with_verified: clean.filter((s) => (s.verified || []).length).length,
  verified_rows: deduped.length,
  originals: deduped.filter((r) => r.grade === 'original').length,
  aftermarket: deduped.filter((r) => r.grade === 'aftermarket').length,
  by_country: deduped.reduce((a, r) => ((a[r.country] = (a[r.country] || 0) + 1), a), {}),
}
log(`verified ${deduped.length} rows across ${summary.sites_with_verified} sites (${summary.originals} original, ${summary.aftermarket} aftermarket)`)

return { summary, verified: deduped, coverage: clean.map((s) => ({ domain: s.domain, country: s.country, verified: (s.verified || []).length, dropped: (s.dropped || []).length, note: s.note })) }

# Project Nakshatra — Command Dashboard (Frontend)

Next.js (App Router), TypeScript, Tailwind CSS, shadcn/ui, MapLibre GL JS &
Recharts disaster command dashboard for the GeoAI decision support system.

## Screens

| Route | Purpose |
| --- | --- |
| `/overview` | Top-line KPIs, Uttarakhand vs Assam district comparison, stacked hazard + relocation-priority charts |
| `/map` | Multi-layer interactive MapLibre risk map (hazard/zone/infrastructure toggles, clickable habitations) |
| `/settlement/[id]` | per-habitation risk, SHAP driver decomposition, civil capacity & evidence |
| `/relocation` | allocation demand matrix + MCDA destination ranking governed by carrying capacity |
| `/scenario` | what-if simulator with an invariant-baseline "SIMULATION MODE" banner |

## Visual language

- Red/yellow/green habitation zones are rendered with hard-contrast CSS
  variables (`--zone-red`/`--zone-yellow`/`--zone-green`).
- Evidence `missing` or `low_confidence` is **never** folded into a zone or
  zeroed. It always surfaces as an explicit grey/dashed badge (settlement,
  map markers, charts). Backend `ValuedFeature.status` matches the same grammar.

## API integration

All screens resolve through `src/lib/api.ts`, which targets the FastAPI v1
gateway:

```
GET  /api/v1/overview
GET  /api/v1/map/vector-tiles
GET  /api/v1/habitations/{id}
POST /api/v1/relocation/plan
POST /api/v1/scenario/simulate
```

Defaults to `http://localhost:8000/api/v1` (matching the backend's CORS allowlist
for `http://localhost:3000`). When the gateway is unreachable the dashboard
transparently falls back to a deterministic demo store (`src/lib/demo.ts`) so
every screen is explorable offline.

## Run it

```bash
npm install
npm run dev        # http://localhost:3000
npm run lint
npm run build
```

Typed contracts live in `src/lib/types.ts`; shared zone geometry/colour
semantics in `src/lib/constants.ts`; the geography/version context in
`src/contexts/app-state.tsx`.

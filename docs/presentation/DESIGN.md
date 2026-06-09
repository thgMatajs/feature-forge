# feature-forge presentation — design spec

> Date: 2026-05-29
> Status: implemented · refreshed 2026-06-09
> Output: `docs/presentation/feature-forge.html` (single self-contained file)

## Purpose

A single HTML deck that explains what **feature-forge** is, how it works, and
where it stands today. Audience is mixed (devs + leadership + curious readers),
so depth is progressive: each slide reads cold; later slides go deeper but
never assume the reader watched in order.

The deck is for asynchronous reading AND live presentation — same artifact
serves both.

## Format

- **Deck of slides**, navigated by keyboard arrows.
- 24 slides (one concept per slide).
- Visual style: terminal / monospace / dark — matches feature-forge's CLI
  identity (`forge plan`, `forge implement`).
- One concept per slide, no walls of text.

## Slide map (24 slides, 5 acts)

### Act 1 — Opening (slides 1–2)
| # | Title | Purpose |
|---|---|---|
| 01 | Hero | `feature-forge` — "um OS pra feature mobile" + 1 tagline |
| 02 | O problema | Por que isso existe: ambiguidade no planning de feature mobile gera retrabalho |

### Act 2 — Principles (slides 3–5)
| # | Title | Purpose |
|---|---|---|
| 03 | 6 princípios | patterns≠deps · files>memory · user decides · mentor calmo · vocab nativo · reversibilidade |
| 04 | O que NÃO é | não é PM, arquiteto, code review, nem tracker |
| 05 | A interface | os 12 comandos numa grade (init, plan, implement, verify, ...) |

### Act 3 — Anatomy: the 6 layers (slides 6–12)
| # | Title | Purpose |
|---|---|---|
| 06 | Visão de cima | diagrama panorâmico das 6 camadas |
| 07 | L0 Engine Core | state machine file-driven, plan→apply→verify→commit |
| 08 | L1 Knowledge | graph + inventory + memory L1–L5 |
| 09 | L2 Integrations | ticketing MCP · docs MCP · vision · find-skills |
| 10 | L3 Capability cards | o que é card, yaml de exemplo, composição vs preset |
| 11 | L4 Orchestration | planning-conductor + execution-conductor + sub-agents |
| 12 | L5 Self-evolution | retrospective → proposed-evolutions → forge evolve |

### Act 4 — A feature end-to-end (slides 13–19)
| # | Title | Purpose |
|---|---|---|
| 13 | Big picture | fluxo plan → implement → verify (3 grandes blocos) |
| 14 | forge plan | Waves A–E do planning-conductor, output = readiness=ready |
| 15 | Subtypes + bugfix | forge plan adapta-se: product/refactor/bugfix/spike/chore, com o caminho bugfix (ticket → regression-test-first → 5-whys) |
| 16 | Os artefatos | PRD · BDD · screen-analysis · tech-spec · task-contracts |
| 17 | forge implement | Plan Mode → Apply Mode → review → commit, 1 task por vez |
| 18 | forge verify | gates duros, scope (task/feature), read-only |
| 19 | forge qa | red-team adversarial: 4 attack vectors × 4 escopos, sandbox, verdict informativo |

### Act 5 — Self-evolution + closing (slides 20–24)
| # | Title | Purpose |
|---|---|---|
| 20 | Como o forge aprende | retrospective após cada feature, padrões viram propostas |
| 21 | forge evolve | user revisa propostas, aceita/rejeita; engine nunca decide sozinho |
| 22 | Status hoje | fases 1–5 ✅, v1.0→v1.2 shipadas, autopilot a seguir |
| 23 | Roadmap | timeline v1.0 → v1.2 → autopilot, com marker em onde estamos |
| 24 | Encerramento | 1 frase forte + links pros docs canônicos |

## Visual system

### Color tokens (CSS custom properties at `:root`)
| Token | Value | Use |
|---|---|---|
| `--bg` | `#0b0f0e` | base background |
| `--bg-elev` | `#111614` | elevated cards/blocks |
| `--fg` | `#e7ece8` | primary text |
| `--fg-dim` | `#8a958f` | secondary text, captions |
| `--accent` | `#baff29` | CTAs, slide number, `$` prompt |
| `--accent-dim` | `#496900` | hover/state |
| `--rule` | `#1f2724` | lines, borders |
| `--warn` | `#ffb454` | ⏳ pending status |
| `--ok` | `#7be07b` | ✅ done status |

### Typography
- UI/headings: `'Inter', system-ui, sans-serif`
- Mono (commands, YAML, paths): `'JetBrains Mono', 'SF Mono', monospace`
- Sizes via `clamp()` for responsiveness:
  - Hero: `clamp(48px, 6vw, 88px)`
  - h1 slide: `clamp(32px, 4vw, 56px)`
  - body: `clamp(18px, 1.6vw, 22px)`
  - mono code: `0.9em`

### Spacing
- Slide = 100vw × 100vh, padding `clamp(48px, 6vw, 96px)`
- Spacing scale: `--s1: 8px` ... `--s8: 64px`
- Content max-width: 1100px, centered

## Slide block types (5 reusable classes)

| Class | Content shape |
|---|---|
| `.slide.hero` | huge title + tagline + `press → to start` hint |
| `.slide.bullets` | title + 3–6 short bullets with unicode markers |
| `.slide.diagram` | title + ASCII diagram in `<pre>` mono |
| `.slide.table` | title + 2-3 column table |
| `.slide.terminal` | title + terminal-style `<pre>` block with green `$` prompt |

Footer on every slide:
- Bottom-left: slide number `07 / 24` (mono, dim)
- Bottom-right: act label `Anatomia · L1 Knowledge` (mono, dim)
- Top: thin 2px progress bar in `--accent`

## Navigation

| Key | Action |
|---|---|
| `→` / `Space` / `PageDown` | next slide |
| `←` / `PageUp` | previous slide |
| `Home` | first slide |
| `End` | last slide |
| `Esc` | grid overview (click any to jump) |
| `?` | shortcuts overlay |

Behavior:
- Current slide stored in `location.hash` (`#7`); reload preserves position
- URL with `#N` deep-links to slide N (shareable)
- Transition: `opacity` + `translateY(8px)` ~240ms; no flashy animation
- Touch: tap right half → next, tap left half → previous (mobile fallback)

## Technical architecture

Single self-contained file:

```
docs/presentation/feature-forge.html      ~1280 lines
  ├── <style>     inline CSS, custom properties + block classes
  ├── <main>      24 sequential <section class="slide ..."> elements
  └── <script>    inline JS: keyboard, hash sync, overview, progress (~80 lines)
```

Constraints:
- No external dependencies (no CDN, no npm)
- No build step
- Opens with double-click or `open feature-forge.html`
- Works offline

## What is NOT in scope

- Schema YAML dumps slide-by-slide (linked, not pasted)
- Each sub-agent prompt explained (mentioned, not detailed)
- The full command surface migration table (linked in slide 24)
- Animations beyond fade+rise on slide change
- Server-side rendering, build pipeline, or framework
- Speaker notes mode (can be added later if needed)
- PDF export (can be done via browser print as fallback)

## Open items

None. All decisions are locked.

## Files this design will produce

1. `docs/presentation/feature-forge.html` — the deck itself
2. `docs/presentation/DESIGN.md` — this file

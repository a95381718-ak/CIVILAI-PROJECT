# CIVILAI — implementation + design plan

## Implementation approach

CIVILAI is a Flask application with an application factory, SQLAlchemy models, session authentication, server-rendered Jinja templates, vanilla JavaScript enhancement, and a small service layer for classification and simulated authority submission. SQLite is the local fallback; `DATABASE_URL` remains the production PostgreSQL switch. The core walkthrough is implemented end to end: seeded demo accounts → citizen dashboard → complaint creation → rule-based classification → review → submission attempt → simulated authority acknowledgement → receipt → authority status update → citizen timeline.

The project keeps the authority receiver logically separate inside the same Flask process. The citizen complaint, submission attempt, authority snapshot, and authority status history are distinct records. The receiver endpoint validates a bearer token, applies idempotency, creates its own authority reference, and returns a structured acknowledgement. Attachment metadata and upload validation are included; storage is local in development with a clear service boundary for Supabase Storage.

## Project structure

- `civilai/__init__.py` — application factory, config, seed data, error handlers.
- `civilai/extensions.py` — SQLAlchemy and login manager instances.
- `civilai/models.py` — users, departments, categories, complaints, attachments, submissions, histories, authority records.
- `civilai/services.py` — rule classifier, safe upload helpers, simulated authority receiver and submission orchestration.
- `civilai/routes.py` — auth, citizen, admin, authority, and receiving API blueprints.
- `civilai/templates/` — shared layout plus role-specific screens.
- `civilai/static/` — custom CSS and small progressive-enhancement JavaScript layer.
- `public/manus-routes.json` — discoverable page route manifest.

## Design direction

### Options considered

1. **Editorial civic intelligence** — 0.07. A newspaper-like civic desk with ink, mineral, and signal tones.
2. **Soft municipal modernism** — 0.06. Calm pale surfaces with blue service accents and generous rounded forms.
3. **Transit control room** — 0.04. Dark operational panels with route lines, statuses, and compact data density.

### Chosen movement: editorial civic intelligence

**Core principles:** grounded, legible, human, consequential. The interface should feel like a trusted public desk where every issue becomes a visible, trackable case—not an anonymous form submission.

**Color philosophy:** deep ink (`#10201d`) anchors authority and readability; mineral paper (`#f4f1ea`) gives the product a civic-document character; soft sage (`#dbe7de`) signals calm progress; signal orange (`#d9663d`) is reserved for actions and attention. No gradient-heavy decoration.

**Layout paradigm:** a persistent narrow left rail establishes place and role, while the content area uses asymmetric editorial blocks, a strong page header, and a primary working column with a contextual side column. Avoid centered stacks of identical cards.

**Signature elements:** the CIVILAI monogram is a split-square “C” / civic signal mark; small uppercase “desk notes” act as wayfinding labels; timeline markers use a vertical signal line with state-colored nodes.

**Interaction philosophy:** actions are explicit and calm. Submission is never implied; review and acknowledgement states are visible. Hover and focus states sharpen borders and lift only the actionable surface. Loading states use short signal pulses rather than spinners everywhere.

**Animation:** 160–220ms ease-out transitions for nav and action states; page-level reveal is a single upward 8px settle; timeline nodes can pulse once when a new state is recorded. Respect reduced-motion preferences.

**Typography system:** `DM Sans` for interface text and `Space Grotesk` for headlines, loaded with robust system fallbacks. Eyebrow labels are compact, letter-spaced, and uppercase. Numbers use tabular lining where available.

**Brand essence:** a civic case desk for turning neighborhood friction into accountable action. Personality: clear, observant, resolute.

**Brand voice:** direct and specific. Example lines: “Turn a street-level issue into a trackable case.” “Your complaint is saved; the receiving desk has not accepted it yet.”

**Wordmark & logo:** a custom inline mark combines a bracketed C with a small vertical signal bar; the wordmark uses spaced lowercase `civilai` beside it rather than a default all-caps treatment.

**Signature brand color:** signal orange `#d9663d`, used sparingly for the primary action and unresolved attention states.

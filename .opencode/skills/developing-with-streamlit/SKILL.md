---
name: developing-with-streamlit
description: Use for ALL Streamlit tasks in Qagro: creating, editing, debugging, beautifying, styling, theming, optimizing, or deploying the Streamlit dashboard (app/streamlit_app.py). Also for session state, caching, Plotly/Folium widgets, and DESIGN.md compliance. Triggers: streamlit, st., dashboard, app.py, style, CSS, theme, session state, performance, cache, fragment, slow rerun, deploy.
license: MIT
compatibility: opencode
---

# Developing with Streamlit (Qagro)

Meta-skill based on the official `streamlit/agent-skills` router
(`developing-with-streamlit`). It points to version-matched reference docs for
Streamlit development.

## How to get the reference docs

Qagro pins `streamlit==1.49.1` (see `requirements.txt`), which predates bundled
skills (>= 1.57). So the discovery script below will report "predates bundled
skills" — that is EXPECTED. In that case use the fallback, then continue with
the Qagro appendix below.

1. Run the bundled discovery script with the project directory:

```bash
python .opencode/skills/developing-with-streamlit/scripts/discover.py --project-dir C:\Users\ansar\Projects\Qagro
```

2. Interpret the result:

- **A path on stdout (exit 0)** — a `SKILL.md` inside the installed Streamlit
  package. Read it; it points into its `references/` folder (dashboards, themes,
  layouts, session state, custom components, etc.). Follow the routing table there.
- **`ERROR:` on stderr (non-zero exit)** — follow the printed instructions.
  For Qagro (Streamlit 1.49.1) expect exit 2; fall back to the complete
  Streamlit docs for LLMs: `https://docs.streamlit.io/llms-full.txt`.

`<SKILL_DIR>` is the directory containing this file; the user project dir is
`C:\Users\ansar\Projects\Qagro`. Passing `--project-dir` matters because the
script resolves `.venv`, `Pipfile`, `poetry.lock`, `pdm.lock`, `uv.lock`
relative to it.

## Routing hints (when bundled skills or llms-full.txt are available)

| Need | Look for |
|---|---|
| Slow app, caching | optimizing performance (cache, fragments, forms) |
| KPI dashboard | building dashboards (metrics, layouts) |
| Visual polish, icons | improving design, themes |
| Widget choice (selectbox vs radio vs pills) | selection widgets guide |
| Button colors, backgrounds | creating themes (use Qagro DESIGN.md first!) |
| Columns, tabs, sidebar, expanders | layouts |
| Dataframes, charts | displaying data (column config, Plotly) |
| Session state, callbacks | session state guide |
| Markdown, badges, LaTeX | markdown guide |
| Multi-page structure | multipage apps |

## Qagro appendix (project-specific, takes precedence in this repo)

Dashboard: `app/streamlit_app.py` (Plotly + Folium, CSV/GeoJSON/PDF export).
Launch: `python -m streamlit run app/streamlit_app.py` (or `run_web.bat`).
Never call bare `streamlit`/`uvicorn` — they may not be in PATH on Windows.

Mandatory rules from `DESIGN.md` (source of truth for styling):

- Tokens: `--qagro-accent #1B7A3D` (only accent, agro-green), `--qagro-ink #111111`,
  `--qagro-muted #333333`, `--qagro-paper #FFFFFF`, `--qagro-wash #F2F5F1`,
  risk red `#C0392B` / amber `#D48806`, spacing multiples of 8, radius 12px,
  font Inter/Segoe UI/system-ui. No gradients, no shadows.
- Typography is the interface: H1 36 / H2 30 / H3 26 / body 20 / caption 18;
  answer digits 46 bold with tabular-nums. One font family only.
- Technique (MAE/RMSE/R2/SHAP) lives ONLY in the "For agronomist" expander.
  Main flow is 3 plain-language steps; never show ids like `Esil`, `P_loss=`.
- Buttons min-height 60px, width 100% (farmer 50+ on a phone); <640px single column.
- Every visible string via `UI[lang]` with key parity ru/kz/en. No hardcoded Russian
  in widgets. Reuse translation dicts already in `app/streamlit_app.py`.
- `swiss-web-design` skill details the grid/whitespace rules; this skill owns
  Streamlit mechanics (`st.cache_data`, session state, fragments, forms).

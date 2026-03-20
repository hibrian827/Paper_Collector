# Paper Collector - Status

## Done
- 5,512 papers collected from DBLP (NDSS, USENIX Security, IEEE S&P, CCS), years 2020-2025
- SQLite database (`papers.db`) with FTS5 full-text search
- Flask web app (`app.py`) with search API, conference/year filtering, pagination
- Modern dark-themed frontend with search scope selector, color-coded conference tags, year filters, expandable abstracts, keyword highlighting
- Data collector (`collect.py`) with DBLP API (toc/stream/venue fallback) + Semantic Scholar for abstracts
- Python venv at `./venv/`

## Paper Counts
| Conference      | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|-----------------|------|------|------|------|------|------|
| CCS             |  149 |  226 |  288 |  293 |  419 |  396 |
| IEEE S&P        |  105 |  115 |  149 |  197 |  262 |  256 |
| NDSS            |   90 |   88 |   84 |   95 |  141 |  212 |
| USENIX Security |  160 |  248 |  257 |  423 |  419 |  440 |

## TODO (Next Session)
1. **Fetch abstracts** — only 1/5,512 papers has an abstract. Run:
   ```
   source venv/bin/activate
   python3 collect.py --abstracts-only
   ```
   Takes ~45+ min due to Semantic Scholar rate limits (0.5s/paper).

2. **Launch the app**:
   ```
   source venv/bin/activate
   python3 app.py
   ```
   Visit http://localhost:5000

## File Structure
- `collect.py` — data collection script (DBLP + Semantic Scholar)
- `app.py` — Flask web server
- `papers.db` — SQLite database (generated)
- `templates/index.html` — main page template
- `static/style.css` — styling
- `static/script.js` — frontend logic
- `requirements.txt` — Python dependencies
- `venv/` — Python virtual environment

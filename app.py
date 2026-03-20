import os
import sqlite3

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(__file__), "papers.db")


######################################################
#                HELPER FUNCTIONS                    #
######################################################


################# get_db #############################
def get_db():
  conn = sqlite3.connect(DB_PATH)
  conn.row_factory = sqlite3.Row
  return conn


######################################################
#                    FUNCTION                        #
######################################################


################### index ############################
@app.route("/")
def index():
  conn = get_db()
  c = conn.cursor()
  c.execute(
    "SELECT DISTINCT conference FROM papers ORDER BY conference"
  )
  conferences = [r["conference"] for r in c.fetchall()]
  c.execute("SELECT DISTINCT year FROM papers ORDER BY year DESC")
  years = [r["year"] for r in c.fetchall()]
  c.execute("SELECT COUNT(*) as cnt FROM papers")
  total = c.fetchone()["cnt"]
  conn.close()
  return render_template(
    "index.html",
    conferences=conferences,
    years=years,
    total=total,
  )


################# api_search #########################
@app.route("/api/search")
def api_search():
  query = request.args.get("q", "").strip()
  conference = request.args.get("conference", "")
  year = request.args.get("year", "")
  scope = request.args.get("scope", "both")
  page = int(request.args.get("page", 1))
  per_page = int(request.args.get("per_page", 25))
  offset = (page - 1) * per_page

  conn = get_db()
  c = conn.cursor()

  conditions = []
  params = []

  if query:
    if scope == "title":
      conditions.append(
        "p.id IN (SELECT rowid FROM papers_fts "
        "WHERE title MATCH ?)"
      )
    elif scope == "abstract":
      conditions.append(
        "p.id IN (SELECT rowid FROM papers_fts "
        "WHERE abstract MATCH ?)"
      )
    else:
      conditions.append(
        "p.id IN (SELECT rowid FROM papers_fts "
        "WHERE papers_fts MATCH ?)"
      )
    fts_query = " ".join(
      f'"{w}"' for w in query.split() if w
    )
    params.append(fts_query)

  if conference:
    conf_list = [
      c.strip() for c in conference.split(",") if c.strip()
    ]
    placeholders = ",".join("?" * len(conf_list))
    conditions.append(f"p.conference IN ({placeholders})")
    params.extend(conf_list)

  if year:
    year_list = [
      int(y.strip()) for y in year.split(",") if y.strip()
    ]
    placeholders = ",".join("?" * len(year_list))
    conditions.append(f"p.year IN ({placeholders})")
    params.extend(year_list)

  where = "WHERE " + " AND ".join(conditions) if conditions else ""

  c.execute(
    f"SELECT COUNT(*) as cnt FROM papers p {where}", params
  )
  total = c.fetchone()["cnt"]

  c.execute(
    f"SELECT p.* FROM papers p {where} "
    f"ORDER BY p.year DESC, p.conference, p.title "
    f"LIMIT ? OFFSET ?",
    params + [per_page, offset],
  )
  papers = [dict(r) for r in c.fetchall()]
  conn.close()

  return jsonify({
    "papers": papers,
    "total": total,
    "page": page,
    "per_page": per_page,
    "pages": (total + per_page - 1) // per_page,
  })


################# api_stats ##########################
@app.route("/api/stats")
def api_stats():
  conn = get_db()
  c = conn.cursor()
  c.execute(
    "SELECT conference, year, COUNT(*) as count "
    "FROM papers GROUP BY conference, year "
    "ORDER BY year DESC, conference"
  )
  stats = [dict(r) for r in c.fetchall()]
  conn.close()
  return jsonify(stats)


######################################################
#                      MAIN                          #
######################################################

if __name__ == "__main__":
  app.run(debug=True, port=5000)

import os
import re
import time
import sqlite3
import argparse

import requests


######################################################
#                HELPER FUNCTIONS                    #
######################################################


################# init_db ############################
def init_db(db_path="papers.db"):
  conn = sqlite3.connect(db_path)
  c = conn.cursor()
  c.execute("""
    CREATE TABLE IF NOT EXISTS papers (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      title TEXT NOT NULL,
      authors TEXT NOT NULL,
      abstract TEXT DEFAULT '',
      conference TEXT NOT NULL,
      year INTEGER NOT NULL,
      doi TEXT DEFAULT '',
      url TEXT DEFAULT '',
      UNIQUE(title, conference, year)
    )
  """)
  c.execute("""
    CREATE INDEX IF NOT EXISTS idx_conference_year
    ON papers(conference, year)
  """)
  c.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS papers_fts USING fts5(
      title, abstract, content='papers', content_rowid='id'
    )
  """)
  conn.commit()
  return conn


############### rebuild_fts ##########################
def rebuild_fts(conn):
  c = conn.cursor()
  try:
    c.execute("DROP TABLE IF EXISTS papers_fts")
  except Exception:
    pass
  c.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS papers_fts USING fts5(
      title, abstract, content='papers', content_rowid='id'
    )
  """)
  c.execute("""
    INSERT INTO papers_fts(rowid, title, abstract)
    SELECT id, title, abstract FROM papers
  """)
  conn.commit()


############### dblp_request #########################
def dblp_request(params, max_retries=3):
  url = "https://dblp.org/search/publ/api"
  for attempt in range(max_retries):
    try:
      r = requests.get(url, params=params, timeout=30)
      r.raise_for_status()
      return r.json()
    except Exception as e:
      if attempt < max_retries - 1:
        wait = (attempt + 1) * 10
        print(f"    Retry in {wait}s ({e})")
        time.sleep(wait)
      else:
        print(f"    Failed after {max_retries} attempts: {e}")
        return None


############ parse_dblp_hits #########################
def parse_dblp_hits(data):
  if not data:
    return []
  hits = data.get("result", {}).get("hits", {}).get("hit", [])
  papers = []
  for hit in hits:
    info = hit.get("info", {})
    title = info.get("title", "").rstrip(".")
    if not title:
      continue
    authors_raw = info.get("authors", {}).get("author", [])
    if isinstance(authors_raw, dict):
      authors_raw = [authors_raw]
    authors = ", ".join(
      a.get("text", a) if isinstance(a, dict) else str(a)
      for a in authors_raw
    )
    papers.append({
      "title": title,
      "authors": authors,
      "doi": info.get("doi", ""),
      "url": info.get("url", ""),
    })
  return papers


######################################################
#                    FUNCTION                        #
######################################################


############# fetch_dblp_papers ######################
def fetch_dblp_papers(conf_key, slug, year):
  print(f"  Fetching: {conf_key} {year} ...")

  # Strategy 1: toc query (most precise)
  toc = f"db/conf/{conf_key}/{slug}{year}.bht:"
  params = {"q": f"toc:{toc}", "h": "1000", "format": "json"}
  data = dblp_request(params)
  papers = parse_dblp_hits(data)

  if papers:
    print(f"    [toc] Found {len(papers)} papers")
    return papers

  time.sleep(3)

  # Strategy 2: stream + year query
  params = {
    "q": f"stream:conf/{conf_key}: year:{year}",
    "h": "1000",
    "format": "json",
  }
  data = dblp_request(params)
  papers = parse_dblp_hits(data)

  if papers:
    print(f"    [stream] Found {len(papers)} papers")
    return papers

  time.sleep(3)

  # Strategy 3: venue + year query
  venue_names = {
    "ndss": "NDSS",
    "uss": "USENIX Security",
    "sp": "SP",
    "ccs": "CCS",
  }
  venue = venue_names.get(conf_key, conf_key.upper())
  params = {
    "q": f"venue:{venue}: year:{year}",
    "h": "1000",
    "format": "json",
  }
  data = dblp_request(params)
  papers = parse_dblp_hits(data)

  if papers:
    print(f"    [venue] Found {len(papers)} papers")
    return papers

  print(f"    No results for {conf_key} {year}")
  return []


########## fetch_abstract_semantic ###################
def fetch_abstract_semantic(doi, title, session):
  if doi:
    url = (
      "https://api.semanticscholar.org/graph/v1/paper/"
      f"DOI:{doi}"
    )
    try:
      r = session.get(url, params={"fields": "abstract"}, timeout=15)
      if r.status_code == 200:
        abstract = r.json().get("abstract", "")
        if abstract:
          return abstract
      elif r.status_code == 429:
        time.sleep(5)
    except Exception:
      pass

  clean_title = re.sub(r"[^\w\s]", "", title)
  url = (
    "https://api.semanticscholar.org/graph/v1/paper/search"
  )
  params = {
    "query": clean_title[:200],
    "fields": "title,abstract",
    "limit": "3",
  }
  try:
    r = session.get(url, params=params, timeout=15)
    if r.status_code == 200:
      for paper in r.json().get("data", []):
        if paper.get("abstract"):
          pt = (paper.get("title") or "").lower().strip().rstrip(".")
          if pt == title.lower().strip().rstrip("."):
            return paper["abstract"]
    elif r.status_code == 429:
      time.sleep(5)
  except Exception:
    pass

  return ""


############ collect_conference ######################
def collect_conference(conn, conf_name, conf_key, slug, years):
  print(f"\n{'='*54}")
  print(f"  Collecting {conf_name}")
  print(f"{'='*54}")
  c = conn.cursor()

  for year in years:
    papers = fetch_dblp_papers(conf_key, slug, year)

    inserted = 0
    for p in papers:
      try:
        c.execute(
          "INSERT OR IGNORE INTO papers "
          "(title, authors, abstract, conference, year, doi, url) "
          "VALUES (?, ?, '', ?, ?, ?, ?)",
          (p["title"], p["authors"], conf_name, year, p["doi"], p["url"]),
        )
        if c.rowcount > 0:
          inserted += 1
      except sqlite3.IntegrityError:
        pass

    conn.commit()
    print(f"    Inserted {inserted} new papers for {year}")
    time.sleep(3)


############## fetch_abstract_openalex ###############
def fetch_abstract_openalex(doi, title, session):
  """Try OpenAlex API — free, no key needed, good coverage."""
  if doi:
    url = f"https://api.openalex.org/works/doi:{doi}"
    try:
      r = session.get(
        url,
        params={"select": "abstract_inverted_index"},
        headers={"User-Agent": "PaperCollector/1.0 (mailto:paper@collector.dev)"},
        timeout=15,
      )
      if r.status_code == 200:
        inv_idx = r.json().get("abstract_inverted_index")
        if inv_idx:
          pos_word = []
          for word, positions in inv_idx.items():
            for pos in positions:
              pos_word.append((pos, word))
          pos_word.sort()
          return " ".join(w for _, w in pos_word)
    except Exception:
      pass

  # Fallback: search by title
  clean_title = re.sub(r"[^\w\s]", "", title)
  url = "https://api.openalex.org/works"
  try:
    r = session.get(
      url,
      params={
        "search": clean_title[:200],
        "select": "title,abstract_inverted_index",
        "per_page": "3",
      },
      headers={"User-Agent": "PaperCollector/1.0 (mailto:paper@collector.dev)"},
      timeout=15,
    )
    if r.status_code == 200:
      for work in r.json().get("results", []):
        inv_idx = work.get("abstract_inverted_index")
        if inv_idx:
          wt = (work.get("title") or "").lower().strip().rstrip(".")
          if wt == title.lower().strip().rstrip("."):
            pos_word = []
            for word, positions in inv_idx.items():
              for pos in positions:
                pos_word.append((pos, word))
            pos_word.sort()
            return " ".join(w for _, w in pos_word)
  except Exception:
    pass

  return ""


############## fetch_abstract_crossref ###############
def fetch_abstract_crossref(doi, session):
  """Try CrossRef API — only works with DOI, returns XML abstract."""
  if not doi:
    return ""
  url = f"https://api.crossref.org/works/{doi}"
  try:
    r = session.get(
      url,
      headers={"User-Agent": "PaperCollector/1.0 (mailto:paper@collector.dev)"},
      timeout=15,
    )
    if r.status_code == 200:
      abstract = r.json().get("message", {}).get("abstract", "")
      if abstract:
        abstract = re.sub(r"<[^>]+>", "", abstract).strip()
        return abstract
  except Exception:
    pass
  return ""


########### fetch_missing_abstracts ##################
def fetch_missing_abstracts(conn, batch_size=500):
  print(f"\n{'='*54}")
  print("  Fetching missing abstracts")
  print(f"  Sources: OpenAlex -> CrossRef -> Semantic Scholar")
  print(f"{'='*54}")

  c = conn.cursor()
  c.execute(
    "SELECT id, doi, title FROM papers "
    "WHERE abstract = '' OR abstract IS NULL "
    "LIMIT ?",
    (batch_size,),
  )
  rows = c.fetchall()

  if not rows:
    print("  All papers already have abstracts!")
    return 0

  print(f"  {len(rows)} papers missing abstracts")
  session = requests.Session()
  fetched = 0
  sources = {"openalex": 0, "crossref": 0, "semantic": 0}

  for i, (paper_id, doi, title) in enumerate(rows):
    abstract = ""

    # Try OpenAlex first (fast, free, good coverage)
    abstract = fetch_abstract_openalex(doi, title, session)
    if abstract:
      sources["openalex"] += 1
    else:
      # Try CrossRef (DOI only)
      abstract = fetch_abstract_crossref(doi, session)
      if abstract:
        sources["crossref"] += 1
      else:
        # Fall back to Semantic Scholar
        abstract = fetch_abstract_semantic(doi, title, session)
        if abstract:
          sources["semantic"] += 1
        time.sleep(0.5)

    if abstract:
      c.execute(
        "UPDATE papers SET abstract = ? WHERE id = ?",
        (abstract, paper_id),
      )
      fetched += 1

    if (i + 1) % 20 == 0:
      conn.commit()
      print(
        f"    Progress: {i + 1}/{len(rows)} "
        f"({fetched} abstracts) "
        f"[OA:{sources['openalex']} CR:{sources['crossref']} SS:{sources['semantic']}]"
      )
    time.sleep(0.1)

  conn.commit()
  print(f"  Fetched {fetched}/{len(rows)} abstracts")
  print(
    f"  Sources — OpenAlex: {sources['openalex']}, "
    f"CrossRef: {sources['crossref']}, "
    f"Semantic Scholar: {sources['semantic']}"
  )
  return len(rows) - fetched


######################################################
#                      MAIN                          #
######################################################


CONFERENCES = [
  ("NDSS", "ndss", "ndss"),
  ("USENIX Security", "uss", "uss"),
  ("IEEE S&P", "sp", "sp"),
  ("CCS", "ccs", "ccs"),
]

YEARS = list(range(2020, 2026))

if __name__ == "__main__":
  parser = argparse.ArgumentParser(
    description="Collect security conference papers"
  )
  parser.add_argument(
    "--abstracts-only", action="store_true",
    help="Only fetch missing abstracts, skip paper collection",
  )
  parser.add_argument(
    "--no-abstracts", action="store_true",
    help="Skip abstract fetching",
  )
  parser.add_argument(
    "--batch-size", type=int, default=500,
    help="Batch size for abstract fetching",
  )
  args = parser.parse_args()

  db_path = os.path.join(os.path.dirname(__file__), "papers.db")
  conn = init_db(db_path)

  if not args.abstracts_only:
    for conf_name, conf_key, slug in CONFERENCES:
      collect_conference(conn, conf_name, conf_key, slug, YEARS)

  if not args.no_abstracts:
    remaining = fetch_missing_abstracts(conn, args.batch_size)
    while remaining > 0:
      print(
        f"\n  Still {remaining} papers without abstracts, "
        "running another batch..."
      )
      prev = remaining
      remaining = fetch_missing_abstracts(conn, args.batch_size)
      if remaining >= prev:
        print("  No progress on abstracts, stopping.")
        break

  rebuild_fts(conn)

  c = conn.cursor()
  c.execute("SELECT COUNT(*) FROM papers")
  total = c.fetchone()[0]
  c.execute("SELECT COUNT(*) FROM papers WHERE abstract != ''")
  with_abstract = c.fetchone()[0]
  print(f"\n{'='*54}")
  print(
    f"  Done! {total} papers total, "
    f"{with_abstract} with abstracts"
  )
  print(f"{'='*54}")

  conn.close()

from flask import Flask, jsonify, request
from flask_cors import CORS
import requests, os, json, time
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")
CACHE_FILE = "/tmp/cache.json"

QUERIES = [
    "Head of Marketing UAE",
    "Marketing Director Dubai",
    "CX Director UAE",
    "Brand Director Dubai",
    "Senior Marketing Manager UAE",
    "Head of Marketing Saudi Arabia",
    "Marketing Director Qatar"
]

TARGET_TITLES = [
    "head of marketing","marketing director","director of marketing",
    "brand director","head of cx","cx director","head of customer experience",
    "senior marketing manager","senior brand manager","vp marketing",
    "chief marketing","cmo","digital marketing director","head of digital"
]

def is_relevant(title):
    return any(t in (title or "").lower() for t in TARGET_TITLES)

def score(title, desc):
    skills = ["brand","digital","marketing","cx","nps","fintech","performance",
              "atl","strategy","campaigns","agency","omnichannel","payments","influencer"]
    text = (title + desc).lower()
    s = 55 if is_relevant(title) else 30
    s += min(30, sum(3 for sk in skills if sk in text))
    return min(95, s)

def get_tags(title):
    tl = (title or "").lower()
    tags = ["Head-level"] if any(t in tl for t in ["head","director","vp","chief","cmo"]) \
           else ["Senior Manager"] if "senior" in tl else ["Manager"]
    if "cx" in tl or "customer experience" in tl: tags.append("CX")
    elif "brand" in tl: tags.append("Brand")
    elif "digital" in tl: tags.append("Digital")
    return tags

def fetch():
    if not RAPIDAPI_KEY:
        return []
    jobs = []
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com"
    }
    for q in QUERIES:
        try:
            r = requests.get(
                "https://jsearch.p.rapidapi.com/search",
                headers=headers,
                params={"query": q, "page": "1", "num_pages": "1", "date_posted": "month"},
                timeout=8
            )
            if r.status_code == 200:
                for j in r.json().get("data", []):
                    title = j.get("job_title", "") or ""
                    if not is_relevant(title):
                        continue
                    company = j.get("employer_name", "") or ""
                    city = j.get("job_city", "") or ""
                    country = j.get("job_country", "") or ""
                    loc = f"{city}, {country}".strip(", ")
                    desc = (j.get("job_description", "") or "")[:200]
                    jobs.append({
                        "title": title,
                        "company": company,
                        "location": loc,
                        "description": desc,
                        "applyUrl": j.get("job_apply_link", "") or "",
                        "source": "LinkedIn",
                        "score": score(title, desc),
                        "posted": (j.get("job_posted_at_datetime_utc", "") or "")[:10],
                        "tags": get_tags(title),
                        "type": "Live listing"
                    })
            time.sleep(0.5)
        except Exception as e:
            print(f"Query failed: {q} - {e}")
    seen, out = set(), []
    for j in jobs:
        k = (j["title"].lower()[:20], j["company"].lower()[:15])
        if k not in seen:
            seen.add(k)
            out.append(j)
    return sorted(out, key=lambda x: x["score"], reverse=True)[:80]

def get_cache():
    try:
        with open(CACHE_FILE) as f:
            d = json.load(f)
        if datetime.now() - datetime.fromisoformat(d["at"]) < timedelta(hours=6):
            return d["jobs"]
    except:
        pass
    return None

def set_cache(jobs):
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump({"at": datetime.now().isoformat(), "jobs": jobs}, f)
    except:
        pass

@app.route("/")
def root():
    return jsonify({"status": "Hassaan Job API", "version": "3.0"})

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "rapidapi_configured": bool(RAPIDAPI_KEY),
        "time": datetime.now().isoformat()
    })

@app.route("/jobs")
def jobs():
    refresh = request.args.get("refresh") == "true"
    if not refresh:
        cached = get_cache()
        if cached:
            return jsonify({"jobs": cached, "source": "cache", "count": len(cached)})
    try:
        j = fetch()
        set_cache(j)
        return jsonify({"jobs": j, "source": "live", "count": len(j)})
    except Exception as e:
        print(f"Fetch error: {e}")
        return jsonify({"jobs": [], "source": "error", "error": str(e), "count": 0})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

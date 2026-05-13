from flask import Flask, jsonify, request
from flask_cors import CORS
import requests, os, json, time
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app, origins="*", methods=["GET", "POST", "OPTIONS"], allow_headers=["Content-Type", "Authorization", "X-Push-Secret"])

RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")
PUSH_SECRET = os.environ.get("PUSH_SECRET", "hz-secret-2025")
CACHE_FILE = "/tmp/cache.json"
LINKEDIN_FILE = "/tmp/linkedin_jobs.json"

TARGET_TITLES = [
    "head of marketing", "marketing director", "director of marketing", "brand director",
    "head of cx", "cx director", "head of customer experience", "senior marketing manager",
    "senior brand manager", "vp marketing", "chief marketing", "cmo", "digital marketing director",
    "head of digital", "brand manager", "pr manager", "communications manager",
    "corporate communications", "growth marketing", "performance marketing manager",
    "digital marketing manager", "social media manager"
]

KEYWORDS = ["brand", "marketing", "digital", "cx", "customer experience", "communications",
            "pr", "performance", "growth", "content", "social media", "campaign", "crm"]

def is_relevant(title, desc=""):
    tl = (title or "").lower()
    return any(t in tl for t in TARGET_TITLES) or sum(1 for k in KEYWORDS if k in tl) >= 2

def score_job(title, desc):
    skills = ["brand", "digital", "marketing", "cx", "nps", "fintech", "performance", "atl",
              "strategy", "campaigns", "agency", "omnichannel", "payments", "influencer",
              "crm", "loyalty", "ecommerce", "communications", "pr", "growth"]
    text = (title + " " + (desc or "")).lower()
    s = 40
    if any(t in title.lower() for t in ["head", "director", "vp", "chief", "cmo"]):
        s += 15
    elif any(t in title.lower() for t in ["senior", "manager"]):
        s += 8
    s += min(35, sum(3 for sk in skills if sk in text))
    return min(95, s)

def get_tags(title):
    tl = (title or "").lower()
    if any(t in tl for t in ["head", "director", "vp", "chief", "cmo"]):
        tags = ["Head-level"]
    elif "senior" in tl:
        tags = ["Senior Manager"]
    else:
        tags = ["Manager"]
    if "cx" in tl or "customer experience" in tl:
        tags.append("CX")
    elif "brand" in tl:
        tags.append("Brand")
    elif "digital" in tl:
        tags.append("Digital")
    elif "pr" in tl or "comm" in tl:
        tags.append("Comms")
    elif "growth" in tl or "performance" in tl:
        tags.append("Growth")
    return tags

QUERIES = [
    "Head of Marketing UAE",
    "Marketing Director Dubai",
    "CX Director UAE",
    "Brand Director Dubai",
    "Senior Marketing Manager UAE",
    "Head of Marketing Saudi Arabia",
    "Marketing Director Qatar",
    "Head of Marketing Malaysia",
    "Marketing Director Kuala Lumpur",
    "Brand Manager Malaysia",
    "Digital Marketing Manager Malaysia",
    "CX Manager Malaysia"
]

def fetch_rapidapi():
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
                    city = j.get("job_city", "") or ""
                    country = j.get("job_country", "") or ""
                    desc = (j.get("job_description", "") or "")[:300]
                    jobs.append({
                        "title": title,
                        "company": j.get("employer_name", "") or "",
                        "location": (city + ", " + country).strip(", "),
                        "description": desc,
                        "applyUrl": j.get("job_apply_link", "") or "",
                        "source": "LinkedIn",
                        "score": score_job(title, desc),
                        "posted": (j.get("job_posted_at_datetime_utc", "") or "")[:10],
                        "tags": get_tags(title),
                        "type": "RapidAPI"
                    })
            time.sleep(0.5)
        except Exception as e:
            print("RapidAPI failed: " + q + " - " + str(e))
    seen = set()
    out = []
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

def get_linkedin_cache():
    try:
        with open(LINKEDIN_FILE) as f:
            return json.load(f)
    except:
        return {"jobs": [], "pushed_at": None, "count": 0}

def set_linkedin_cache(jobs):
    try:
        with open(LINKEDIN_FILE, "w") as f:
            json.dump({"jobs": jobs, "pushed_at": datetime.now().isoformat(), "count": len(jobs)}, f)
    except:
        pass

@app.after_request
def after_request(response):
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization,X-Push-Secret")
    response.headers.add("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    return response

@app.route("/")
def root():
    return jsonify({"status": "ok", "version": "4.0"})

@app.route("/health")
def health():
    li = get_linkedin_cache()
    return jsonify({
        "status": "ok",
        "rapidapi_configured": bool(RAPIDAPI_KEY),
        "linkedin_jobs": li.get("count", 0),
        "linkedin_last_pushed": li.get("pushed_at"),
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
        j = fetch_rapidapi()
        set_cache(j)
        return jsonify({"jobs": j, "source": "live", "count": len(j)})
    except Exception as e:
        return jsonify({"jobs": [], "source": "error", "error": str(e), "count": 0})

@app.route("/linkedin-jobs")
def linkedin_jobs():
    data = get_linkedin_cache()
    return jsonify(data)

@app.route("/push-jobs", methods=["POST", "OPTIONS"])
def push_jobs():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})
    secret = request.headers.get("X-Push-Secret", "") or (request.json or {}).get("secret", "")
    if secret != PUSH_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    try:
        raw_jobs = (request.json or {}).get("jobs", [])
        if not raw_jobs:
            return jsonify({"error": "No jobs provided"}), 400
        filtered = []
        seen = set()
        for j in raw_jobs:
            title = j.get("job_title") or j.get("title") or ""
            desc = j.get("job_description") or j.get("description") or ""
            if not is_relevant(title, desc):
                continue
            company = j.get("company_name") or j.get("company") or ""
            k = (title.lower()[:20], company.lower()[:15])
            if k in seen:
                continue
            seen.add(k)
            filtered.append({
                "title": title,
                "company": company,
                "location": j.get("location") or "",
                "description": desc[:400],
                "applyUrl": j.get("job_url") or j.get("apply_url") or j.get("applyUrl") or "",
                "source": "LinkedIn",
                "score": score_job(title, desc),
                "posted": j.get("time_posted") or j.get("posted") or "",
                "tags": get_tags(title),
                "type": "LinkedIn via Apify"
            })
        filtered = sorted(filtered, key=lambda x: x["score"], reverse=True)
        set_linkedin_cache(filtered)
        return jsonify({
            "ok": True,
            "received": len(raw_jobs),
            "filtered": len(filtered),
            "pushed_at": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deux passes:
1) Calcule un score BASE pour TOUTES les entreprises (sans enrichissement web).
   Ce score utilise toutes les règles mais avec signaux "locaux" (proxies).
2) Sélectionne le TOP 240 par score BASE (tie-break: funding le plus récent).
   Puis ré-évalue ces 240 avec ENRICHISSEMENT web (SerpAPI + pages jobs/stack),
   et recalcule le score FINAL. Les autres conservent leur score BASE.

Sorties:
- out/scored_full.csv (scores finaux)
- out/top200.csv     (top 200 finaux)

Usage:
  export SERPAPI_KEY="ta_cle_250req"
  python score_prospects_top240.py input.csv --outdir ./out --delay 1
"""

import os
import re
import time
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin, quote_plus

import requests
from bs4 import BeautifulSoup
import pandas as pd

# ---- Config ----
UA = "Mozilla/5.0 (compatible; OutboundScorer/0.1)"
HDR = {"User-Agent": UA}
NOW = datetime(2025, 10, 15, tzinfo=timezone.utc)

RX_SF = re.compile(r"\b(salesforce|sfdc|sales cloud|service cloud|marketing cloud|salesforce\.com)\b", re.IGNORECASE)
RX_LK = re.compile(r"\b(looker|lookml|looker studio|looker blocks?)\b", re.IGNORECASE)
RX_FPNA = re.compile(r"\b(fp&a|fpna|financial planning)\b", re.IGNORECASE)

CAREERS_HINTS = ("career", "careers", "job", "jobs", "join", "vacancy", "opportunities")
CAREERS_FALLBACK = ("/careers", "/jobs", "/career", "/join-us")
SERIES_GROWTH = {"series b", "series c", "series d", "growth equity", "private equity"}

LOGGER = logging.getLogger("top240")

# ---- Parsers ----
def months_since(date_str: str):
    if not isinstance(date_str, str) or not date_str.strip():
        return None
    s = date_str.strip()
    fmts = ["%Y-%m-%d","%Y/%m/%d","%d/%m/%Y","%m/%d/%Y","%b %d, %Y","%B %d, %Y","%Y-%m"]
    for f in fmts:
        try:
            dt = datetime.strptime(s, f).replace(tzinfo=timezone.utc)
            return (NOW.year - dt.year) * 12 + (NOW.month - dt.month)
        except Exception:
            pass
    return None

def parse_money_range_usd(s: str):
    if not isinstance(s, str) or not s.strip():
        return (None, None)
    x = s.replace(",", "").upper().strip().replace(" TO ", "-")
    if "UNKNOWN" in x or x in {"-", "N/A", "NA"}:
        return (None, None)
    def num(tok):
        m = re.search(r"(\d+(\.\d+)?)\s*([KMB])?", tok)
        if not m:
            try: return float(tok)
            except: return None
        v = float(m.group(1)); suf = m.group(3)
        if suf == "K": v*=1e3
        elif suf == "M": v*=1e6
        elif suf == "B": v*=1e9
        return v
    m = re.match(r"^\$?([\d\.]+)\s*([KMB])\s*[-–]\s*\$?([\d\.]+)\s*([KMB])$", x)
    if m:
        a = num(m.group(1)+m.group(2)); b = num(m.group(3)+m.group(4))
        return (a,b)
    m = re.match(r"^\$?([\d\.]+)\s*([KMB])\+?$", x)
    if m:
        v = num(m.group(1)+m.group(2)); return (v, None)
    anynum = re.findall(r"([\d\.]+)\s*([KMB])", x)
    if anynum:
        vals = [num(n+u) for n,u in anynum if num(n+u) is not None]
        if vals: return (min(vals), max(vals))
    return (None, None)

def parse_emp_range(s: str):
    if s is None: return (None, None)
    if not isinstance(s, str): s = str(s)
    x = s.replace(",", "").lower().strip().replace(" to ", "-")
    if x.endswith("+"):
        try: base = int(re.sub(r"\D","", x)); return (base, None)
        except: return (None, None)
    m = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", x)
    if m: return (int(m.group(1)), int(m.group(2)))
    try:
        v = int(re.sub(r"\D","", x)); return (v, v)
    except: return (None, None)

def yn(v):
    if isinstance(v,str):
        t=v.strip().lower()
        if t in {"yes","y","true","t","1","actively hiring","hiring"}: return True
        if t in {"no","n","false","f","0"}: return False
    if isinstance(v,(int,float)): return bool(v)
    return False

# ---- HTTP helpers ----
def fetch(url, timeout=12):
    try:
        r = requests.get(url, headers=HDR, timeout=timeout, allow_redirects=True)
        if r.status_code==200: return r.text
    except Exception:
        return None
    return None

def allowed(url):
    try:
        p=urlparse(url)
        rb=f"{p.scheme}://{p.netloc}/robots.txt"
        r=requests.get(rb, headers=HDR, timeout=8)
        if r.status_code!=200: return True
        if re.search(r"(?im)^disallow\s*:\s*/\s*$", r.text): return False
        return True
    except Exception:
        return True

# ---- Enrichment detectors ----
def find_career_links(home_html, base):
    links=[]
    soup=BeautifulSoup(home_html, "html.parser")
    for a in soup.find_all("a", href=True):
        href=a.get("href"); ll=str(href).lower()
        if any(k in ll for k in CAREERS_HINTS):
            links.append(urljoin(base, href))
    for fb in CAREERS_FALLBACK:
        links.append(urljoin(base, fb))
    seen=set(); out=[]
    for u in links:
        if u not in seen: seen.add(u); out.append(u)
    return out

def scan_jobs_for_fpna(domain, delay=1.0):
    try:
        parsed = urlparse(domain if str(domain).startswith("http") else "https://" + str(domain))
        base = f"{parsed.scheme}://{parsed.netloc}"
        if not allowed(base): return (False,"")
        home = fetch(base)
        if not home: return (False,"")
        if RX_FPNA.search(home):
            return (True, f"{base} (homepage)")
        links = find_career_links(home, base)
        for u in links[:6]:
            time.sleep(delay)
            html = fetch(u)
            if not html: continue
            if RX_FPNA.search(html):
                return (True, u)
        return (False,"")
    except Exception:
        return (False,"")

def detect_stack_via_jobs(domain, delay=1.0):
    try:
        parsed = urlparse(domain if str(domain).startswith("http") else "https://" + str(domain))
        base = f"{parsed.scheme}://{parsed.netloc}"
        if not allowed(base): return (False,"",False,"")
        home = fetch(base)
        if not home: return (False,"",False,"")
        links = find_career_links(home, base)
        for u in links[:6]:
            time.sleep(delay)
            html = fetch(u)
            if not html: continue
            sf = bool(RX_SF.search(html))
            lk = bool(RX_LK.search(html))
            if sf or lk:
                return (sf, u if sf else "", lk, u if lk else "")
        return (False,"",False,"")
    except Exception:
        return (False,"",False,"")

def detect_stackshare(domain):
    try:
        parsed = urlparse(domain if domain.startswith("http") else "https://" + domain)
        slug = (parsed.hostname or domain).split(".")[0]
        url = f"https://stackshare.io/{slug}"
        if not allowed(url): return (False,"",False,"")
        html = fetch(url)
        if not html: return (False,"",False,"")
        sf = bool(RX_SF.search(html)); lk = bool(RX_LK.search(html))
        return (sf, "stackshare", lk, "stackshare")
    except Exception:
        return (False,"",False,"")

def detect_builtwith(domain):
    try:
        parsed = urlparse(domain if domain.startswith("http") else "https://" + domain)
        host = parsed.hostname or domain
        url = f"https://builtwith.com/{host}"
        if not allowed(url): return (False,"",False,"")
        html = fetch(url)
        if not html: return (False,"",False,"")
        sf = bool(RX_SF.search(html)); lk = bool(RX_LK.search(html))
        return (sf, "builtwith", lk, "builtwith")
    except Exception:
        return (False,"",False,"")

def serpapi_fpna_count(company_name, serpapi_key):
    if not serpapi_key or not company_name:
        return (None, "")
    try:
        q = f'site:linkedin.com/in ("FP&A" OR FPnA) "{company_name}"'
        url = f"https://serpapi.com/search.json?engine=google&q={quote_plus(q)}&api_key={serpapi_key}"
        r = requests.get(url, headers=HDR, timeout=15)
        if r.status_code != 200:
            return (None, "")
        data = r.json()
        total = data.get("search_information", {}).get("total_results", None)
        ev = f"SerpAPI: {q}"
        if isinstance(total, (int, float)): return (int(total), ev)
        org = data.get("organic_results", [])
        return ((len(org) if org else None), ev)
    except Exception:
        return (None, "")

# ---- Scoring (critères identiques, source différente BASE vs ENRICH) ----
def compute_flags_local(row):
    name = (row.get("Organization Name") or "").strip()
    website = row.get("Website") or row.get("Organization Name URL") or ""
    ipo_status = str(row.get("IPO Status") or "").strip().lower()
    last_funding_type = str(row.get("Last Funding Type") or "").strip().lower()
    last_funding_date = row.get("Last Funding Date")
    hiring = yn(row.get("Actively Hiring"))
    depts = row.get("Contact Job Departments") or ""
    desc = row.get("Description") or ""
    emp_min, emp_max = parse_emp_range(row.get("Number of Employees"))
    rev_min, rev_max = parse_money_range_usd(row.get("Estimated Revenue Range"))

    # Taille
    size_ok = False
    if emp_min is not None and emp_max is not None:
        size_ok = (emp_min <= 2000 and emp_max >= 200)
    elif emp_min is not None:
        size_ok = (200 <= emp_min <= 2000)

    # Croissance
    m = months_since(last_funding_date)
    recent_raise = (m is not None and m <= 12)
    series_ok = (ipo_status not in {"public"} and last_funding_type in SERIES_GROWTH)
    growth_ok = bool(hiring or recent_raise or series_ok)

    # FP&A headcount (proxy local)
    mentions = len(RX_FPNA.findall(f"{depts}\n{desc}"))
    fpna_count_est = min(20, mentions * 2)
    fpna_ok = fpna_count_est > 5

    # Jobs FP&A (proxy local)
    jobs_ok = bool(hiring and RX_FPNA.search(f"{depts}\n{desc}"))

    # Stack (proxy local)
    stack_ok = bool(RX_SF.search(f"{depts}\n{desc}") or RX_LK.search(f"{depts}\n{desc}"))

    # Mid-market revenu
    if rev_min is not None or rev_max is not None:
        lo, hi = 50e6, 1e9
        rlo = rev_min if rev_min is not None else 0
        rhi = rev_max if rev_max is not None else 9e18
        mid_ok = (rlo <= hi and rhi >= lo)
    else:
        mid_ok = size_ok

    score = sum([size_ok, growth_ok, fpna_ok, jobs_ok, stack_ok, mid_ok])
    return {
        "size_ok": bool(size_ok),
        "growth_ok": bool(growth_ok),
        "fpna_ok": bool(fpna_ok),
        "jobs_ok": bool(jobs_ok),
        "stack_ok": bool(stack_ok),
        "mid_ok": bool(mid_ok),
        "score": int(score),
        "months_since_raise": m if m is not None else 9999
    }

def compute_flags_enriched(row, delay=1.0, serpapi_key=None):
    name = (row.get("Organization Name") or "").strip()
    website = row.get("Website") or row.get("Organization Name URL") or ""
    ipo_status = str(row.get("IPO Status") or "").strip().lower()
    last_funding_type = str(row.get("Last Funding Type") or "").strip().lower()
    last_funding_date = row.get("Last Funding Date")
    hiring = yn(row.get("Actively Hiring"))
    depts = row.get("Contact Job Departments") or ""
    desc = row.get("Description") or ""
    emp_min, emp_max = parse_emp_range(row.get("Number of Employees"))
    rev_min, rev_max = parse_money_range_usd(row.get("Estimated Revenue Range"))

    # Taille
    size_ok = False
    if emp_min is not None and emp_max is not None:
        size_ok = (emp_min <= 2000 and emp_max >= 200)
    elif emp_min is not None:
        size_ok = (200 <= emp_min <= 2000)

    # Croissance
    m = months_since(last_funding_date)
    recent_raise = (m is not None and m <= 12)
    series_ok = (ipo_status not in {"public"} and last_funding_type in SERIES_GROWTH)
    growth_ok = bool(hiring or recent_raise or series_ok)

    # FP&A headcount (SerpAPI sinon proxy)
    fpna_count, fpna_ev = serpapi_fpna_count(name, serpapi_key) if serpapi_key else (None, "")
    if fpna_count is None:
        mentions = len(RX_FPNA.findall(f"{depts}\n{desc}"))
        fpna_count = min(20, mentions * 2)
    fpna_ok = (fpna_count is not None and fpna_count > 5)

    # Jobs FP&A (scrape pages)
    jobs_ok, _ = (False, "")
    if website:
        jobs_ok, _ = scan_jobs_for_fpna(website, delay=delay)

    # Stack (jobs + stackshare + builtwith + local texte)
    stack_ok = False
    if website:
        a,b,c,d = detect_stack_via_jobs(website, delay=delay)
        stack_ok = bool(a or c)
        if not stack_ok:
            a,b,c,d = detect_stackshare(website); stack_ok = bool(a or c)
        if not stack_ok:
            a,b,c,d = detect_builtwith(website); stack_ok = bool(a or c)
    if not stack_ok:
        stack_ok = bool(RX_SF.search(f"{depts}\n{desc}") or RX_LK.search(f"{depts}\n{desc}"))

    # Mid-market
    if rev_min is not None or rev_max is not None:
        lo, hi = 50e6, 1e9
        rlo = rev_min if rev_min is not None else 0
        rhi = rev_max if rev_max is not None else 9e18
        mid_ok = (rlo <= hi and rhi >= lo)
    else:
        mid_ok = size_ok

    score = sum([size_ok, growth_ok, fpna_ok, jobs_ok, stack_ok, mid_ok])
    return {
        "size_ok": bool(size_ok),
        "growth_ok": bool(growth_ok),
        "fpna_ok": bool(fpna_ok),
        "jobs_ok": bool(jobs_ok),
        "stack_ok": bool(stack_ok),
        "mid_ok": bool(mid_ok),
        "score": int(score),
        "months_since_raise": m if m is not None else 9999
    }

# ---- Pipeline ----
def main():
    ap = argparse.ArgumentParser(description="Deux passes: enrichissement uniquement sur le top 240 après score base.")
    ap.add_argument("input", help="input CSV path")
    ap.add_argument("--outdir", default="./out", help="output directory")
    ap.add_argument("--topn", type=int, default=240, help="N à enrichir (défaut 240)")
    ap.add_argument("--delay", type=float, default=1.0, help="délai entre requêtes web")
    ap.add_argument("--log-every", type=int, default=1, help="log toutes les N lignes")
    ap.add_argument("--quiet", action="store_true", help="logs réduits")
    ap.add_argument("--serpapi-key", default=os.getenv("SERPAPI_KEY",""), help="clé SerpAPI pour FP&A headcount")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.ERROR if args.quiet else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S"
    )

    outdir = Path(args.outdir); outdir.mkdir(parents=True, exist_ok=True)
    LOGGER.info(f"Chargement {args.input}")
    df = pd.read_csv(args.input, dtype=str).fillna("")
    total = len(df)
    LOGGER.info(f"Lignes: {total} | TopN enrichis: {args.topn} | SerpAPI: {'YES' if args.serpapi_key else 'NO'}")

    # Pass 1: score BASE local
    base_rows=[]
    for i, row in df.iterrows():
        if args.log_every and (i % args.log_every == 0):
            LOGGER.info(f"[BASE {i+1}/{total}] {row.get('Organization Name','')}")
        flags = compute_flags_local(row)
        r = dict(row)
        r["Score_BASE"] = flags["score"]
        r["BASE_MonthsSinceRaise"] = flags["months_since_raise"]
        base_rows.append(r)
    base_df = pd.DataFrame(base_rows)

    # Choix du TOP N par Score_BASE, tie-break par recent funding (moins de mois = mieux)
    base_df["_tie"] = base_df["BASE_MonthsSinceRaise"].astype(int)
    base_sorted = base_df.sort_values(by=["Score_BASE","_tie"], ascending=[False, True])
    enrich_index = set(base_sorted.head(args.topn).index.tolist())
    LOGGER.info(f"Sélectionné {len(enrich_index)} lignes pour enrichissement.")

    # Pass 2: score FINAL, enrich uniquement topN
    final_rows=[]
    for i, row in df.iterrows():
        if args.log_every and (i % args.log_every == 0):
            LOGGER.info(f"[FINAL {i+1}/{total}] {row.get('Organization Name','')} | {'ENRICH' if i in enrich_index else 'LOCAL'}")
        if i in enrich_index:
            flags = compute_flags_enriched(row, delay=args.delay, serpapi_key=(args.serpapi_key or None))
        else:
            flags = compute_flags_local(row)
        r = dict(row)
        r["Score"] = flags["score"]
        r["Size_OK"] = flags["size_ok"]
        r["Growth_OK"] = flags["growth_ok"]
        r["FPnA_OK"] = flags["fpna_ok"]
        r["Jobs_OK"] = flags["jobs_ok"]
        r["Stack_OK"] = flags["stack_ok"]
        r["Mid_OK"] = flags["mid_ok"]
        r["MonthsSinceRaise"] = flags["months_since_raise"]
        r["Enriched"] = (i in enrich_index)
        final_rows.append(r)

        if i in enrich_index:
            time.sleep(args.delay)

    out = pd.DataFrame(final_rows)

    # Tri final: Score desc, funding le plus récent
    out = out.sort_values(by=["Score","MonthsSinceRaise"], ascending=[False, True])

    full_path = outdir / "scored_full.csv"
    top200_path = outdir / "top200.csv"
    out.to_csv(full_path, index=False)
    out.head(200).to_csv(top200_path, index=False)

    dist = out["Score"].value_counts().sort_index(ascending=False)
    LOGGER.info(f"Distribution scores:\n{dist.to_string()}")
    LOGGER.info(f"Wrote: {full_path} et {top200_path}")

if __name__ == "__main__":
    main()

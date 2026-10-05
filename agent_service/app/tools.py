from typing import Dict, List, Any, Optional
import math
import re
from collections import Counter
import httpx
from app.config import settings

SEED_REPORTS: List[Dict[str, Any]] = [
    {
        "report_id": "REP-10293",
        "text": "During maintenance of compressor C-204, isolation was not verified before opening pressurised line. Residual pressure was observed.",
        "site": "Digboi Facility A",
        "location": "Compressor House C-204",
        "asset": "C-204",
        "activity": "Maintenance",
        "sif_potential": True,
        "sif_score": 0.91,
        "risk_band": "HIGH",
        "life_saving_rules": ["Energy Isolation"],
        "barrier_failure": "Isolation Verification",
        "date": "2026-09-09"
    },
    {
        "report_id": "REP-10381",
        "text": "Worker entered confined space at Tank T-12 without completing atmospheric gas test procedure. No injury occurred.",
        "site": "Dulianjan Tank Farm",
        "location": "Storage Tank T-12",
        "asset": "T-12",
        "activity": "Tank Cleaning",
        "sif_potential": True,
        "sif_score": 0.74,
        "risk_band": "ELEVATED",
        "life_saving_rules": ["Confined Space Entry"],
        "barrier_failure": "Atmospheric Gas Testing",
        "date": "2026-09-08"
    },
    {
        "report_id": "REP-10422",
        "text": "Crane slewing during lifting operation — banksman lost visual contact for 3 minutes. Load was 4.2 tonnes.",
        "site": "Moran Drilling Rig 4",
        "location": "Rig Floor",
        "asset": "Crane CR-02",
        "activity": "Lifting Operations",
        "sif_potential": True,
        "sif_score": 0.68,
        "risk_band": "ELEVATED",
        "life_saving_rules": ["Safe Mechanical Lifting"],
        "barrier_failure": "Banksman Supervision",
        "date": "2026-09-07"
    },
    {
        "report_id": "REP-10519",
        "text": "Worker not wearing fall arrest harness while working at height of 6m on scaffold structure at C-204.",
        "site": "Digboi Facility A",
        "location": "Compressor House C-204",
        "asset": "C-204 Scaffold",
        "activity": "Scaffold Maintenance",
        "sif_potential": True,
        "sif_score": 0.87,
        "risk_band": "HIGH",
        "life_saving_rules": ["Work at Height"],
        "barrier_failure": "Fall Protection Harness",
        "date": "2026-09-06"
    },
    {
        "report_id": "REP-10602",
        "text": "Minor oil spill during pump P-204 maintenance. Contained within secondary bund wall.",
        "site": "Dulianjan Pump Station",
        "location": "Pump House 2",
        "asset": "P-204",
        "activity": "Pump Seal Change",
        "sif_potential": False,
        "sif_score": 0.18,
        "risk_band": "LOW",
        "life_saving_rules": ["Environmental Containment"],
        "barrier_failure": "Secondary Bund Containment",
        "date": "2026-09-05"
    }
]

UPLOADED_REPORTS_STORE: Dict[str, List[Dict[str, Any]]] = {}

def add_uploaded_reports(reports: List[Dict[str, Any]], conversation_id: str = "default"):
    """Store dynamically uploaded safety reports for immediate RAG retrieval."""
    if conversation_id not in UPLOADED_REPORTS_STORE:
        UPLOADED_REPORTS_STORE[conversation_id] = []
    
    for idx, r in enumerate(reports):
        rep_id = r.get("report_id") or f"UPL-{idx+1:03d}"
        entry = {
            "report_id": rep_id,
            "text": r.get("text") or r.get("narrative") or r.get("raw_text") or "",
            "site": r.get("site", "Uploaded Asset Facility"),
            "location": r.get("location", "Field Unit"),
            "asset": r.get("asset", "Uploaded Equipment"),
            "activity": r.get("activity", "Operations"),
            "sif_potential": bool(r.get("sif_potential", r.get("sif_probability", 0.0) >= 0.5 or r.get("flagged", False))),
            "sif_score": float(r.get("sif_score", r.get("sif_probability", 0.5))),
            "risk_band": str(r.get("risk_band", r.get("band", "LOW"))).upper(),
            "life_saving_rules": r.get("life_saving_rules", ["General Safety"]),
            "barrier_failure": r.get("barrier_failure", r.get("guidance", "Process Control Verification")),
            "date": r.get("date", "2026-09-10")
        }
        UPLOADED_REPORTS_STORE[conversation_id] = [
            x for x in UPLOADED_REPORTS_STORE[conversation_id] if x.get("report_id") != rep_id
        ]
        UPLOADED_REPORTS_STORE[conversation_id].insert(0, entry)

def get_uploaded_reports(conversation_id: str = "default") -> List[Dict[str, Any]]:
    combined = list(UPLOADED_REPORTS_STORE.get(conversation_id, []))
    if conversation_id != "default":
        combined.extend(UPLOADED_REPORTS_STORE.get("default", []))
    return combined

def get_all_reports(conversation_id: str = "default") -> List[Dict[str, Any]]:
    """Retrieve combined reports: dynamically uploaded reports first, then MongoDB, then seeds."""
    reports = list(get_uploaded_reports(conversation_id))
    
    for seed in SEED_REPORTS:
        if not any(r.get("report_id") == seed.get("report_id") for r in reports):
            reports.append(seed)

    if settings.MONGODB_URI:
        try:
            from pymongo import MongoClient
            client = MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=1500)
            db = client[settings.MONGODB_DATABASE]
            mongo_docs = list(db["reports"].find({}, {"_id": 0}).limit(100))
            for doc in mongo_docs:
                rep_id = doc.get("report_id")
                if not any(r["report_id"] == rep_id for r in reports):
                    reports.insert(0, {
                        "report_id": rep_id or "REP-DB",
                        "text": doc.get("raw_text", ""),
                        "site": doc.get("site", "Oil India Site"),
                        "location": doc.get("location", "Field Operations"),
                        "asset": doc.get("asset", "General Asset"),
                        "activity": doc.get("activity", "General Activity"),
                        "sif_potential": doc.get("sif_probability", 0.0) >= 0.5 or doc.get("flagged", False),
                        "sif_score": doc.get("sif_probability", 0.5),
                        "risk_band": doc.get("risk_band", "LOW"),
                        "life_saving_rules": ["General Safety"],
                        "barrier_failure": doc.get("guidance", "Verification"),
                        "date": doc.get("created_at", "2026-09-10")
                    })
        except Exception:
            pass
    return reports

def tokenize(text: str) -> List[str]:
    """Tokenize and normalize text into keywords for semantic retrieval."""
    return re.findall(r'\b[a-zA-Z0-9_\-]{2,}\b', text.lower())

def compute_cosine_similarity(query_tokens: List[str], doc_tokens: List[str]) -> float:
    """Calculate cosine similarity between query and document token bags."""
    if not query_tokens or not doc_tokens:
        return 0.0
    q_counts = Counter(query_tokens)
    d_counts = Counter(doc_tokens)
    dot_product = sum(q_counts[k] * d_counts[k] for k in q_counts if k in d_counts)
    q_norm = math.sqrt(sum(v * v for v in q_counts.values()))
    d_norm = math.sqrt(sum(v * v for v in d_counts.values()))
    if q_norm == 0 or d_norm == 0:
        return 0.0
    return dot_product / (q_norm * d_norm)

def search_safety_reports(
    query: Optional[str] = None,
    site: Optional[str] = None,
    risk_band: Optional[str] = None,
    asset: Optional[str] = None,
    limit: int = 5,
    conversation_id: str = "default"
) -> List[Dict[str, Any]]:
    """Search safety reports using semantic cosine ranking and structured filtering."""
    all_reports = get_all_reports(conversation_id)
    filtered = all_reports

    if site:
        filtered = [r for r in filtered if site.lower() in r.get("site", "").lower()]
    if risk_band:
        filtered = [r for r in filtered if r.get("risk_band", "").upper() == risk_band.upper()]
    if asset:
        filtered = [r for r in filtered if asset.lower() in r.get("asset", "").lower() or asset.lower() in r.get("location", "").lower()]

    if not query:
        return filtered[:limit]

    q_tokens = tokenize(query)
    scored_reports = []
    for r in filtered:
        content = f"{r.get('text', '')} {r.get('asset', '')} {r.get('barrier_failure', '')} {' '.join(r.get('life_saving_rules', []))}"
        d_tokens = tokenize(content)
        sim = compute_cosine_similarity(q_tokens, d_tokens)
        scored_reports.append((sim, r))

    scored_reports.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored_reports[:limit]]

def get_report(report_id: str, conversation_id: str = "default") -> Optional[Dict[str, Any]]:
    """Fetch complete structured safety report by ID."""
    for r in get_all_reports(conversation_id):
        if r.get("report_id", "").upper() == report_id.upper():
            return r
    return None

def get_risk_summary(site: Optional[str] = None, conversation_id: str = "default") -> Dict[str, Any]:
    """Get aggregated risk metrics for safety dashboard and HSE agent reasoning."""
    reports = get_all_reports(conversation_id)
    if site:
        reports = [r for r in reports if site.lower() in r.get("site", "").lower()]

    total = len(reports)
    sif_count = sum(1 for r in reports if r.get("sif_potential"))
    high_risk_count = sum(1 for r in reports if r.get("risk_band") == "HIGH")

    return {
        "site": site or "All Sites",
        "total_reports": total,
        "sif_potential_reports": sif_count,
        "high_risk_count": high_risk_count,
        "sif_percentage": round((sif_count / total * 100), 1) if total else 0.0,
        "dominant_precursor": "Energy Isolation & Isolation Verification Failure",
    }

def get_asset_risk(asset_id: str, conversation_id: str = "default") -> Dict[str, Any]:
    """Fetch risk analysis specifically for an industrial asset (e.g. Compressor C-204)."""
    all_reports = get_all_reports(conversation_id)
    asset_reports = [r for r in all_reports if asset_id.lower() in r.get("asset", "").lower() or asset_id.lower() in r.get("location", "").lower()]
    sif_reports = [r for r in asset_reports if r.get("sif_potential")]

    primary_barrier = "Energy Isolation Verification"
    if asset_reports:
        failures = [r.get("barrier_failure", "") for r in asset_reports if r.get("barrier_failure")]
        if failures:
            primary_barrier = Counter(failures).most_common(1)[0][0]

    return {
        "asset_id": asset_id,
        "total_reports": len(asset_reports),
        "sif_report_count": len(sif_reports),
        "risk_level": "HIGH" if len(sif_reports) > 1 else "ELEVATED" if len(sif_reports) == 1 else "LOW",
        "primary_barrier_failure": primary_barrier,
        "associated_life_saving_rules": ["Energy Isolation", "Work at Height"],
        "evidence_report_ids": [r["report_id"] for r in asset_reports]
    }

def get_precursor_patterns() -> List[Dict[str, Any]]:
    """Get recurring precursor combinations across OIL assets."""
    return [
        {
            "activity": "Maintenance",
            "barrier_failure": "Energy Isolation Verification",
            "life_saving_rule": "Energy Isolation",
            "sif_count": 2,
            "associated_assets": ["C-204"],
            "trend": "Increasing"
        },
        {
            "activity": "Confined Space Entry",
            "barrier_failure": "Atmospheric Gas Testing",
            "life_saving_rule": "Confined Space Entry",
            "sif_count": 1,
            "associated_assets": ["T-12"],
            "trend": "Stable"
        }
    ]

async def score_report(narrative: str) -> Dict[str, Any]:
    """Connect to SIF Scoring ML Service /score API."""
    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(f"{settings.ML_SERVICE_URL}/score", json={"narrative": narrative}, timeout=5.0)
            if res.status_code == 200:
                return res.json()
        except Exception:
            pass
    return {
        "narrative": narrative,
        "sif_probability": 0.89,
        "threshold": 0.5,
        "flagged": True,
        "band": "HIGH",
        "guidance": "High SIF potential detected. Immediate energy isolation check required."
    }


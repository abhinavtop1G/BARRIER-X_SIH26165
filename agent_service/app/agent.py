from typing import Dict, List, Any, Optional
import json
import httpx
from app import tools
from app.config import settings

SYSTEM_PROMPT = """You are the BARRIER X AI HSE Safety Intelligence Agent for Oil & Gas industrial operations (Oil India Limited and global energy facilities).
Your purpose is to provide authoritative safety intelligence, incident analysis, risk triage, and regulatory guidance for HSSE officers and operations managers.

Capabilities & Response Rules:
1. Uploaded Dataset & Incident Analysis:
   - When safety observations or incident datasets are uploaded or retrieved, analyze them meticulously.
   - Explicitly cite Report IDs (e.g., REP-10293, UPL-001) and include the SIF probability and risk band.
   - Distinguish between direct evidence from reports and your recommended safety interventions.

2. Out-of-Context & General HSE Safety Knowledge:
   - If the user asks general, procedural, or regulatory questions (e.g., IOGP Life-Saving Rules, DGMS / OISD standards, OSHA compliance, LOTO procedures, H2S toxic gas protocols, confined space entry, hot work permits, barrier management, bow-tie methodology), answer authoritatively using your comprehensive industrial HSE expertise.
   - Do NOT refuse to answer general safety questions. Explain best practices, mandatory barrier checks, and the Hierarchy of Controls (Elimination, Substitution, Engineering Controls, Administrative Controls, PPE).

3. Safety-First, Professional Tone:
   - Keep answers clear, structured, and actionable.
   - Use bullet points and bold headers for readability.
"""

async def call_external_llm(system_prompt: str, user_prompt: str) -> Optional[str]:
    """Call external LLM API (Google Gemini / Groq / OpenAI) if API keys are configured server-side."""

    if settings.GEMINI_API_KEY:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={settings.GEMINI_API_KEY}"
            full_prompt = f"{system_prompt}\n\n{user_prompt}"
            async with httpx.AsyncClient() as client:
                res = await client.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json={
                        "contents": [
                            {
                                "parts": [{"text": full_prompt}]
                            }
                        ],
                        "generationConfig": {"thinkingConfig": {"thinkingBudget": 0}},
                    },
                    timeout=30.0
                )
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            return parts[0].get("text", "")
                print(f"[agent] Gemini returned {res.status_code}: {res.text[:200]}")
        except Exception as exc:
            print(f"[agent] Gemini call failed: {type(exc).__name__}: {exc}")

    if settings.GROQ_API_KEY:
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json"},
                    json={
                        "model": "llama-3.3-70b-versatile",
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        "temperature": 0.2
                    },
                    timeout=10.0
                )
                if res.status_code == 200:
                    return res.json()["choices"][0]["message"]["content"]
        except Exception:
            pass

    if settings.OPENAI_API_KEY:
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}", "Content-Type": "application/json"},
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        "temperature": 0.2
                    },
                    timeout=10.0
                )
                if res.status_code == 200:
                    return res.json()["choices"][0]["message"]["content"]
        except Exception:
            pass

    return None

async def function_process_query(
    user_message: str,
    conversation_id: str = "default",
    uploaded_reports: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    msg_lower = user_message.lower()
    tools_used = []
    evidence = []

    uploaded_in_session = tools.get_uploaded_reports(conversation_id)

    if "upload" in msg_lower or "dataset" in msg_lower or "file" in msg_lower:
        tools_used.append("get_uploaded_reports")
        if uploaded_in_session:
            evidence = [
                {"report_id": r["report_id"], "finding": r["text"], "band": r.get("risk_band", "LOW"), "prob": r.get("sif_score", 0.5)}
                for r in uploaded_in_session[:8]
            ]
        else:
            tools_used.append("get_all_reports")
            reports = tools.get_all_reports(conversation_id)
            evidence = [{"report_id": r["report_id"], "finding": r["text"], "band": r.get("risk_band", "LOW")} for r in reports[:5]]

    elif "c-204" in msg_lower or "compressor" in msg_lower or "p-204" in msg_lower:
        target_asset = "C-204" if "c-204" in msg_lower or "compressor" in msg_lower else "P-204"
        tools_used.extend(["get_asset_risk", "search_safety_reports"])
        reports = tools.search_safety_reports(asset=target_asset, conversation_id=conversation_id)
        evidence = [{"report_id": r["report_id"], "finding": r["text"], "band": r["risk_band"]} for r in reports]

    elif "summary" in msg_lower or "metric" in msg_lower or "kpi" in msg_lower:
        tools_used.append("get_risk_summary")
        summary = tools.get_risk_summary(conversation_id=conversation_id)
        evidence = [{"type": "summary", "total": summary["total_reports"], "high_risk": summary["high_risk_count"], "sif_count": summary["sif_potential_reports"]}]

    elif "highest" in msg_lower or "worst" in msg_lower or "high risk" in msg_lower:
        tools_used.append("search_safety_reports")
        high_reports = [r for r in tools.get_all_reports(conversation_id) if r.get("risk_band") == "HIGH" or r.get("sif_score", 0) >= 0.75]
        if not high_reports:
            high_reports = tools.get_all_reports(conversation_id)[:3]
        evidence = [{"report_id": r["report_id"], "finding": r["text"], "band": r.get("risk_band"), "score": r.get("sif_score")} for r in high_reports[:5]]

    else:
        tools_used.append("search_safety_reports")
        reports = tools.search_safety_reports(query=user_message, conversation_id=conversation_id, limit=5)
        evidence = [{"report_id": r["report_id"], "finding": r["text"], "band": r.get("risk_band", "LOW")} for r in reports]

    evidence_str = json.dumps(evidence, indent=2)
    user_prompt = f"User Query: {user_message}\n\nRetrieved Safety Reports & Context:\n{evidence_str}\n\nProvide an insightful, domain-accurate safety assessment. If the question is a general safety question or outside the retrieved reports, answer it authoritatively using industrial HSE standards."

    llm_response = await call_external_llm(SYSTEM_PROMPT, user_prompt)
    if llm_response:
        return {
            "answer": llm_response,
            "evidence": evidence,
            "tools_used": tools_used,
            "conversation_id": conversation_id
        }

    
    if "upload" in msg_lower or "dataset" in msg_lower or "my report" in msg_lower:
        if uploaded_in_session:
            high_count = sum(1 for r in uploaded_in_session if r.get("risk_band") == "HIGH")
            answer_text = (
                f"**Analysis of Uploaded Safety Dataset:**\n\n"
                f"• **Records Ingested**: {len(uploaded_in_session)} incident reports\n"
                f"• **High-Risk SIF Precursors**: {high_count} records\n\n"
                "**Key Observations from Upload:**\n" +
                "\n".join([f"• **{r['report_id']}** [{r['risk_band']}]: {r['text']}" for r in uploaded_in_session[:3]]) +
                "\n\n**Recommended Next Steps:**\n"
                "Review the highest risk items and enforce pre-job barrier verification audits."
            )
        else:
            answer_text = (
                "You can upload any incident dataset (.CSV or text) using the **Upload Dataset** option. "
                "Once uploaded, the DeBERTa ML model will score the SIF probabilities and I will automatically reason over your specific records."
            )

    elif "loto" in msg_lower or "energy isolation" in msg_lower or "lockout" in msg_lower:
        answer_text = (
            "**Lockout/Tagout (LOTO) & Energy Isolation Protocol (OISD / OSHA / IOGP):**\n\n"
            "Energy Isolation is a fundamental Life-Saving Rule designed to prevent zero-energy state violations during maintenance on pressurized, electrical, or hydraulic systems.\n\n"
            "**Core Verification Steps:**\n"
            "1. **Notify & Identify**: Inform affected operators and identify all potential energy sources (hydraulic, mechanical, electrical, thermal).\n"
            "2. **De-energize & Isolate**: Actuate primary isolation valves or circuit breakers.\n"
            "3. **Lock & Tag**: Apply individual padlock and danger warning tags.\n"
            "4. **Residual Energy Dissipation**: Vent, bleed, and drain all trapped lines. Verify pressure gauge reads 0 PSI.\n"
            "5. **Zero Energy Verification Test**: Physically attempt to restart the unit or verify pressure relief prior to breaking line containment.\n\n"
            "**Relevant Incident Reference**: Report **REP-10293** documents an isolation verification failure on Compressor C-204, where residual pressure was trapped in an unvented line."
        )

    elif "confined space" in msg_lower or "gas test" in msg_lower:
        answer_text = (
            "**Confined Space Entry Protocol (DGMS / OSHA 1910.146 / IOGP):**\n\n"
            "Confined spaces (storage tanks, vessels, sumps) pose immediate atmospheric and entrapment hazards.\n\n"
            "**Mandatory Safety Controls:**\n"
            "• **Permit to Work (PTW)**: Authorized by qualified HSE supervisor before opening entry points.\n"
            "• **Multi-Gas Atmospheric Testing**: Continuous monitoring of Oxygen (19.5% – 23.5%), LEL (Lower Explosive Limit < 5%), and toxic gases (H2S < 10 ppm, CO < 25 ppm).\n"
            "• **Dedicated Hole Watch/Standby**: A dedicated sentry stationed outside with emergency retrieval hoist.\n"
            "• **Forced Air Ventilation**: Continuous mechanical air exchange throughout occupancy.\n\n"
            "**Relevant Incident Reference**: Report **REP-10381** captures a high-potential near miss at Tank T-12 where personnel entered without completing atmospheric gas verification."
        )

    elif "iogp" in msg_lower or "life-saving" in msg_lower or "life saving" in msg_lower:
        answer_text = (
            "**IOGP 9 Life-Saving Rules (International Association of Oil & Gas Producers):**\n\n"
            "These standardized rules address activities with the highest frequency of fatal incidents in upstream and downstream operations:\n\n"
            "1. **Bypassing Safety Controls**: Obtain authorization before overriding or disabling safety devices.\n"
            "2. **Confined Space**: Obtain authorization and complete atmospheric testing before entering.\n"
            "3. **Driving**: Obey speed limits, wear seatbelts, and avoid mobile phone distractions.\n"
            "4. **Energy Isolation**: Verify zero-energy state before starting work.\n"
            "5. **Hot Work**: Control flammable atmospheres and ignition sources.\n"
            "6. **Line of Fire**: Position yourself clear of moving machinery, pressurized lines, and dropped objects.\n"
            "7. **Safe Mechanical Lifting**: Plan lifts, check rigging, and stay out of suspended load zones.\n"
            "8. **Work Authorization**: Confirm that a valid Permit to Work is in place.\n"
            "9. **Working at Height**: Use 100% fall protection tie-off when working outside protected scaffolding.\n\n"
            "BARRIER X continuously maps all submitted incident narratives against these 9 rules."
        )

    elif "h2s" in msg_lower or "hydrogen sulfide" in msg_lower or "gas leak" in msg_lower:
        answer_text = (
            "**Hydrogen Sulfide (H2S) Emergency & Operational Protocol:**\n\n"
            "H2S is a colorless, highly toxic gas common in sour crude oil and gas reservoirs. At high concentrations (>100 ppm), olfactory fatigue occurs instantaneously.\n\n"
            "**Operational Defenses:**\n"
            "• **Personal Gas Monitors (PGMs)**: Calibrated with dual alarm thresholds (Low Alarm: 5 ppm, High Alarm: 10 ppm).\n"
            "• **Wind Direction Awareness**: Always observe on-site wind socks before entering process areas.\n"
            "• **Emergency Evacuation**: Move cross-wind, then up-wind to a designated Muster Point.\n"
            "• **Respiratory Protection**: Positive-pressure SCBA (Self-Contained Breathing Apparatus) is mandatory for rescue or line breaking in sour service."
        )

    elif "what is sif" in msg_lower or "sif definition" in msg_lower or "serious injury" in msg_lower:
        answer_text = (
            "**Serious Injury and Fatality (SIF) Potential Methodology:**\n\n"
            "Traditional Heinrich's safety triangle assumes reducing minor incidents proportionally reduces fatalities. Contemporary safety science proves this is false: **only 15–20% of incidents carry SIF potential**.\n\n"
            "**SIF Precursor Criteria (CCPS / Campbell Institute):**\n"
            "An event has SIF potential when it involves:\n"
            "1. **A High-Energy Source** (gravity, electrical, chemical, pressurized fluid, kinetic load).\n"
            "2. **A Failed or Missing Critical Barrier** (isolation valve, relief system, harness, gas detector).\n"
            "3. **A Realistic Chain of Events** where absent fortunate circumstances, fatal injury would have occurred.\n\n"
            "BARRIER X DeBERTa fine-tuned transformers analyze free-text narratives to classify whether these precursor conditions were active."
        )

    elif "c-204" in msg_lower or "compressor" in msg_lower:
        answer_text = (
            "**Asset Integrity & Risk Audit: Compressor C-204**\n\n"
            "• **Current Risk Status**: **HIGH RISK**\n"
            "• **Location**: Digboi Facility A — Compressor House\n\n"
            "**Incident History & Evidence:**\n"
            "• **REP-10293** (SIF: 91%, HIGH): Pressure line opened without verification of zero-energy state.\n"
            "• **REP-10519** (SIF: 87%, HIGH): Maintenance contractor working on C-204 scaffolding at 6m height without harness attachment.\n\n"
            "**Root Precursor Pattern**: Recurring failure of pre-job verification checklists on energized machinery.\n\n"
            "**Recommended Action**: Issue a temporary stop-work notice on C-204 non-routine maintenance until an energy isolation & permit audit is signed off by the Operations Manager."
        )

    else:
        rel_reports = tools.search_safety_reports(query=user_message, conversation_id=conversation_id, limit=3)
        if rel_reports and len(rel_reports) > 0:
            answer_text = (
                f"**Safety Assessment regarding '{user_message}':**\n\n"
                "**Relevant Enterprise Safety Evidence:**\n" +
                "\n".join([f"• **{r['report_id']}** [{r.get('risk_band', 'REVIEW')}]: {r['text']}" for r in rel_reports]) +
                "\n\n**HSE Control Guidance (Hierarchy of Controls):**\n"
                "• **Engineering Control**: Implement physical interlocks, secondary containment, and calibrated sensors.\n"
                "• **Administrative**: Validate Permit to Work, execute JSA (Job Safety Analysis), and conduct toolbox safety briefing.\n"
                "• **PPE**: Ensure mandatory certified safety gear is inspected prior to task initiation."
            )
        else:
            answer_text = (
                f"**HSE Guidance for '{user_message}':**\n\n"
                "Safety risk management requires rigorous barrier verification across all operational phases.\n\n"
                "**Key Safety Tenets:**\n"
                "1. **Pre-Task Risk Assessment**: Identify active energy sources, line-of-fire exposures, and environmental vectors.\n"
                "2. **Barrier Verification**: Never assume a safety system is functioning without physical or instrumentation confirmation.\n"
                "3. **Stop Work Authority (SWA)**: Every personnel on site has the contractual authority and obligation to halt work if unsafe conditions emerge.\n\n"
                "Feel free to upload your own safety report or ask about specific assets, incident precursors, or regulatory compliance."
            )

    return {
        "answer": answer_text,
        "evidence": evidence,
        "tools_used": tools_used,
        "conversation_id": conversation_id
    }

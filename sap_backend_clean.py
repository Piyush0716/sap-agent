from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import requests
import json
import re
from groq import Groq
from datetime import datetime
import random
import string

app = FastAPI(title="SAP Agent")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"], allow_credentials=True)

SUPABASE_URL = "https://wqaiziymroogggjyalqe.supabase.co"
SUPABASE_KEY = "sb_secret_R_mcP6nHrmXLxfnHJVio3w_DJHwvzfK"
GROQ_KEY = "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"

groq_client = Groq(api_key=GROQ_KEY)
SB = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}

def db_get(table, params=""):
    try:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/{table}?{params}", headers=SB, timeout=15)
        return r.json() if r.status_code == 200 else []
    except:
        return []

def db_post(table, data):
    try:
        r = requests.post(f"{SUPABASE_URL}/rest/v1/{table}", headers={**SB, "Prefer": "return=representation"}, json=data, timeout=15)
        return r.json(), r.status_code
    except:
        return {}, 500

def db_patch(table, col, val, data):
    try:
        r = requests.patch(f"{SUPABASE_URL}/rest/v1/{table}?{col}=eq.{val}", headers={**SB, "Prefer": "return=representation"}, json=data, timeout=15)
        return r.json(), r.status_code
    except:
        return {}, 500

def rand_id():
    return "CASE-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

class CaseIn(BaseModel):
    description: str
    request_type: Optional[str] = None
    pdf_text: Optional[str] = None
    case_id: Optional[str] = None

class OpsIn(BaseModel):
    case_id: str
    action: str
    modified_summary: Optional[dict] = None
    ops_user: Optional[str] = "Priya Nair | priya.nair@hpe.com"

PROMPT = """You are an expert at reading enterprise service contract requests.
Extract fields from the description and return ONLY valid JSON.

Fields:
- request_type: one of [Contract Amendment, Renewal Amendment, Orders, New Business Quote, Renewal Quote]
- contract_id: ID starting with CTR- (null if not found)
- quote_id: ID starting with QT- (null if not found)
- order_id: ID starting with ORD- (null if not found)
- reference_id: ID starting with REF- (null if not found)
- serial_numbers: list of IDs starting with SRL- (empty list if none)
- customer_name: company name mentioned (null if not found)
- change_type: what the customer wants (e.g. change quantity, add serial, renew contract)
- change_details: specific details (e.g. from 5 to 10, remove SRL-XXX)
- term_months: renewal term in months (null if not found)
- missing_fields: list of mandatory fields missing

Mandatory by type:
- Contract Amendment: contract_id + change_type
- Renewal Amendment: (quote_id OR reference_id) + change_type
- Orders: (order_id OR reference_id) + change_type
- New Business Quote: customer_name + change_type
- Renewal Quote: contract_id + change_type

Request type (from form, use this if description does not specify): {rt}
Description: {desc}
PDF text: {pdf}
"""

def extract(description, pdf_text="", request_type=""):
    try:
        r = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": PROMPT.format(desc=description, pdf=pdf_text or "None", rt=request_type or "Not specified")}],
            max_tokens=800, temperature=0
        )
        text = re.sub(r'```json|```', '', r.choices[0].message.content.strip()).strip()
        return json.loads(text)
    except Exception as e:
        return {"error": str(e), "change_type": "unknown", "missing_fields": ["description unclear"]}

def validate(extracted):
    found = {}
    not_found = []
    if extracted.get("contract_id"):
        rows = db_get("contracts", f"contract_id=eq.{extracted['contract_id']}&select=contract_id,customer_name,product_description,quantity,contract_status,contract_end_date,asset_serial_number")
        if rows: found["contract"] = rows[0]
        else: not_found.append(f"Contract {extracted['contract_id']} not found")
    if extracted.get("quote_id"):
        rows = db_get("quotes", f"quote_id=eq.{extracted['quote_id']}&select=quote_id,customer_name,product_description,quantity,quote_status,term_months")
        if rows: found["quote"] = rows[0]
        else: not_found.append(f"Quote {extracted['quote_id']} not found")
    if extracted.get("reference_id"):
        rows = db_get("quotes", f"reference_id=eq.{extracted['reference_id']}&select=quote_id,customer_name,product_description,quantity,quote_status")
        if rows: found["quote_by_ref"] = rows[0]
        else:
            rows = db_get("orders", f"reference_id=eq.{extracted['reference_id']}&select=order_id,customer_name,product_description,quantity,order_status")
            if rows: found["order_by_ref"] = rows[0]
            else: not_found.append(f"Reference {extracted['reference_id']} not found")
    if extracted.get("order_id"):
        rows = db_get("orders", f"order_id=eq.{extracted['order_id']}&select=order_id,customer_name,product_description,quantity,order_status")
        if rows: found["order"] = rows[0]
        else: not_found.append(f"Order {extracted['order_id']} not found")
    return {"found": found, "not_found": not_found}

def build_summary(extracted, validation):
    rec = (validation["found"].get("contract") or validation["found"].get("quote") or
           validation["found"].get("quote_by_ref") or validation["found"].get("order_by_ref") or
           validation["found"].get("order") or {})
    
    # Check quantity mismatch
    mismatch = None
    if rec.get("quantity") and extracted.get("change_details"):
        cd = extracted["change_details"].lower()
        nums = re.findall(r'\d+', cd)
        if nums and int(nums[0]) != int(rec["quantity"]):
            mismatch = {"requested_from": nums[0], "db_current": str(rec["quantity"])}

    return {
        "request_type": extracted.get("request_type"),
        "customer_name": rec.get("customer_name") or extracted.get("customer_name", "Unknown"),
        "record_id": (extracted.get("contract_id") or extracted.get("quote_id") or
                     extracted.get("order_id") or extracted.get("reference_id")),
        "product": rec.get("product_description", "—"),
        "current_quantity": rec.get("quantity"),
        "serial_numbers": extracted.get("serial_numbers", []),
        "change_type": extracted.get("change_type", "—"),
        "change_details": extracted.get("change_details", "—"),
        "term_months": extracted.get("term_months"),
        "db_record": rec,
        "validated": len(validation["not_found"]) == 0 and bool(validation["found"]),
        "validation_issues": validation["not_found"],
        "quantity_mismatch": mismatch
    }

@app.get("/health")
def health():
    return {"status": "ok", "service": "SAP Agent", "model": "llama-3.3-70b-versatile"}

@app.post("/process-case")
def process_case(req: CaseIn):
    case_id = req.case_id or rand_id()
    extracted = extract(req.description, req.pdf_text, req.request_type or "")
    if "error" in extracted and not extracted.get("change_type"):
        return {"status": "error", "case_id": case_id, "message": "Could not process request. Please try again."}
    # Use form request_type if LLM didn't extract it
    if req.request_type and not extracted.get("request_type"):
        extracted["request_type"] = req.request_type
    # Remove request_type from missing_fields if provided in form
    if req.request_type and "request_type" in extracted.get("missing_fields", []):
        extracted["missing_fields"] = [m for m in extracted["missing_fields"] if "request_type" not in m]
    missing = extracted.get("missing_fields", [])
    if not extracted.get("request_type"):
        missing.append("request_type")
    if missing:
        questions = []
        for m in missing:
            if "contract_id" in m: questions.append("Could you provide your Contract ID? (Format: CTR-XXXXXXXX)")
            elif "quote_id" in m or "reference_id" in m: questions.append("Could you provide your Quote ID (QT-XXXXXXXX) or Reference ID (REF-XXXXXXXXXX)?")
            elif "order_id" in m: questions.append("Could you provide your Order ID (ORD-XXXXXXXX) or Reference ID (REF-XXXXXXXXXX)?")
            elif "customer_name" in m: questions.append("Could you provide your company name?")
            elif "change_type" in m: questions.append("Could you describe what change you would like to make?")
            elif "request_type" in m: questions.append("Could you clarify the type of request? (Contract Amendment, Renewal, New Quote, Order)")
            else: questions.append(f"Could you provide: {m}?")
        try: db_post("agent_cases", {"case_id": case_id, "description": req.description, "request_type": extracted.get("request_type"), "status": "escalated_to_customer", "extracted_data": json.dumps(extracted), "created_at": datetime.utcnow().isoformat()})
        except: pass
        return {"status": "escalated", "case_id": case_id, "questions": questions, "extracted_so_far": extracted}
    validation = validate(extracted)
    summary = build_summary(extracted, validation)
    summary["case_id"] = case_id
    try: db_post("agent_cases", {"case_id": case_id, "description": req.description, "request_type": extracted.get("request_type"), "status": "pending_customer_confirm", "extracted_data": json.dumps(extracted), "summary": json.dumps(summary), "created_at": datetime.utcnow().isoformat()})
    except: pass
    if validation["not_found"]:
        return {"status": "validation_failed", "case_id": case_id, "message": "Could not validate some IDs against database.", "validation_issues": validation["not_found"], "summary": summary}
    return {"status": "ready_for_confirm", "case_id": case_id, "message": "Request understood. Please confirm.", "summary": summary}

@app.post("/customer-confirm/{case_id}")
def customer_confirm(case_id: str):
    try: db_patch("agent_cases", "case_id", case_id, {"status": "pending_ops_review"})
    except: pass
    return {"status": "ok", "message": "Forwarded to Services Operations team."}

@app.get("/ops-queue")
def ops_queue():
    cases = db_get("agent_cases", "status=eq.pending_ops_review&order=created_at.desc&limit=50")
    result = []
    for c in (cases if isinstance(cases, list) else []):
        try: summary = json.loads(c.get("summary") or "{}")
        except: summary = {}
        result.append({"case_id": c["case_id"], "request_type": c.get("request_type"), "status": c.get("status"), "created_at": c.get("created_at"), "description": c.get("description"), "summary": summary})
    return result

@app.post("/ops-action")
def ops_action(req: OpsIn):
    if req.action in ["approve", "final_approve"]:
        cases = db_get("agent_cases", f"case_id=eq.{req.case_id}&select=*")
        if not cases: return {"status": "error", "message": "Case not found"}
        case = cases[0]
        try: summary = json.loads(case.get("summary") or "{}")
        except: summary = {}
        if req.modified_summary: summary = req.modified_summary
        sap = {"case_id": req.case_id, "request_type": case.get("request_type"), "record_id": summary.get("record_id"), "customer_name": summary.get("customer_name"), "change_type": summary.get("change_type"), "change_details": summary.get("change_details"), "approved_by": req.ops_user, "approved_at": datetime.utcnow().isoformat(), "sap_status": "simulated_success", "sap_message": f"SAP API called — {summary.get('change_type')} applied to {summary.get('record_id')}"}
        try: db_post("sap_updates", sap)
        except: pass
        try: db_patch("agent_cases", "case_id", req.case_id, {"status": "approved_sap_updated"})
        except: pass
        return {"status": "ok", "message": f"SAP updated. {summary.get('change_type')} applied to {summary.get('record_id')}.", "sap_record": sap}
    elif req.action == "modify":
        if req.modified_summary:
            try: db_patch("agent_cases", "case_id", req.case_id, {"summary": json.dumps(req.modified_summary), "status": "modified_pending_confirm"})
            except: pass
        return {"status": "ok", "message": "Case updated."}
    elif req.action == "info_request":
        try: db_patch("agent_cases", "case_id", req.case_id, {"status": "info_requested", "ops_message": req.modified_summary.get("message","") if req.modified_summary else ""})
        except: pass
        return {"status": "ok", "message": "Info request sent to customer."}
    return {"status": "error", "message": "Unknown action"}

@app.get("/sap-log")
def sap_log():
    data = db_get("sap_updates", "order=approved_at.desc&limit=100")
    return data if isinstance(data, list) else []

@app.get("/cases")
def get_cases():
    data = db_get("agent_cases", "order=created_at.desc&limit=100")
    return data if isinstance(data, list) else []

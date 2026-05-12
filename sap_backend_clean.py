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
import base64
import io

try:
    import pdfplumber
    PDF_SUPPORT = True
except:
    PDF_SUPPORT = False

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
        r = requests.post(f"{SUPABASE_URL}/rest/v1/{table}", 
            headers={**SB, "Prefer": "return=representation"}, json=data, timeout=15)
        return r.json(), r.status_code
    except:
        return {}, 500

def db_patch(table, col, val, data):
    try:
        r = requests.patch(f"{SUPABASE_URL}/rest/v1/{table}?{col}=eq.{val}",
            headers={**SB, "Prefer": "return=representation"}, json=data, timeout=15)
        return r.json(), r.status_code
    except:
        return {}, 500

def rand_id():
    return "CASE-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

def extract_pdf(b64):
    if not PDF_SUPPORT or not b64:
        return ""
    try:
        pdf_bytes = base64.b64decode(b64)
        parts = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages[:10]:
                t = page.extract_text()
                if t:
                    parts.append(t)
        return "\n".join(parts)[:4000]
    except:
        return ""

def fetch_db_context(text):
    """Fetch relevant records from DB based on IDs found in text"""
    context = []
    
    # Find contract IDs
    for cid in re.findall(r'CTR-[A-Z0-9]+', text):
        rows = db_get("contracts", f"contract_id=eq.{cid}&select=contract_id,customer_name,product_description,quantity,contract_status,contract_end_date,asset_serial_number,contract_type,quote_id,order_id")
        if rows:
            context.append(f"CONTRACT FOUND IN DATABASE:\n{json.dumps(rows[0], indent=2)}")

    # Find quote IDs
    for qid in re.findall(r'QT-[A-Z0-9]+', text):
        rows = db_get("quotes", f"quote_id=eq.{qid}&select=quote_id,customer_name,product_description,quantity,quote_status,term_months,reference_id,contract_id")
        if rows:
            context.append(f"QUOTE FOUND IN DATABASE:\n{json.dumps(rows[0], indent=2)}")

    # Find reference IDs
    for rid in re.findall(r'REF-[A-Z0-9]+', text):
        rows = db_get("quotes", f"reference_id=eq.{rid}&select=quote_id,customer_name,product_description,quantity,quote_status,term_months")
        if not rows:
            rows = db_get("orders", f"reference_id=eq.{rid}&select=order_id,customer_name,product_description,quantity,order_status")
        if rows:
            context.append(f"RECORD FOUND IN DATABASE:\n{json.dumps(rows[0], indent=2)}")

    # Find order IDs
    for oid in re.findall(r'ORD-[A-Z0-9]+', text):
        rows = db_get("orders", f"order_id=eq.{oid}&select=order_id,customer_name,product_description,quantity,order_status,reference_id")
        if rows:
            context.append(f"ORDER FOUND IN DATABASE:\n{json.dumps(rows[0], indent=2)}")

    return "\n\n".join(context)

SYSTEM_PROMPT = """You are an intelligent SAP contract management agent. You work for HPE Services Operations.

Your job is to understand service contract change requests from customers, partners, and sales reps — and prepare structured summaries for the Services Operations team to approve and execute in SAP.

You have access to a contract database. When a request comes in, you will receive:
1. The customer's description (could be in any language)
2. Any PDF content attached
3. Any matching database records already fetched for you

Your behaviour:
- Read everything provided and reason intelligently — like a smart human ops analyst would
- Extract what you understand: what needs to change, on which record, for which customer
- If information is in the PDF or database records, use it — do not ask for it again
- Only ask for clarification if something is genuinely ambiguous or missing that you cannot infer
- Do not ask for information that is already present anywhere in the context
- Use common sense: if someone says "change end customer name", that applies to the contract level — do not ask which item
- Be natural — do not sound like a bot with a checklist

Always respond in this JSON format:
{
  "status": "understood" | "need_clarification" | "error",
  "message": "Natural language response to show the customer",
  "clarification_questions": ["question1", "question2"],  // only if status is need_clarification
  "extracted": {
    "request_type": "Contract Amendment | Renewal Amendment | Orders | New Business Quote | Renewal Quote",
    "record_id": "CTR-XXXXX or QT-XXXXX or ORD-XXXXX or REF-XXXXX",
    "customer_name": "...",
    "product": "...",
    "current_quantity": null,
    "change_type": "what needs to change",
    "change_details": "specific details of the change",
    "serial_numbers": [],
    "term_months": null,
    "validated": true/false,
    "quantity_mismatch": null or {"requested_from": "X", "db_current": "Y"}
  }
}

Return ONLY valid JSON. No markdown, no explanation outside the JSON."""

def call_agent(description, pdf_text, db_context, request_type, chat_history):
    """Call LLM agent with full context"""
    
    user_message = f"""REQUEST TYPE (selected by user): {request_type or 'Not specified'}

CUSTOMER DESCRIPTION:
{description}
"""
    if pdf_text:
        user_message += f"""
PDF CONTENT:
{pdf_text}
"""
    if db_context:
        user_message += f"""
DATABASE RECORDS (already fetched):
{db_context}
"""
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    # Add chat history for multi-turn
    for h in chat_history[-6:]:
        messages.append(h)
    
    messages.append({"role": "user", "content": user_message})
    
    try:
        r = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=1200,
            temperature=0.1
        )
        text = re.sub(r'```json|```', '', r.choices[0].message.content.strip()).strip()
        result = json.loads(text)
        return result, messages + [{"role": "assistant", "content": r.choices[0].message.content}]
    except Exception as e:
        return {"status": "error", "message": f"Agent error: {str(e)}", "extracted": {}}, messages

class CaseIn(BaseModel):
    description: str
    request_type: Optional[str] = None
    pdf_base64: Optional[str] = None
    case_id: Optional[str] = None
    chat_history: Optional[list] = []

class OpsIn(BaseModel):
    case_id: str
    action: str
    modified_summary: Optional[dict] = None
    ops_user: Optional[str] = "Priya Nair | priya.nair@hpe.com"

@app.get("/health")
def health():
    return {"status": "ok", "service": "SAP Agent v2", "model": "llama-3.3-70b-versatile"}

@app.post("/process-case")
def process_case(req: CaseIn):
    case_id = req.case_id or rand_id()
    
    # Extract PDF text
    pdf_text = extract_pdf(req.pdf_base64) if req.pdf_base64 else ""
    
    # Combine all text to search for IDs
    all_text = f"{req.description} {pdf_text}"
    
    # Fetch database context
    db_context = fetch_db_context(all_text)
    
    # Call LLM agent
    result, updated_history = call_agent(
        req.description, 
        pdf_text, 
        db_context, 
        req.request_type,
        req.chat_history or []
    )
    
    status = result.get("status", "error")
    extracted = result.get("extracted", {})
    
    # Check quantity mismatch
    if extracted.get("current_quantity") and extracted.get("change_details"):
        nums = re.findall(r'\d+', str(extracted.get("change_details", "")))
        if nums and db_context:
            import re as re2
            db_qty = re2.findall(r'"quantity":\s*(\d+)', db_context)
            if db_qty and nums[0] != db_qty[0]:
                extracted["quantity_mismatch"] = {
                    "requested_from": nums[0],
                    "db_current": db_qty[0]
                }
    
    # Save case
    try:
        db_post("agent_cases", {
            "case_id": case_id,
            "description": req.description,
            "request_type": extracted.get("request_type") or req.request_type,
            "status": "pending_customer_confirm" if status == "understood" else "escalated_to_customer",
            "extracted_data": json.dumps(extracted),
            "summary": json.dumps(extracted),
            "created_at": datetime.utcnow().isoformat()
        })
    except:
        pass
    
    if status == "need_clarification":
        return {
            "status": "escalated",
            "case_id": case_id,
            "message": result.get("message", "I need some clarification."),
            "questions": result.get("clarification_questions", []),
            "extracted_so_far": extracted,
            "chat_history": updated_history
        }
    elif status == "understood":
        summary = {
            "case_id": case_id,
            "request_type": extracted.get("request_type") or req.request_type,
            "customer_name": extracted.get("customer_name", "—"),
            "record_id": extracted.get("record_id", "—"),
            "product": extracted.get("product", "—"),
            "current_quantity": extracted.get("current_quantity"),
            "change_type": extracted.get("change_type", "—"),
            "change_details": extracted.get("change_details", "—"),
            "serial_numbers": extracted.get("serial_numbers", []),
            "term_months": extracted.get("term_months"),
            "validated": extracted.get("validated", False),
            "validation_issues": [] if extracted.get("validated") else ["Could not verify against database"],
            "quantity_mismatch": extracted.get("quantity_mismatch"),
            "db_record": {}
        }
        return {
            "status": "ready_for_confirm",
            "case_id": case_id,
            "message": result.get("message", "I have understood your request. Please confirm."),
            "summary": summary,
            "chat_history": updated_history
        }
    else:
        return {"status": "error", "case_id": case_id, "message": result.get("message", "Could not process request.")}

@app.post("/customer-confirm/{case_id}")
def customer_confirm(case_id: str):
    try:
        db_patch("agent_cases", "case_id", case_id, {"status": "pending_ops_review"})
    except:
        pass
    return {"status": "ok", "message": "Forwarded to Services Operations team."}

@app.get("/ops-queue")
def ops_queue():
    cases = db_get("agent_cases", "status=eq.pending_ops_review&order=created_at.desc&limit=50")
    result = []
    for c in (cases if isinstance(cases, list) else []):
        try: summary = json.loads(c.get("summary") or "{}")
        except: summary = {}
        result.append({
            "case_id": c["case_id"],
            "request_type": c.get("request_type"),
            "status": c.get("status"),
            "created_at": c.get("created_at"),
            "description": c.get("description"),
            "summary": summary
        })
    return result

@app.post("/ops-action")
def ops_action(req: OpsIn):
    if req.action in ["approve", "final_approve"]:
        cases = db_get("agent_cases", f"case_id=eq.{req.case_id}&select=*")
        if not cases:
            return {"status": "error", "message": "Case not found"}
        case = cases[0]
        try: summary = json.loads(case.get("summary") or "{}")
        except: summary = {}
        if req.modified_summary:
            summary = req.modified_summary
        sap = {
            "case_id": req.case_id,
            "request_type": case.get("request_type"),
            "record_id": summary.get("record_id"),
            "customer_name": summary.get("customer_name"),
            "change_type": summary.get("change_type"),
            "change_details": summary.get("change_details"),
            "approved_by": req.ops_user,
            "approved_at": datetime.utcnow().isoformat(),
            "sap_status": "simulated_success",
            "sap_message": f"SAP API called — {summary.get('change_type')} applied to {summary.get('record_id')}"
        }
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
        msg = req.modified_summary.get("message", "") if req.modified_summary else ""
        try: db_patch("agent_cases", "case_id", req.case_id, {"status": "info_requested"})
        except: pass
        return {"status": "ok", "message": "Info request sent."}
    
    return {"status": "error", "message": "Unknown action"}

@app.get("/sap-log")
def sap_log():
    data = db_get("sap_updates", "order=approved_at.desc&limit=100")
    return data if isinstance(data, list) else []

@app.get("/cases")
def get_cases():
    data = db_get("agent_cases", "order=created_at.desc&limit=100")
    return data if isinstance(data, list) else []

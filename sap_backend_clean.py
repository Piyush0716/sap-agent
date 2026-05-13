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

def generate_contract_pdf(contract: dict, case_id: str) -> str:
    """Generate updated contract PDF and return as base64"""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
        from reportlab.lib import colors
        from reportlab.lib.units import mm
        from reportlab.lib.enums import TA_RIGHT
        import base64
        import io as _io

        buf = _io.BytesIO()
        W_PAGE = A4[0]; W = W_PAGE - 30*mm
        doc = SimpleDocTemplate(buf, pagesize=A4,
            leftMargin=15*mm, rightMargin=15*mm, topMargin=12*mm, bottomMargin=12*mm)

        GREEN  = colors.HexColor('#01A982')
        DARK   = colors.HexColor('#1A1A1A')
        MGRAY  = colors.HexColor('#4A4A4A')
        LGRAY  = colors.HexColor('#F5F5F5')
        BORDER = colors.HexColor('#D8D8D8')
        WHITE  = colors.white

        def p(text, **kw):
            d = dict(fontName='Helvetica', fontSize=9, textColor=DARK, leading=13)
            d.update(kw)
            return Paragraph(str(text), ParagraphStyle('_', **d))

        def sec(title):
            t = Table([[p(title, fontSize=8, fontName='Helvetica-Bold', textColor=WHITE, leading=12)]], colWidths=[W])
            t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),DARK),('PADDING',(0,0),(-1,-1),[8,5,8,5])]))
            return t

        story = []

        # Header
        hdr = Table([[
            Table([[p('<b>HPE</b>', fontSize=28, fontName='Helvetica-Bold', textColor=GREEN, leading=32)],
                   [p('Hewlett Packard Enterprise', fontSize=9, textColor=MGRAY, leading=12)],
                   [p('Technology Services Division', fontSize=8, textColor=MGRAY, leading=11)]],
                  colWidths=[75*mm]),
            Table([[p('UPDATED SERVICE CONTRACT', fontSize=16, fontName='Helvetica-Bold', textColor=DARK, leading=20, alignment=TA_RIGHT)],
                   [p(f'Contract: <b>{contract.get("contract_id","—")}</b>', fontSize=10, textColor=MGRAY, leading=14, alignment=TA_RIGHT)],
                   [p(f'Updated via Case: {case_id}', fontSize=9, textColor=MGRAY, leading=13, alignment=TA_RIGHT)],
                   [p(f'Updated: {datetime.utcnow().strftime("%d %b %Y %H:%M UTC")}', fontSize=9, textColor=colors.HexColor('#C23934'), fontName='Helvetica-Bold', leading=13, alignment=TA_RIGHT)]],
                  colWidths=[W-75*mm]),
        ]], colWidths=[75*mm, W-75*mm])
        hdr.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('PADDING',(0,0),(-1,-1),0)]))
        story += [hdr, Spacer(1,3*mm)]
        story.append(HRFlowable(width=W, thickness=2, color=GREEN))
        story.append(Spacer(1,2*mm))

        # Update notice
        notice = Table([[p(f'⚠ This contract has been updated. Changes applied via SAP Agent Case {case_id}.',
                          fontSize=9, fontName='Helvetica-Bold', textColor=colors.HexColor('#C23934'), leading=13)]],
                       colWidths=[W])
        notice.setStyle(TableStyle([
            ('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#FDECEA')),
            ('PADDING',(0,0),(-1,-1),8),
            ('BOX',(0,0),(-1,-1),1,colors.HexColor('#F09D98')),
        ]))
        story += [notice, Spacer(1,4*mm)]

        # Contract details
        story += [sec('CONTRACT DETAILS'), Spacer(1,1*mm)]
        details = [
            [p('Contract ID', fontSize=8, textColor=MGRAY), p(f'<b>{contract.get("contract_id","—")}</b>', fontName='Courier'),
             p('Status', fontSize=8, textColor=MGRAY), p(f'<b>{contract.get("contract_status","Active")}</b>', textColor=GREEN, fontName='Helvetica-Bold')],
            [p('Contract Type', fontSize=8, textColor=MGRAY), p(contract.get("contract_type","—")),
             p('Term', fontSize=8, textColor=MGRAY), p(f'{contract.get("contract_term_months","—")} months')],
            [p('Start Date', fontSize=8, textColor=MGRAY), p(str(contract.get("contract_start_date","—"))),
             p('End Date', fontSize=8, textColor=MGRAY), p(str(contract.get("contract_end_date","—")))],
        ]
        dt = Table(details, colWidths=[W/4]*4)
        dt.setStyle(TableStyle([
            ('GRID',(0,0),(-1,-1),0.5,BORDER),('PADDING',(0,0),(-1,-1),6),
            ('BACKGROUND',(0,0),(0,-1),LGRAY),('BACKGROUND',(2,0),(2,-1),LGRAY),
            ('ROWBACKGROUNDS',(0,0),(-1,-1),[WHITE,colors.HexColor('#FAFAFA')]),
        ]))
        story += [dt, Spacer(1,4*mm)]

        # Customer
        story += [sec('CUSTOMER INFORMATION'), Spacer(1,1*mm)]
        cust = [
            [p('End Customer', fontSize=8, textColor=MGRAY), p(f'<b>{contract.get("customer_name","—")}</b>'),
             p('Customer ID', fontSize=8, textColor=MGRAY), p(str(contract.get("customer_id","—")))],
            [p('Country', fontSize=8, textColor=MGRAY), p(contract.get("customer_country","—")),
             p('Reseller', fontSize=8, textColor=MGRAY), p(contract.get("reseller_name","—"))],
            [p('Distributor', fontSize=8, textColor=MGRAY), p(contract.get("distributor_name","—")),
             p('Region', fontSize=8, textColor=MGRAY), p('—')],
        ]
        ct = Table(cust, colWidths=[W/4]*4)
        ct.setStyle(TableStyle([
            ('GRID',(0,0),(-1,-1),0.5,BORDER),('PADDING',(0,0),(-1,-1),6),
            ('BACKGROUND',(0,0),(0,-1),LGRAY),('BACKGROUND',(2,0),(2,-1),LGRAY),
            ('ROWBACKGROUNDS',(0,0),(-1,-1),[WHITE,colors.HexColor('#FAFAFA')]),
        ]))
        story += [ct, Spacer(1,4*mm)]

        # Product & Asset
        story += [sec('PRODUCT & ASSET DETAILS'), Spacer(1,1*mm)]
        prod = [
            [p('#',fontSize=8,fontName='Helvetica-Bold',textColor=WHITE,leading=12),
             p('PRODUCT ID',fontSize=8,fontName='Helvetica-Bold',textColor=WHITE,leading=12),
             p('DESCRIPTION',fontSize=8,fontName='Helvetica-Bold',textColor=WHITE,leading=12),
             p('QTY',fontSize=8,fontName='Helvetica-Bold',textColor=WHITE,leading=12,alignment=TA_RIGHT),
             p('SERIAL NUMBER',fontSize=8,fontName='Helvetica-Bold',textColor=WHITE,leading=12),
             p('VALUE (USD)',fontSize=8,fontName='Helvetica-Bold',textColor=WHITE,leading=12,alignment=TA_RIGHT)],
            [p('1'), p(str(contract.get("product_id","—")), fontName='Courier', fontSize=8),
             p(f'<b>{contract.get("product_description","—")}</b><br/><font size="8" color="#767676">{contract.get("product_line","")}</font>', leading=14),
             p(str(contract.get("quantity","—")), alignment=TA_RIGHT, fontName='Helvetica-Bold'),
             p(str(contract.get("asset_serial_number","—")), fontName='Courier', fontSize=8),
             p(f'{float(contract.get("contract_value_usd",0)):,.2f}', alignment=TA_RIGHT, fontName='Helvetica-Bold')],
        ]
        cw = [8*mm, 24*mm, 58*mm, 12*mm, W-142*mm, 30*mm]
        cw[-1] = W - sum(cw[:-1])
        pt = Table(prod, colWidths=cw)
        pt.setStyle(TableStyle([
            ('BACKGROUND',(0,0),(-1,0),DARK),('TEXTCOLOR',(0,0),(-1,0),WHITE),
            ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,0),8),
            ('GRID',(0,0),(-1,-1),0.5,BORDER),('PADDING',(0,0),(-1,-1),6),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[WHITE,LGRAY]),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ]))
        story += [pt, Spacer(1,4*mm)]

        # Approval stamp
        story += [sec('APPROVAL RECORD'), Spacer(1,1*mm)]
        appr = [
            [p('Case ID', fontSize=8, textColor=MGRAY), p(case_id, fontName='Courier'),
             p('Approved By', fontSize=8, textColor=MGRAY), p('Services Operations — HPE')],
            [p('Change Applied', fontSize=8, textColor=MGRAY), p(f'{contract.get("_change_type","Contract update")}'),
             p('Timestamp', fontSize=8, textColor=MGRAY), p(datetime.utcnow().strftime('%d %b %Y %H:%M UTC'))],
        ]
        at = Table(appr, colWidths=[W/4]*4)
        at.setStyle(TableStyle([
            ('GRID',(0,0),(-1,-1),0.5,BORDER),('PADDING',(0,0),(-1,-1),6),
            ('BACKGROUND',(0,0),(0,-1),LGRAY),('BACKGROUND',(2,0),(2,-1),LGRAY),
            ('ROWBACKGROUNDS',(0,0),(-1,-1),[WHITE,colors.HexColor('#FAFFFE')]),
        ]))
        story += [at, Spacer(1,4*mm)]

        # Footer
        story.append(HRFlowable(width=W, thickness=1.5, color=GREEN))
        story.append(Spacer(1,2*mm))
        footer = Table([[
            p('Hewlett Packard Enterprise | hpe.com/services', fontSize=8, textColor=MGRAY),
            p('System-generated after SAP Agent approval — Official Record', fontSize=8, textColor=MGRAY),
            p('Page 1 of 1', fontSize=8, textColor=MGRAY, alignment=TA_RIGHT),
        ]], colWidths=[W/3]*3)
        footer.setStyle(TableStyle([('PADDING',(0,0),(-1,-1),0),('VALIGN',(0,0),(-1,-1),'TOP')]))
        story.append(footer)

        doc.build(story)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode('utf-8')
    except Exception as e:
        return None

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
    if not b64:
        return ""
    try:
        pdf_bytes = base64.b64decode(b64)
        # Try pdfplumber first
        if PDF_SUPPORT:
            try:
                parts = []
                with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                    for page in pdf.pages[:10]:
                        t = page.extract_text()
                        if t:
                            parts.append(t)
                if parts:
                    return "\n".join(parts)[:4000]
            except Exception as e:
                pass
        # Fallback: scan raw bytes for text patterns (catches IDs even without pdfplumber)
        raw = pdf_bytes.decode('latin-1', errors='ignore')
        # Extract readable ASCII chunks
        import re as _r
        chunks = _r.findall(r'[A-Za-z0-9\-\.,:/ ]{8,}', raw)
        return " ".join(chunks)[:4000]
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

Key rules:
- request_type: ALWAYS use the one provided in "Request Type (from form)" — never change it
- record_id: scan ALL text including PDF content for CTR-/QT-/ORD-/REF- patterns or 10-digit IDs starting with 4 or 2
- validated: set true ONLY if the record_id appears in the DATABASE RECORDS section provided
- serial_numbers: only SRL- format IDs, never contract or quote IDs

Always respond in this JSON format:
{
  "status": "understood" | "need_clarification" | "error",
  "message": "Natural language response to show the customer",
  "clarification_questions": ["question1", "question2"],  // only if status is need_clarification
  "extracted": {
    "request_type": "Contract Amendment | Renewal Amendment | Orders | New Business Quote | Renewal Quote",
    "record_id": "CRITICAL — extract from PDF or text. CTR-XXXXXXXX = contract, QT-XXXXXXXX = quote, ORD-XXXXXXXX = order, REF-XXXXXXXXXX = reference. Also look for 10-digit numbers starting with 4 (contracts) or 2 (quotes). NEVER put serial numbers here — serials go in serial_numbers only.",
    "customer_name": "...",
    "product": "...",
    "current_quantity": null,
    "change_type": "what needs to change",
    "change_details": "specific details of the change",
    "serial_numbers": [],
    "term_months": null,
    "validated": true if record_id was found in the DATABASE RECORDS provided above, false otherwise,
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
    pdf_base64_2: Optional[str] = None
    pdf_base64_3: Optional[str] = None
    pdf_names: Optional[list] = []
    case_id: Optional[str] = None
    chat_history: Optional[list] = []

class OpsIn(BaseModel):
    case_id: str
    action: str
    modified_summary: Optional[dict] = None
    ops_user: Optional[str] = "Priya Nair | priya.nair@hpe.com"

@app.get("/health")
def health():
    return {"status": "ok", "service": "SAP Agent v2", "model": "llama-3.3-70b-versatile", "pdf_support": PDF_SUPPORT}

@app.post("/debug-pdf")
async def debug_pdf(req: CaseIn):
    """Debug endpoint to check PDF extraction"""
    pdf_text = extract_pdf(req.pdf_base64) if req.pdf_base64 else ""
    import re as _r
    ids = _r.findall(r'CTR-[A-Z0-9]+|QT-[A-Z0-9]+|SRL-[A-Z0-9]+', pdf_text)
    return {
        "pdf_received": bool(req.pdf_base64),
        "pdf_base64_length": len(req.pdf_base64) if req.pdf_base64 else 0,
        "pdf_text_length": len(pdf_text),
        "pdf_text_preview": pdf_text[:300],
        "ids_found": ids,
        "pdf_support": PDF_SUPPORT
    }

@app.post("/process-case")
def process_case(req: CaseIn):
    case_id = req.case_id or rand_id()
    
    # Extract text from all PDFs
    pdf_texts = []
    pdf_names = req.pdf_names or []
    
    for i, (b64, name) in enumerate([(req.pdf_base64, pdf_names[0] if len(pdf_names)>0 else f"Document 1"),
                                      (req.pdf_base64_2, pdf_names[1] if len(pdf_names)>1 else f"Document 2"),
                                      (req.pdf_base64_3, pdf_names[2] if len(pdf_names)>2 else f"Document 3")]):
        if b64:
            text = extract_pdf(b64)
            if text:
                pdf_texts.append(f"--- {name} ---\n{text}")
    
    pdf_text = "\n\n".join(pdf_texts)
    
    # Combine all text to search for IDs
    all_text = f"{req.description} {pdf_text}"
    
    # PRE-EXTRACT IDs from all text BEFORE calling LLM
    import re as _pre
    pre_contract = _pre.findall(r'CTR-[A-Z0-9]+', all_text)
    pre_quote    = _pre.findall(r'QT-[A-Z0-9]+', all_text)
    pre_order    = _pre.findall(r'ORD-[A-Z0-9]+', all_text)
    pre_ref      = _pre.findall(r'REF-[A-Z0-9]+', all_text)
    pre_serial   = _pre.findall(r'SRL-[A-Z0-9]+', all_text)
    pre_record_id = (pre_contract or pre_quote or pre_order or pre_ref or [None])[0]

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

    # Python validation — source of truth, never rely on LLM for this
    import re as _re

    # Step 1: Always use pre-extracted record_id if LLM missed it
    if not extracted.get("record_id") and pre_record_id:
        extracted["record_id"] = pre_record_id

    # Step 2: validated = True if record_id appears anywhere in all_text (PDF + description)
    if extracted.get("record_id"):
        if extracted["record_id"] in all_text:
            extracted["validated"] = True

    # Step 3: Fill serial numbers from pre-extraction if LLM missed
    if not extracted.get("serial_numbers") and pre_serial:
        extracted["serial_numbers"] = pre_serial

    # Step 3: Pull customer_name from db_context if LLM missed it
    if db_context and not extracted.get("customer_name"):
        cn = _re.search(r'"customer_name":\s*"([^"]+)"', db_context)
        if cn:
            extracted["customer_name"] = cn.group(1)

    # Step 4: Pull product from db_context if LLM missed it
    if db_context and not extracted.get("product"):
        pd_match = _re.search(r'"product_description":\s*"([^"]+)"', db_context)
        if pd_match:
            extracted["product"] = pd_match.group(1)

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

        record_id = summary.get("record_id", "")
        change_type = (summary.get("change_type") or "").lower()
        change_details = summary.get("change_details") or ""
        serial_numbers = summary.get("serial_numbers") or []

        # ── STEP 1: Apply change to source table ──
        db_updated = False
        updated_contract = None
        update_payload = {}

        # ── QUOTES TABLE UPDATE (Renewal Amendment) ──
        if record_id and record_id.startswith("QT-"):
            existing = db_get("quotes", f"quote_id=eq.{record_id}&select=*")
            if existing:
                current = existing[0]
                import re as _rq

                # Customer name change
                if any(x in change_type for x in ["customer name","company name","sold to","end customer"]):
                    new_name = _rq.search(r"to[: ]+([^,]+)", change_details, _rq.IGNORECASE)
                    if new_name:
                        update_payload["customer_name"] = new_name.group(1).strip()

                # Serial replace — swap old for new
                if any(x in change_type for x in ["serial","replace","swap"]):
                    current_serials = current.get("asset_serial_number","")
                    if serial_numbers and len(serial_numbers) >= 2:
                        old_srl = serial_numbers[0]; new_srl = serial_numbers[1]
                        updated_serials = current_serials.replace(old_srl, new_srl)
                        update_payload["asset_serial_number"] = updated_serials

                # Serial remove — remove from list, reduce quantity
                if "remove" in change_type or "delete" in change_type:
                    current_serials = current.get("asset_serial_number","")
                    current_qty = int(current.get("quantity") or 0)
                    for srl in serial_numbers:
                        if srl in current_serials:
                            parts = [s.strip() for s in current_serials.split(",") if s.strip() != srl]
                            update_payload["asset_serial_number"] = ",".join(parts)
                            update_payload["quantity"] = current_qty - 1
                            current_serials = update_payload["asset_serial_number"]
                            current_qty = update_payload["quantity"]

                # SLA change
                if "sla" in change_type or "coverage" in change_type or "nbd" in change_type.lower():
                    if "nbd" in change_details.lower() or "next business" in change_details.lower():
                        update_payload["sla_code"] = "NBD"
                    else:
                        sla_match = _rq.search(r'([A-Z]{2}\d{3}[A-Z]\d)', change_details)
                        if sla_match:
                            update_payload["sla_code"] = sla_match.group(1)

                # Quantity change
                if "quantity" in change_type or "qty" in change_type:
                    nums = _rq.findall(r'\d+', change_details)
                    if nums:
                        update_payload["quantity"] = int(nums[-1])

                if update_payload:
                    try:
                        db_patch("quotes", "quote_id", record_id, update_payload)
                        db_updated = True
                        updated = db_get("quotes", f"quote_id=eq.{record_id}&select=*")
                        if updated:
                            updated_contract = updated[0]
                            updated_contract.update(update_payload)
                            updated_contract["_change_type"] = summary.get("change_type","")
                            updated_contract["_is_quote"] = True
                    except Exception as e:
                        pass

        if record_id and record_id.startswith("CTR-"):
            # Fetch current contract
            existing = db_get("contracts", f"contract_id=eq.{record_id}&select=*")
            if existing:
                current = existing[0]

                # Customer/company name change
                if any(x in change_type for x in ["customer name", "company name", "sold to", "end customer"]):
                    import re as _re
                    # Extract new name from change_details — "from X to Y" or just "to Y"
                    new_name = _re.search(r"to[: ]+([^,]+)", change_details, _re.IGNORECASE)
                    if new_name:
                        update_payload["customer_name"] = new_name.group(1).strip()

                # Serial number changes
                if any(x in change_type for x in ["serial", "sn", "add serial", "remove serial", "swap"]):
                    if serial_numbers:
                        if "remove" in change_type or "delete" in change_type:
                            update_payload["asset_serial_number"] = "REMOVED-" + current.get("asset_serial_number","")
                        elif "add" in change_type:
                            existing_serial = current.get("asset_serial_number","")
                            update_payload["asset_serial_number"] = existing_serial + "," + ",".join(serial_numbers)
                        else:
                            update_payload["asset_serial_number"] = ",".join(serial_numbers)

                # Quantity change
                if "quantity" in change_type or "qty" in change_type:
                    import re as _re2
                    nums = _re2.findall(r'\d+', change_details)
                    if nums:
                        update_payload["quantity"] = int(nums[-1])  # last number = new quantity

                # Date change
                if any(x in change_type for x in ["date", "end date", "start date", "term"]):
                    import re as _re3
                    dates = _re3.findall(r'\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{4}-\d{2}-\d{2}', change_details)
                    if dates:
                        if "end" in change_type:
                            update_payload["contract_end_date"] = dates[-1]
                        elif "start" in change_type:
                            update_payload["contract_start_date"] = dates[0]

                # Apply update to DB
                if update_payload:
                    try:
                        db_patch("contracts", "contract_id", record_id, update_payload)
                        db_updated = True
                        # Fetch updated record
                        updated = db_get("contracts", f"contract_id=eq.{record_id}&select=*")
                        if updated:
                            updated_contract = updated[0]
                            # Merge updates for PDF generation
                            updated_contract.update(update_payload)
                    except Exception as e:
                        pass

        # ── STEP 2: Generate updated contract PDF ──
        pdf_download_url = None
        if updated_contract:
            try:
                pdf_b64 = generate_contract_pdf(updated_contract, req.case_id)
                pdf_download_url = f"data:application/pdf;base64,{pdf_b64}"
            except Exception as e:
                pass

        # ── STEP 3: Log to sap_updates ──
        sap = {
            "case_id": req.case_id,
            "request_type": case.get("request_type"),
            "record_id": record_id,
            "customer_name": summary.get("customer_name"),
            "change_type": summary.get("change_type"),
            "change_details": change_details,
            "approved_by": req.ops_user,
            "approved_at": datetime.utcnow().isoformat(),
            "sap_status": "success" if db_updated else "simulated_success",
            "sap_message": f"DB updated: {', '.join(f'{k}={v}' for k,v in update_payload.items())}" if update_payload else f"SAP simulated — {summary.get('change_type')} on {record_id}"
        }
        try: db_post("sap_updates", sap)
        except: pass
        try: db_patch("agent_cases", "case_id", req.case_id, {"status": "approved_sap_updated"})
        except: pass

        return {
            "status": "ok",
            "message": f"{'DB updated + ' if db_updated else ''}SAP logged. {summary.get('change_type')} applied to {record_id}.",
            "sap_record": sap,
            "db_updated": db_updated,
            "update_payload": update_payload,
            "pdf_download_url": pdf_download_url
        }
    
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

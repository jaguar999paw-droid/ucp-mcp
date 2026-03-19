"""
ucp_backend.py — FastAPI app exposing all UCP-compliant REST endpoints for KituDigital.

Endpoints:
  GET  /.well-known/ucp               — business profile (capability advertisement)
  GET  /ucp/products/search           — product discovery
  GET  /ucp/products/{id}             — single product detail
  POST /ucp/checkout/sessions         — create checkout session
  GET  /ucp/checkout/sessions/{sid}   — get session state
  PUT  /ucp/checkout/sessions/{sid}   — update session (qty / coupon)
  POST /ucp/checkout/sessions/{sid}/complete  — finalise order
  GET  /ucp/orders/{oid}              — order status (post-purchase)
  POST /ucp/orders/{oid}/cancel       — cancel order

Run:  uvicorn ucp_backend:app --host 0.0.0.0 --port 8100 --reload
"""

import json, uuid, hashlib, hmac, os, logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ucp_backend")

app = FastAPI(title="KituDigital UCP Backend", version="1.0.0")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(BASE_DIR, "catalog.json")) as f:
    CATALOG: list[dict] = json.load(f)["products"]
CATALOG_IDX: dict[str, dict] = {p["id"]: p for p in CATALOG}

SESSIONS: dict[str, dict] = {}
ORDERS:   dict[str, dict] = {}
PAYMENT_SECRET = os.getenv("UCP_PAYMENT_SECRET", "kitudigital-dev-secret-2026")
COUPONS = {"KITU10": 0.10, "DEVDAY": 0.20, "WELCOME": 0.15}


class CartItem(BaseModel):
    product_id: str
    quantity: int = 1

class CreateSessionRequest(BaseModel):
    items: list[CartItem]
    buyer_email: Optional[str] = None
    coupon_code: Optional[str] = None

class UpdateSessionRequest(BaseModel):
    items: Optional[list[CartItem]] = None
    coupon_code: Optional[str] = None
    buyer_email: Optional[str] = None

class CompleteSessionRequest(BaseModel):
    payment_token: str
    billing_name: str
    billing_country: str = "KE"


def _calc_totals(items, coupon):
    subtotal, line_items = 0.0, []
    for item in items:
        p = CATALOG_IDX.get(item.product_id)
        if not p: raise HTTPException(404, f"Product {item.product_id} not found")
        if not p["in_stock"]: raise HTTPException(409, f"Product {item.product_id} out of stock")
        lp = round(p["price"] * item.quantity, 2)
        subtotal += lp
        line_items.append({"product_id": item.product_id, "name": p["name"],
                            "unit_price": p["price"], "quantity": item.quantity, "line_total": lp})
    discount = round(subtotal * COUPONS.get((coupon or "").upper(), 0), 2)
    return {"line_items": line_items, "subtotal": subtotal,
            "discount": discount, "total": round(subtotal - discount, 2), "currency": "USD"}

def _verify_token(token, sid):
    exp = hmac.new(PAYMENT_SECRET.encode(), sid.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(token, exp)

def _ts(): return datetime.now(timezone.utc).isoformat()


@app.get("/.well-known/ucp")
async def business_profile(request: Request):
    base = str(request.base_url).rstrip("/")
    return {
        "ucp_version": "1.0", "merchant_id": "kitudigital-ke-001",
        "display_name": "KituDigital",
        "description": "Digital goods marketplace — developer tools, study packs, design assets.",
        "country": "KE", "currency": "USD", "services": ["shopping"],
        "capabilities": ["product_discovery", "checkout", "order_status", "order_cancel", "coupons"],
        "endpoints": {
            "product_search":     f"{base}/ucp/products/search",
            "product_detail":     f"{base}/ucp/products/{{id}}",
            "checkout_create":    f"{base}/ucp/checkout/sessions",
            "checkout_get":       f"{base}/ucp/checkout/sessions/{{sid}}",
            "checkout_update":    f"{base}/ucp/checkout/sessions/{{sid}}",
            "checkout_complete":  f"{base}/ucp/checkout/sessions/{{sid}}/complete",
            "order_status":       f"{base}/ucp/orders/{{oid}}",
            "order_cancel":       f"{base}/ucp/orders/{{oid}}/cancel",
        },
        "payment_handlers": ["stripe", "mpesa", "paypal"],
        "transport": ["rest", "mcp"], "contact": "api@kitudigital.ke",
    }

@app.get("/ucp/products/search")
async def search_products(q: Optional[str]=None, category: Optional[str]=None,
                          max_price: Optional[float]=None, tag: Optional[str]=None, limit: int=10):
    r = CATALOG[:]
    if q:         ql=q.lower(); r=[p for p in r if ql in p["name"].lower() or ql in p["description"].lower()]
    if category:  r=[p for p in r if p["category"]==category]
    if max_price: r=[p for p in r if p["price"]<=max_price]
    if tag:       r=[p for p in r if tag.lower() in p["tags"]]
    return {"count": len(r[:limit]), "products": r[:limit]}

@app.get("/ucp/products/{product_id}")
async def get_product(product_id: str):
    p = CATALOG_IDX.get(product_id)
    if not p: raise HTTPException(404, "Product not found")
    return p

@app.post("/ucp/checkout/sessions", status_code=201)
async def create_session(body: CreateSessionRequest):
    sid = f"sess_{uuid.uuid4().hex[:16]}"
    totals = _calc_totals(body.items, body.coupon_code)
    sess = {"session_id": sid, "status": "pending",
            "items": [i.model_dump() for i in body.items],
            "buyer_email": body.buyer_email, "coupon_code": body.coupon_code,
            **totals, "created_at": _ts(), "updated_at": _ts(),
            "continue_url": None, "order_id": None}
    SESSIONS[sid] = sess
    log.info("Session created: %s  total=%.2f", sid, totals["total"])
    return sess

@app.get("/ucp/checkout/sessions/{session_id}")
async def get_session(session_id: str):
    s = SESSIONS.get(session_id)
    if not s: raise HTTPException(404, "Session not found")
    return s

@app.put("/ucp/checkout/sessions/{session_id}")
async def update_session(session_id: str, body: UpdateSessionRequest):
    s = SESSIONS.get(session_id)
    if not s: raise HTTPException(404, "Session not found")
    if s["status"] != "pending": raise HTTPException(409, f"Cannot update '{s['status']}' session")
    if body.items is not None: s["items"] = [i.model_dump() for i in body.items]
    if body.coupon_code is not None: s["coupon_code"] = body.coupon_code
    if body.buyer_email is not None: s["buyer_email"] = body.buyer_email
    s.update(_calc_totals([CartItem(**i) for i in s["items"]], s["coupon_code"]))
    s["updated_at"] = _ts()
    return s

@app.post("/ucp/checkout/sessions/{session_id}/complete")
async def complete_session(session_id: str, body: CompleteSessionRequest):
    s = SESSIONS.get(session_id)
    if not s: raise HTTPException(404, "Session not found")
    if s["status"] != "pending": raise HTTPException(409, f"Session already '{s['status']}'")
    if not s.get("buyer_email"):
        s["continue_url"] = f"/checkout/email?session={session_id}"
        s["status"] = "needs_input"
        return JSONResponse(202, {"status": "needs_input", "reason": "buyer_email_required",
            "continue_url": s["continue_url"],
            "message": "Add buyer_email via PUT then retry."})
    if not _verify_token(body.payment_token, session_id):
        raise HTTPException(402, "Payment mandate verification failed")
    oid = f"ord_{uuid.uuid4().hex[:12]}"
    order = {"order_id": oid, "session_id": session_id, "status": "confirmed",
             "buyer_email": s["buyer_email"], "billing_name": body.billing_name,
             "billing_country": body.billing_country, "line_items": s["line_items"],
             "subtotal": s["subtotal"], "discount": s["discount"],
             "total": s["total"], "currency": s["currency"],
             "coupon_code": s.get("coupon_code"), "created_at": _ts(),
             "download_links": {i["product_id"]: CATALOG_IDX[i["product_id"]]["download_url"]
                                for i in s["line_items"] if i["product_id"] in CATALOG_IDX}}
    ORDERS[oid] = order
    s.update({"status": "completed", "order_id": oid, "updated_at": _ts()})
    log.info("Order confirmed: %s  total=%.2f", oid, order["total"])
    return order

@app.get("/ucp/orders/{order_id}")
async def get_order(order_id: str):
    o = ORDERS.get(order_id)
    if not o: raise HTTPException(404, "Order not found")
    return o

@app.post("/ucp/orders/{order_id}/cancel")
async def cancel_order(order_id: str):
    o = ORDERS.get(order_id)
    if not o: raise HTTPException(404, "Order not found")
    if o["status"] == "cancelled": return {"message": "Already cancelled", "order_id": order_id}
    if o["status"] == "delivered": raise HTTPException(409, "Cannot cancel delivered order")
    o.update({"status": "cancelled", "cancelled_at": _ts()})
    log.info("Order cancelled: %s", order_id)
    return {"message": "Order cancelled", "order_id": order_id, "status": "cancelled"}

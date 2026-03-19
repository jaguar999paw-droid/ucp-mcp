"""
ucp-mcp server.py — FastMCP server wrapping KituDigital's UCP REST backend.
Exposes 10 MCP tools covering the full agentic commerce lifecycle.

Tools: ucp_business_profile, ucp_search_products, ucp_get_product,
       ucp_create_session, ucp_get_session, ucp_update_session,
       ucp_complete_checkout, ucp_get_order, ucp_cancel_order,
       ucp_generate_token
"""

import hashlib, hmac, json, logging, os, sys
from typing import Optional
import httpx
from mcp.server.fastmcp import FastMCP

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
os.makedirs(os.path.join(BASE_DIR, "logs"), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s ucp-mcp %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stderr),
              logging.FileHandler(os.path.join(BASE_DIR, "logs", "server.log"), encoding="utf-8")],
)
log = logging.getLogger("ucp_mcp")

mcp = FastMCP("ucp-mcp")
UCP_BASE       = os.getenv("UCP_BASE_URL",        "http://localhost:8100")
PAYMENT_SECRET = os.getenv("UCP_PAYMENT_SECRET",  "kitudigital-dev-secret-2026")


async def _get(path, **params):
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"{UCP_BASE}{path}", params={k:v for k,v in params.items() if v is not None})
        r.raise_for_status(); return r.json()

async def _post(path, body):
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(f"{UCP_BASE}{path}", json=body); r.raise_for_status(); return r.json()

async def _put(path, body):
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.put(f"{UCP_BASE}{path}", json=body); r.raise_for_status(); return r.json()

def _fmt(d): return json.dumps(d, indent=2)


@mcp.tool()
async def ucp_business_profile() -> str:
    """Fetch KituDigital's UCP business profile (/.well-known/ucp).
    Shows all capabilities, endpoints, payment handlers, and transports.
    Call this first to discover what the merchant supports."""
    return _fmt(await _get("/.well-known/ucp"))


@mcp.tool()
async def ucp_search_products(
    query: Optional[str] = None,
    category: Optional[str] = None,
    max_price: Optional[float] = None,
    tag: Optional[str] = None,
    limit: int = 10,
) -> str:
    """Search KituDigital product catalog.
    category options: developer-tools | study-guides | cybersecurity | design-assets
    tag examples: ctf, docker, figma, mcp, ubuntu"""
    return _fmt(await _get("/ucp/products/search", q=query, category=category,
                            max_price=max_price, tag=tag, limit=limit))


@mcp.tool()
async def ucp_get_product(product_id: str) -> str:
    """Fetch full detail for a single product by ID (e.g. 'kitu-003')."""
    return _fmt(await _get(f"/ucp/products/{product_id}"))


@mcp.tool()
async def ucp_create_session(items: str, buyer_email: Optional[str]=None,
                              coupon_code: Optional[str]=None) -> str:
    """Create a UCP checkout session.
    items: JSON array e.g. '[{"product_id":"kitu-003","quantity":1}]'
    coupon_code: KITU10 (10%), DEVDAY (20%), WELCOME (15%)
    Returns session_id — keep it for all subsequent calls."""
    return _fmt(await _post("/ucp/checkout/sessions",
                            {"items": json.loads(items), "buyer_email": buyer_email,
                             "coupon_code": coupon_code}))


@mcp.tool()
async def ucp_get_session(session_id: str) -> str:
    """Get state of a checkout session. Shows status, totals, continue_url if human input needed."""
    return _fmt(await _get(f"/ucp/checkout/sessions/{session_id}"))


@mcp.tool()
async def ucp_update_session(session_id: str, items: Optional[str]=None,
                              coupon_code: Optional[str]=None, buyer_email: Optional[str]=None) -> str:
    """Update a pending session — change items, apply coupon, or add buyer_email.
    buyer_email is required before completing checkout."""
    body = {}
    if items       is not None: body["items"]       = json.loads(items)
    if coupon_code is not None: body["coupon_code"] = coupon_code
    if buyer_email is not None: body["buyer_email"] = buyer_email
    return _fmt(await _put(f"/ucp/checkout/sessions/{session_id}", body))


@mcp.tool()
async def ucp_complete_checkout(session_id: str, payment_token: str,
                                 billing_name: str, billing_country: str="KE") -> str:
    """Submit AP2 payment mandate and finalise the order.
    If buyer_email missing, returns needs_input + continue_url — add email then retry.
    Use ucp_generate_token(session_id) to get a dev-mode token for testing."""
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(f"{UCP_BASE}/ucp/checkout/sessions/{session_id}/complete",
                         json={"payment_token": payment_token,
                               "billing_name": billing_name,
                               "billing_country": billing_country})
        return _fmt(r.json())


@mcp.tool()
async def ucp_get_order(order_id: str) -> str:
    """Fetch confirmed order status + download_links for each product."""
    return _fmt(await _get(f"/ucp/orders/{order_id}"))


@mcp.tool()
async def ucp_cancel_order(order_id: str) -> str:
    """Cancel a confirmed order (cannot cancel delivered orders)."""
    return _fmt(await _post(f"/ucp/orders/{order_id}/cancel", {}))


@mcp.tool()
async def ucp_generate_token(session_id: str) -> str:
    """Generate a dev-mode AP2 payment token for testing. NOT for production use."""
    token = hmac.new(PAYMENT_SECRET.encode(), session_id.encode(), hashlib.sha256).hexdigest()
    return json.dumps({"session_id": session_id, "payment_token": token,
                       "note": "dev-mode only — replace with real AP2 mandate in production"})


if __name__ == "__main__":
    log.info("Starting ucp-mcp server (stdio)...")
    mcp.run(transport="stdio")

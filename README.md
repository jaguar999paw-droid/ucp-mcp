# ucp-mcp

**KituDigital** — UCP (Universal Commerce Protocol) backend + FastMCP server.  
Agentic digital goods checkout for Claude and other AI agents.

## What's inside

| File | Purpose |
|---|---|
| `ucp_backend.py` | FastAPI app — 9 fully UCP-compliant REST endpoints |
| `server.py` | FastMCP server — 10 Claude-callable tools wrapping the backend |
| `catalog.json` | Product catalog — 6 digital goods (dev tools, CTF bundles, study packs) |
| `docker-compose.yml` | Runs the FastAPI backend on port 8100 |
| `requirements.txt` | Python deps |
| `setup.sh` | One-shot bootstrap (venv + install) |

## Business: KituDigital

A Kenya-based digital goods marketplace. Zero inventory, instant downloads, agentic-first.

**Products:**
- `kitu-001` Kenya Developer Starter Pack — $4.99
- `kitu-002` University CS Exam Study Pack — $3.49
- `kitu-003` CTF Quickstart Bundle — $5.99
- `kitu-004` Self-Hosted Infrastructure Playbook — $7.99
- `kitu-005` UI Design Starter Kit (Figma + SVG) — $6.49
- `kitu-006` MCP Server Development Guide — $9.99

**Coupons:** `KITU10` (10%), `DEVDAY` (20%), `WELCOME` (15%)

## Quick start

```bash
# 1 — clone and bootstrap
git clone https://github.com/karanjaofficial25flow-hue/ucp-mcp.git
cd ~/MCP/ucp-mcp
chmod +x setup.sh && ./setup.sh

# 2 — start the UCP backend
docker compose up -d

# 3 — verify
curl http://localhost:8100/.well-known/ucp | python3 -m json.tool

# 4 — restart Claude Desktop to activate the MCP server
```

## MCP tools exposed to Claude

| Tool | What it does |
|---|---|
| `ucp_business_profile` | Fetch /.well-known/ucp — capabilities + endpoints |
| `ucp_search_products` | Discover products with text/category/price/tag filters |
| `ucp_get_product` | Single product detail |
| `ucp_create_session` | Open a checkout session |
| `ucp_get_session` | Read session state |
| `ucp_update_session` | Change items / apply coupon / add email |
| `ucp_complete_checkout` | Submit AP2 payment mandate → confirm order |
| `ucp_get_order` | Order status + download links |
| `ucp_cancel_order` | Cancel an order |
| `ucp_generate_token` | Dev-mode AP2 payment token for testing |

## UCP endpoints

```
GET  /.well-known/ucp
GET  /ucp/products/search
GET  /ucp/products/{id}
POST /ucp/checkout/sessions
GET  /ucp/checkout/sessions/{sid}
PUT  /ucp/checkout/sessions/{sid}
POST /ucp/checkout/sessions/{sid}/complete
GET  /ucp/orders/{oid}
POST /ucp/orders/{oid}/cancel
```

## Claude Desktop config entry

Already written to `~/.config/claude/claude_desktop_config.json` and
`~/.config/Claude/claude_desktop_config.json` by the setup process.

```json
"ucp-mcp": {
  "command": "/home/kamau/MCP/ucp-mcp/venv/bin/python",
  "args": ["/path/to/MCP/ucp-mcp/server.py"],
  "env": {
    "UCP_BASE_URL": "http://localhost:8100",
    "UCP_PAYMENT_SECRET": "kitudigital-dev-secret-2026"
  }
}
```

## Protocol compatibility

UCP is interoperable with MCP, A2A, and AP2. This server uses MCP as the transport binding,
with REST as the underlying backend protocol — exactly the architecture described in the
[UCP spec](https://github.com/Universal-Commerce-Protocol/ucp).

## License

MIT

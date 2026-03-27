"""
White Horse — x402 Payment Layer v3 (CDP auth)
"""

import os, time, uuid, logging
import jwt
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

log = logging.getLogger("payments")

PAY_TO           = os.getenv("PAYMENT_WALLET",   "0x7E37015a806FF05d6ab3de50F6D0e8765d38C72D")
ORDER_PRICE      # Stop old white-horse, start new proxy
/home/brack/.npm-global/bin/pm2 stop white-horse
/home/brack/.npm-global/bin/pm2 start /home/brack/white-horse/server.js --name white-horse --node-args="--env-file=/home/brack/white-horse/.env"
/home/brack/.npm-global/bin/pm2 save= os.getenv("ORDER_PRICE",       "$0.01")
TABLE_PRICE      = os.getenv("TABLE_PRICE",       "$0.01")
NETWORK          = os.getenv("PAYMENT_NETWORK",   "eip155:8453")
PAYMENTS_ENABLED = os.getenv("PAYMENTS_ENABLED",  "true").lower() == "true"

CDP_KEY_NAME    = os.getenv("CDP_API_KEY_NAME",    "")
CDP_PRIVATE_KEY = os.getenv("CDP_API_KEY_PRIVATE_KEY", "").replace("\\n", "\n")
CDP_FACILITATOR = "https://api.cdp.coinbase.com/platform/v2/x402"

GATED_ROUTES = {
    "/order":                  ORDER_PRICE,
    "/table/{table_id}/order": TABLE_PRICE,
}


def _make_cdp_jwt(path: str) -> str:
    key = load_pem_private_key(CDP_PRIVATE_KEY.encode(), password=None)
    now = int(time.time())
    claims = {
        "sub": CDP_KEY_NAME,
        "iss": "cdp",
        "nbf": now,
        "exp": now + 60,
        "uris": [f"POST {path}"],
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(claims, key, algorithm="ES256",
                      headers={"kid": CDP_KEY_NAME, "nonce": uuid.uuid4().hex})


def _cdp_headers() -> dict:
    """Return auth headers for all three facilitator endpoints."""
    return {
        "verify":    {"Authorization": f"Bearer {_make_cdp_jwt('/platform/v2/x402/verify')}"},
        "settle":    {"Authorization": f"Bearer {_make_cdp_jwt('/platform/v2/x402/settle')}"},
        "supported": {"Authorization": f"Bearer {_make_cdp_jwt('/platform/v2/x402/supported')}"},
    }


class StarletteHTTPAdapter:
    def __init__(self, request: Request):
        self._request = request
    def get_path(self):              return self._request.url.path
    def get_method(self):            return self._request.method
    def get_header(self, name):      return self._request.headers.get(name)
    def get_accept_header(self):     return self._request.headers.get("accept", "")
    def get_body(self):              return None
    def get_query_param(self, name): return self._request.query_params.get(name)
    def get_query_params(self):      return dict(self._request.query_params)
    def get_url(self):               return str(self._request.url)


def _match_route(path: str):
    for pattern, price in GATED_ROUTES.items():
        if "{" not in pattern:
            if path == pattern:
                return price
        else:
            prefix = pattern.split("{")[0].rstrip("/")
            suffix = pattern.split("}")[1] if "}" in pattern else ""
            if path.startswith(prefix) and path.endswith(suffix):
                return price
    return None


def build_payment_app(fastapi_app):
    if not PAYMENTS_ENABLED:
        log.info("[PAYMENTS] Disabled")
        return fastapi_app

    try:
        from x402.http import (
            x402HTTPResourceServer, HTTPFacilitatorClient, FacilitatorConfig,
            RouteConfig, PaymentOption, HTTPRequestContext, CreateHeadersAuthProvider,
        )
        from x402 import x402ResourceServer
        from x402.mechanisms.evm.exact import ExactEvmServerScheme
    except ImportError as e:
        log.error(f"[PAYMENTS] Import failed: {e}")
        return fastapi_app

    auth      = CreateHeadersAuthProvider(create_headers=_cdp_headers)
    config    = FacilitatorConfig(url=CDP_FACILITATOR, auth_provider=auth)
    facilitator     = HTTPFacilitatorClient(config)
    resource_server = x402ResourceServer(facilitator)
    resource_server.register(NETWORK, ExactEvmServerScheme())

    routes = {
        "/order": RouteConfig(accepts=PaymentOption(
            scheme="exact", pay_to=PAY_TO, price=ORDER_PRICE, network=NETWORK
        )),
        "/table/{table_id}/order": RouteConfig(accepts=PaymentOption(
            scheme="exact", pay_to=PAY_TO, price=TABLE_PRICE, network=NETWORK
        )),
    }

    http_server = x402HTTPResourceServer(resource_server, routes)

    class X402Middleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            path = request.url.path.replace("/pub", "", 1)
            if request.method != "POST" or _match_route(path) is None:
                return await call_next(request)
            payment_header = request.headers.get("X-PAYMENT")
            adapter = StarletteHTTPAdapter(request)
            context = HTTPRequestContext(
                adapter=adapter, path=path,
                method=request.method, payment_header=payment_header,
            )
            result = await http_server.process_http_request(context)
            if result.type == "no-payment-required":
                return await call_next(request)
            resp = result.response
            if resp:
                return JSONResponse(
                    status_code=resp.status,
                    content=resp.body,
                    headers=dict(resp.headers or {}),
                )
            return await call_next(request)

    fastapi_app.add_middleware(X402Middleware)
    log.info(f"[PAYMENTS] CDP auth enabled — {PAY_TO} | {NETWORK}")
    return fastapi_app

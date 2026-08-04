"""REST endpoints. Everything that isn't a live push (see ws.py) lives
here: reading/writing settings and the panic-button flatten-all. Matches
dashboard/app.js's two REST calls exactly -- PUT /api/settings and
POST /api/flatten-all -- plus a few read endpoints useful outside the
dashboard (curl/scripts/monitoring)."""

from fastapi import APIRouter, Request

from . import serialize

router = APIRouter(prefix="/api")


@router.get("/settings")
async def get_settings(request: Request):
    state = request.app.state.app_state
    return state.get_settings().to_dict()


@router.put("/settings")
async def put_settings(request: Request):
    state = request.app.state.app_state
    body = await request.json()
    updated = state.update_settings(body)
    await state.broadcast_settings()
    return updated.to_dict()


@router.post("/flatten-all")
async def flatten_all(request: Request):
    state = request.app.state.app_state
    results = state.broker.flatten_all()
    await state.broadcast_full_state()
    watermark = state._order_log_watermark
    state._order_log_watermark = await state.broadcast_new_orders(watermark)
    return [
        {
            "client_order_id": r.client_order_id,
            "broker_order_id": r.broker_order_id,
            "status": r.status.value,
            "filled_quantity": r.filled_quantity,
            "avg_fill_price": r.avg_fill_price,
            "reason": r.reason,
        }
        for r in results
    ]


@router.get("/account")
async def get_account(request: Request):
    state = request.app.state.app_state
    return serialize.account_to_dict(state.broker.get_account_summary())


@router.get("/positions")
async def get_positions(request: Request):
    state = request.app.state.app_state
    return {s: serialize.position_to_dict(p) for s, p in state.broker.get_positions().items()}


@router.get("/orders")
async def get_orders(request: Request):
    state = request.app.state.app_state
    return list(getattr(state.broker, "order_log_entries", []))[-200:]


@router.get("/status")
async def get_status(request: Request):
    state = request.app.state.app_state
    return {
        "connection_state": state.broker.connection_state.value,
        "account_mode": state.get_settings().account_mode,
    }

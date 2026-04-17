"""Stock media API routes — search + download."""

import logging
import uuid
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from modules.review_engine.exceptions import StockMediaError

logger = logging.getLogger(__name__)


def _error_response(message, code, status=400):
    return jsonify({
        "success": False, "error": code, "message": message,
        "code": status, "timestamp": datetime.now(timezone.utc).isoformat(),
        "trace_id": uuid.uuid4().hex[:16],
    }), status


def _ok(data, status=200):
    return jsonify({"success": True, **data}), status


def create_stock_blueprint(*, jobs_getter):
    bp = Blueprint("stock_api", __name__)

    @bp.route("/api/stock/search", methods=["GET"])
    def stock_search():
        query = request.args.get("q", "").strip()
        if not query:
            return _error_response("Query parameter 'q' required", "MISSING_PARAM", 400)

        try:
            from modules.review_engine.stock_media import search_stock
            results = search_stock(
                query,
                orientation=request.args.get("orientation", ""),
                per_page=int(request.args.get("per_page", 15)),
            )
            return _ok({
                "results": [
                    {
                        "id": r.id, "url": r.url, "preview_url": r.preview_url,
                        "duration": r.duration, "photographer": r.photographer,
                        "width": r.width, "height": r.height,
                    }
                    for r in results
                ],
                "total": len(results),
            })
        except StockMediaError as e:
            return _error_response(str(e), "STOCK_SEARCH_FAILED", 400)

    @bp.route("/api/stock/download", methods=["POST"])
    def stock_download():
        # Round-15 finding H2: previously this endpoint created a
        # job record with status="queued" but no worker was scheduled,
        # so clients polling GET /api/job/<id> waited forever. Return
        # 501 Not Implemented to surface the gap rather than silently
        # dead-stub. Wiring to a real worker is v0.19.0 WISHLIST item E2.
        return _error_response(
            "stock download is not yet implemented in this build",
            "NOT_IMPLEMENTED",
            501,
        )

    return bp

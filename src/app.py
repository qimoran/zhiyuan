from __future__ import annotations

import os

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from src.common.config import get_app_config
from src.common.exceptions import AppError
from src.common.logger import get_logger, setup_logging
from src.common.response import error_response
from src.common.trace import clear_trace_id, get_trace_id, set_trace_id
from src.web.api_routes import api_bp
from src.web.routes import web_bp

logger = get_logger("app")


def create_app() -> Flask:
    """创建 Flask 应用。"""
    setup_logging()
    app = Flask(__name__)
    app.secret_key = os.getenv("APP_SECRET_KEY") or os.getenv("SECRET_KEY") or "zhiyuan-dev-secret"
    app.register_blueprint(api_bp)
    app.register_blueprint(web_bp)

    @app.before_request
    def before_request() -> None:
        trace_id = request.headers.get("X-Trace-Id")
        set_trace_id(trace_id)

    @app.after_request
    def after_request(response):
        response.headers["X-Trace-Id"] = get_trace_id()
        clear_trace_id()
        return response

    @app.errorhandler(AppError)
    def handle_app_error(error: AppError):
        logger.warning("业务异常：%s", error.message)
        return jsonify(error_response(error.code, error.message)), 400

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException):
        logger.warning("HTTP异常：%s %s", error.code, error.description)
        return jsonify(error_response(error.code or 500, error.description)), error.code or 500

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        logger.exception("未处理异常：%s", error)
        return jsonify(error_response(50000, "系统异常，请稍后重试")), 500

    return app


app = create_app()


if __name__ == "__main__":
    config = get_app_config()
    app.run(host=config.host, port=config.port, debug=config.debug)

from __future__ import annotations

from flask import Flask, jsonify, request

from src.common.config import get_app_config
from src.common.database import ping_database
from src.common.exceptions import AppError
from src.common.logger import get_logger, setup_logging
from src.common.response import error_response, success_response
from src.common.trace import clear_trace_id, set_trace_id

logger = get_logger("app")


def create_app() -> Flask:
    """创建 Flask 应用。"""
    setup_logging()
    app = Flask(__name__)

    @app.before_request
    def before_request() -> None:
        trace_id = request.headers.get("X-Trace-Id")
        set_trace_id(trace_id)

    @app.after_request
    def after_request(response):
        response.headers["X-Trace-Id"] = success_response().get("trace_id", "-")
        clear_trace_id()
        return response

    @app.get("/api/health")
    def health_check():
        """系统健康检查接口。"""
        database_ok = False
        try:
            database_ok = ping_database()
        except Exception as exc:
            logger.warning("数据库健康检查失败：%s", exc)

        return jsonify(
            success_response(
                {
                    "status": "ok",
                    "database": "ok" if database_ok else "unavailable",
                }
            )
        )

    @app.errorhandler(AppError)
    def handle_app_error(error: AppError):
        logger.warning("业务异常：%s", error.message)
        return jsonify(error_response(error.code, error.message)), 400

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        logger.exception("未处理异常：%s", error)
        return jsonify(error_response(50000, "系统异常，请稍后重试")), 500

    return app


app = create_app()


if __name__ == "__main__":
    config = get_app_config()
    app.run(host=config.host, port=config.port, debug=config.debug)

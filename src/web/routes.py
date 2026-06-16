"""S08 基础页面路由。

第一版只提供轻量入口页，完整前端交互留到 S11。
"""

from __future__ import annotations

from flask import Blueprint, redirect, render_template_string, url_for

web_bp = Blueprint("web", __name__)


@web_bp.get("/")
def index():
    return render_template_string(
        """
        <!doctype html>
        <html lang="zh-CN">
        <head>
          <meta charset="utf-8">
          <title>考研择校推荐系统</title>
          <style>
            body { font-family: Arial, "Microsoft YaHei", sans-serif; margin: 40px; line-height: 1.7; }
            a { color: #0f766e; display: block; margin: 8px 0; }
          </style>
        </head>
        <body>
          <h1>考研择校推荐系统</h1>
          <p>S08 基础 API 已接入，完整页面交互将在 S11 完成。</p>
          <a href="/api/health">/api/health</a>
          <a href="/api/university/list">/api/university/list</a>
          <a href="/api/major/list">/api/major/list</a>
          <a href="/api/source/list">/api/source/list</a>
        </body>
        </html>
        """
    )


@web_bp.get("/universities")
def universities_page():
    return redirect(url_for("api.university_list"))


@web_bp.get("/majors")
def majors_page():
    return redirect(url_for("api.major_list"))


@web_bp.get("/sources")
def sources_page():
    return redirect(url_for("api.source_list"))

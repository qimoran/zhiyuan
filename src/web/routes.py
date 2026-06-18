"""S11 Web 页面路由。"""

from __future__ import annotations

from flask import Blueprint, Response, redirect, render_template, url_for

web_bp = Blueprint("web", __name__)


@web_bp.get("/")
def index():
    return render_template("index.html", active_page="index", page_title="首页")


@web_bp.get("/recommend")
def recommend_page():
    return render_template("recommend.html", active_page="recommend", page_title="开始推荐")


@web_bp.get("/result")
def result_page():
    return render_template("result.html", active_page="recommend", page_title="推荐结果")


@web_bp.get("/universities")
def universities_page():
    return render_template("universities.html", active_page="universities", page_title="学校列表")


@web_bp.get("/majors")
def majors_page():
    return render_template("majors.html", active_page="majors", page_title="专业列表")


@web_bp.get("/charts")
def charts_page():
    return render_template("charts.html", active_page="charts", page_title="数据图表")


@web_bp.get("/report")
def report_page():
    return render_template("report.html", active_page="report", page_title="推荐报告")


@web_bp.get("/sources")
def sources_page():
    return redirect(url_for("api.source_list"))


@web_bp.get("/favicon.ico")
def favicon():
    return Response(status=204)

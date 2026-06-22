from __future__ import annotations

from src.app import create_app


def test_chart_api_contract(monkeypatch) -> None:
    app = create_app()
    app.testing = True
    from src.web import api_routes

    monkeypatch.setattr(
        api_routes,
        "get_university_type",
        lambda filters: {"x_axis": ["综合类"], "series": [{"name": "学校类型", "data": [1]}], "warnings": []},
    )
    response = app.test_client().get("/api/chart/university-type")
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["x_axis"] == ["综合类"]


def test_report_api_contract(monkeypatch) -> None:
    app = create_app()
    app.testing = True
    from src.web import api_routes

    monkeypatch.setattr(
        api_routes,
        "generate_report",
        lambda payload: {
            "report_id": 1,
            "report_type": "template",
            "report_content": "模板报告\n仅供参考，最终以官方招生政策和当年复试录取结果为准。",
            "warnings": [],
        },
    )
    response = app.test_client().post("/api/report/generate", json={"report_type": "template"})
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["report_type"] == "template"


def test_unknown_route_returns_404_json() -> None:
    app = create_app()
    app.testing = True
    response = app.test_client().get("/api/not-exists")
    payload = response.get_json()
    assert response.status_code == 404
    assert payload["code"] == 404

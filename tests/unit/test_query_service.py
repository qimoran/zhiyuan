from __future__ import annotations

from src.services import query_service


def test_list_universities_adds_validated_official_site(monkeypatch) -> None:
    def fake_fetch_all(sql: str, params: dict[str, object]) -> list[dict[str, object]]:
        assert "official_site" in sql
        assert params == {"limit": query_service.DEFAULT_LIMIT, "offset": 0}
        return [
            {
                "id": 1,
                "candidate_school_id": 252,
                "university_name": "重庆大学",
                "official_site": None,
            }
        ]

    monkeypatch.setattr(query_service, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(query_service, "fetch_one", lambda sql, params: {"total": 1})

    result = query_service.list_universities({})

    assert result["items"][0]["official_site"] == "https://yz.cqu.edu.cn/"


def test_list_universities_prefers_validated_official_site(monkeypatch) -> None:
    def fake_fetch_all(sql: str, params: dict[str, object]) -> list[dict[str, object]]:
        return [
            {
                "id": 2,
                "candidate_school_id": 252,
                "university_name": "重庆大学",
                "official_site": "https://graduate.cqu.edu.cn/",
            }
        ]

    monkeypatch.setattr(query_service, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(query_service, "fetch_one", lambda sql, params: {"total": 1})

    result = query_service.list_universities({})

    assert result["items"][0]["official_site"] == "https://yz.cqu.edu.cn/"

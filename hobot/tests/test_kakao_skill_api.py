import os
import sys
import types
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

neo4j_stub = types.ModuleType("neo4j")


class _StubGraphDatabase:
    @staticmethod
    def driver(*args, **kwargs):
        raise RuntimeError("Neo4j driver should not be used in unit tests")


neo4j_stub.GraphDatabase = _StubGraphDatabase
neo4j_stub.Driver = object
sys.modules.setdefault("neo4j", neo4j_stub)

from service.kakao.skill_api import router as kakao_skill_router


class _StubAnswer:
    def __init__(self):
        self.conclusion = "한국 부동산은 최근 거래량이 회복되는 흐름입니다."
        self.key_points = [
            "서울 주요 지역 거래량이 최근 3개월 기준 반등했습니다.",
            "금리 레벨이 높아 급격한 상승보다 완만한 회복이 우세합니다.",
        ]
        self.uncertainty = "정책 변수와 대출 규제 변화에 따라 변동성이 커질 수 있습니다."


class _StubCitation:
    def __init__(self, title: str):
        self.doc_title = title


class _StubGraphAnswerResponse:
    def __init__(self):
        self.answer = _StubAnswer()
        self.citations = [
            _StubCitation("KR Real Estate Monthly Summary"),
            _StubCitation("KR Real Estate Transactions"),
        ]


class TestKakaoSkillApi(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(kakao_skill_router, prefix="/api")
        self.client = TestClient(app)

    def test_kakao_skill_chatbot_returns_kakao_v2_payload(self):
        payload = {
            "userRequest": {
                "utterance": "한국 부동산 전망 알려줘",
                "user": {"id": "kakao-user-1"},
            },
            "action": {
                "clientExtra": {
                    "country_code": "KR",
                    "time_range": "90d",
                }
            },
        }

        with patch(
            "service.kakao.skill_api.generate_graph_rag_answer",
            return_value=_StubGraphAnswerResponse(),
        ) as mock_generate:
            response = self.client.post("/api/kakao/skill/chatbot", json=payload)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body.get("version"), "2.0")

        outputs = ((body.get("template") or {}).get("outputs") or [])
        self.assertTrue(outputs)
        text = str((((outputs[0] or {}).get("simpleText") or {}).get("text") or ""))
        self.assertIn("핵심 포인트", text)
        self.assertIn("근거", text)

        self.assertTrue(mock_generate.called)
        call_args = mock_generate.call_args.kwargs
        self.assertEqual(call_args.get("user_id"), "kakao:kakao-user-1")
        answer_request = call_args.get("request")
        if answer_request is None and mock_generate.call_args.args:
            answer_request = mock_generate.call_args.args[0]
        self.assertEqual(answer_request.country_code, "KR")
        self.assertEqual(answer_request.time_range, "90d")

    def test_kakao_skill_webhook_secret_guard(self):
        payload = {
            "userRequest": {
                "utterance": "테스트",
                "user": {"id": "kakao-user-2"},
            }
        }

        with patch.dict(os.environ, {"KAKAO_SKILL_WEBHOOK_SECRET": "secret-123"}, clear=False):
            forbidden = self.client.post("/api/kakao/skill/chatbot", json=payload)
            self.assertEqual(forbidden.status_code, 403)

            with patch(
                "service.kakao.skill_api.generate_graph_rag_answer",
                return_value=_StubGraphAnswerResponse(),
            ):
                allowed = self.client.post(
                    "/api/kakao/skill/chatbot",
                    json=payload,
                    headers={"X-Webhook-Secret": "secret-123"},
                )
            self.assertEqual(allowed.status_code, 200)


if __name__ == "__main__":
    unittest.main()

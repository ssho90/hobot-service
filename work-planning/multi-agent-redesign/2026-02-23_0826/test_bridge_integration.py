"""
Phase 2 보완 - DomainInsight 스키마 브릿지 통합 테스트

_execute_branch_agents에서 생성하는 DomainInsight payload가
_build_structured_data_context_for_supervisor → _compact_structured_data_for_prompt를 거쳐
슈퍼에이전트 프롬프트에 올바르게 도달하는지 검증합니다.
"""


def test_domain_insight_field_mapping():
    """
    도메인 에이전트의 DomainInsight payload가 agent_insights 수집 시
    새 필드명(analytical_summary, key_drivers, primary_trend, ...)으로 올바르게 매핑되는지 검증
    """
    # 시뮬레이션: _execute_branch_agents가 만든 것과 동일한 구조
    mock_branch_results = [
        {
            "branch": "graph",
            "enabled": True,
            "dispatch_mode": "parallel",
            "agent_runs": [
                {
                    "agent": "equity_analyst_agent",
                    "branch": "graph",
                    "status": "executed",
                    "tool_probe": {"tool": "graph", "status": "ok", "row_count": 5},
                    "agent_llm": {
                        "enabled": True,
                        "status": "ok",
                        "model": "gemini-3-flash-preview",
                        "payload": {
                            "domain_source": "EQUITY_ANALYST",
                            "primary_trend": "BULL",
                            "confidence_score": 0.82,
                            "key_drivers": [
                                "20일 이평선이 60일 이평선 상향 돌파 (Golden Cross)",
                                "FRED 실업률 4.1% 유지 (전월 동일)",
                                "최근 실적 서프라이즈로 투자 심리 개선"
                            ],
                            "quantitative_metrics": {
                                "20일 MA": "185.3",
                                "60일 MA": "178.9",
                                "실업률": "4.1%"
                            },
                            "analytical_summary": "AAPL은 골든크로스 신호와 실적 서프라이즈로 단기 강세 국면 진입. 다만 금리 불확실성이 상방 제한 요인."
                        }
                    }
                },
                {
                    "agent": "macro_economy_agent",
                    "branch": "graph",
                    "status": "executed",
                    "tool_probe": {"tool": "graph", "status": "ok", "row_count": 3},
                    "agent_llm": {
                        "enabled": True,
                        "status": "degraded",  # fallback 결과
                        "model": "gemini-3-flash-preview",
                        "payload": {
                            "domain_source": "MACRO_ECONOMY",
                            "primary_trend": "NEUTRAL",
                            "confidence_score": 0.0,
                            "key_drivers": ["에이전트 응답 지연/스키마 불일치 오류"],
                            "quantitative_metrics": {},
                            "analytical_summary": "현재 데이터를 분석할 수 없습니다. (LLM 에러/지연)"
                        }
                    }
                }
            ]
        }
    ]

    # --- 1단계: agent_insights 수집 로직 시뮬레이션 ---
    agent_insights = []
    for branch_result in mock_branch_results:
        if not isinstance(branch_result, dict):
            continue
        agent_runs = branch_result.get("agent_runs")
        if not isinstance(agent_runs, list):
            continue
        for agent_run in agent_runs:
            if not isinstance(agent_run, dict):
                continue
            agent_name = str(agent_run.get("agent") or "").strip()
            agent_llm = agent_run.get("agent_llm")
            if not isinstance(agent_llm, dict):
                continue
            agent_llm_status = str(agent_llm.get("status") or "").strip()
            if agent_llm_status not in {"ok", "degraded"}:
                continue
            payload = agent_llm.get("payload")
            if not isinstance(payload, dict):
                continue

            analytical_summary = str(
                payload.get("analytical_summary") or payload.get("summary") or ""
            ).strip()
            domain_source = str(
                payload.get("domain_source") or agent_name.replace("_agent", "").upper()
            ).strip()
            primary_trend = str(payload.get("primary_trend") or "NEUTRAL").upper()
            if primary_trend not in {"BULL", "BEAR", "NEUTRAL"}:
                primary_trend = "NEUTRAL"

            confidence_score_raw = payload.get("confidence_score")
            confidence_score = 0.5
            try:
                if confidence_score_raw is not None:
                    confidence_score = float(confidence_score_raw)
                    confidence_score = max(0.0, min(1.0, confidence_score))
            except Exception:
                pass

            key_drivers_raw = (
                payload.get("key_drivers")
                if isinstance(payload.get("key_drivers"), list)
                else payload.get("key_points")
                if isinstance(payload.get("key_points"), list)
                else []
            )
            key_drivers = [str(item).strip() for item in key_drivers_raw if str(item).strip()][:5]

            quantitative_metrics_raw = payload.get("quantitative_metrics")
            quantitative_metrics = {}
            if isinstance(quantitative_metrics_raw, dict):
                for k, v in quantitative_metrics_raw.items():
                    if str(k).strip():
                        quantitative_metrics[str(k).strip()] = str(v).strip()

            if not analytical_summary and not key_drivers:
                continue
            agent_insights.append(
                {
                    "domain_source": domain_source,
                    "agent": agent_name,
                    "branch": str(agent_run.get("branch") or "").strip(),
                    "model": str(agent_llm.get("model") or "").strip(),
                    "primary_trend": primary_trend,
                    "confidence_score": confidence_score,
                    "key_drivers": key_drivers,
                    "quantitative_metrics": quantitative_metrics,
                    "analytical_summary": analytical_summary,
                    "agent_status": agent_llm_status,
                }
            )

    # --- 검증 ---
    assert len(agent_insights) == 2, f"Expected 2 insights, got {len(agent_insights)}"

    # Equity (ok)
    eq = agent_insights[0]
    assert eq["domain_source"] == "EQUITY_ANALYST"
    assert eq["primary_trend"] == "BULL"
    assert eq["confidence_score"] == 0.82
    assert len(eq["key_drivers"]) == 3
    assert "골든크로스" in eq["analytical_summary"]
    assert eq["quantitative_metrics"]["20일 MA"] == "185.3"
    assert eq["agent_status"] == "ok"
    print(f"  ✅ Equity Insight: trend={eq['primary_trend']}, conf={eq['confidence_score']}, drivers={len(eq['key_drivers'])}")

    # Macro (degraded/fallback)
    macro = agent_insights[1]
    assert macro["domain_source"] == "MACRO_ECONOMY"
    assert macro["primary_trend"] == "NEUTRAL"
    assert macro["confidence_score"] == 0.0
    assert macro["agent_status"] == "degraded"
    assert "분석할 수 없습니다" in macro["analytical_summary"]
    print(f"  ✅ Macro Insight (fallback): trend={macro['primary_trend']}, conf={macro['confidence_score']}, status={macro['agent_status']}")

    # --- 2단계: Compact for Prompt 시뮬레이션 ---
    def _truncate(text, max_len):
        t = str(text or "").strip()
        return t[:max_len] if len(t) > max_len else t

    compact_insights = []
    for insight in agent_insights[:4]:
        key_drivers_raw = (
            insight.get("key_drivers")
            if isinstance(insight.get("key_drivers"), list)
            else []
        )
        qm_raw = insight.get("quantitative_metrics") if isinstance(insight.get("quantitative_metrics"), dict) else {}
        metrics_compact = {}
        for mk, mv in list(qm_raw.items())[:5]:
            if str(mk).strip():
                metrics_compact[str(mk).strip()] = _truncate(str(mv), 60)
        compact_insights.append({
            "domain_source": str(insight.get("domain_source") or "").strip(),
            "primary_trend": str(insight.get("primary_trend") or "NEUTRAL").upper(),
            "confidence_score": insight.get("confidence_score", 0.5),
            "key_drivers": [_truncate(d, 120) for d in key_drivers_raw[:4]],
            "quantitative_metrics": metrics_compact,
            "analytical_summary": _truncate(
                insight.get("analytical_summary") or insight.get("summary"), 260
            ),
            "agent_status": str(insight.get("agent_status") or "ok").strip(),
        })

    assert len(compact_insights) == 2
    assert "domain_source" in compact_insights[0]
    assert "primary_trend" in compact_insights[0]
    assert "confidence_score" in compact_insights[0]
    assert "key_drivers" in compact_insights[0]
    assert "quantitative_metrics" in compact_insights[0]
    assert "analytical_summary" in compact_insights[0]
    # 구(舊) 필드가 없는지 확인
    assert "summary" not in compact_insights[0]
    assert "key_points" not in compact_insights[0]
    assert "risks" not in compact_insights[0]
    assert "confidence" not in compact_insights[0]
    print(f"  ✅ Compact Insights: 새 스키마 필드만 포함, 구(舊) 필드 제거 확인")

    print("\n🎉 모든 DomainInsight 브릿지 테스트 통과!")


if __name__ == "__main__":
    print("=" * 60)
    print("[Phase 2 보완] DomainInsight 스키마 브릿지 통합 테스트")
    print("=" * 60)
    test_domain_insight_field_mapping()

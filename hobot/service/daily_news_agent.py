from dotenv import load_dotenv
from langchain_tavily import TavilySearch
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import ToolMessage, HumanMessage
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages

load_dotenv(override=True)

# 1. 도구 정의
tavily_tool = TavilySearch(
    max_results=5,
    topic="news",
)

# 2. 상태 정의
class State(TypedDict):
    messages: Annotated[list, add_messages]

# 3. LLM + 도구 바인딩
llm = ChatOpenAI(model="gpt-4o-mini")
llm_with_tools = llm.bind_tools([tavily_tool])

# 4. 뉴스 요청 노드
def ask_news(state: State):
    return {
        "messages": [
            HumanMessage(content="""
Get the daily news on the following topics:
1. AI Technology (around 10 articles in total)
2. Blockchain Technology (around 10 articles in total)
3. Economy related to USA stock market and cryptocurrency. (around 10 articles in total)
4. USA economy, society, technology, war (around 10 articles in total, at least 2 article per topic)
5. Korean economy, society, technology (around 10 articles in total, at least 2 article per topic)
6. Other Technology (around 5 articles in total)
""")
        ]
    }

# 5. LLM 호출 (tool call 포함)
def call_llm(state: State):
    answer = llm_with_tools.invoke(state["messages"])
    return {"messages": [answer]}

# 6. tool 실행 노드
import json
def run_tool(state: State):
    message = state["messages"][-1]
    outputs = []
    for call in message.tool_calls:
        result = tavily_tool.invoke(call["args"])
        outputs.append(ToolMessage(
            content=json.dumps(result, ensure_ascii=False),
            name=call["name"],
            tool_call_id=call["id"]
        ))
    return {"messages": outputs}

# 7. 요약 노드
def summarize(state: State):
    summary = llm.invoke([
        *state["messages"],
        HumanMessage(content="""
Summarize the following news by category. 주어진 뉴스들 중 카테고리별로 중요하다고 생각되는 뉴스들을 5~8개씩 추려서 요약해줘.
1. AI Technology.
2. Blockchain Technology.
3. Economy related to USA stock market and cryptocurrency.
4. USA economy, society, technology, war.
5. Korean economy, society, technology.
6. Other Technology.

*Translate the summary into Korean. Don't include the English original text, only the Korean summary.
""")
    ])
    return {"messages": [summary]}

# 8. 그래프 연결
graph = StateGraph(State)
graph.add_node("ask_news", ask_news)
graph.add_node("call_llm", call_llm)
graph.add_node("run_tool", run_tool)
graph.add_node("summarize", summarize)

# 흐름 제어
def needs_tool(state: State):
    message = state["messages"][-1]
    return "run_tool" if hasattr(message, "tool_calls") and message.tool_calls else "summarize"

graph.add_conditional_edges("call_llm", needs_tool, {"run_tool": "run_tool", "summarize": "summarize"})
graph.add_edge("run_tool", "summarize")
graph.add_edge("summarize", END)
graph.add_edge(START, "ask_news")
graph.add_edge("ask_news", "call_llm")

compiled = graph.compile()

if __name__ == "__main__":
    # 실행
    # for step in compiled.stream({}, stream_mode="values"):
    #     for key, value in step.items():
    #         print(f"== {key} ==")
    #         print(value)

    final_state = compiled.invoke({})

    # 최종 상태(final_state)는 'messages' 키를 가진 딕셔너리입니다.
    # 이 키의 값인 리스트에서 마지막 항목이 최종 요약 AIMessage입니다.
    last_message = final_state['messages'][-1]

    # AIMessage 객체의 내용(content)만 출력합니다.
    print(last_message.content)
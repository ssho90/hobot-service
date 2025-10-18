from __future__ import annotations
from dotenv import load_dotenv

load_dotenv()

# 💬 기억 저장소 기반 LLM 멀티턴 챗봇 (Vector DB 없이)

from datetime import datetime
from typing import List
import openai

from datetime import datetime
from typing import TypedDict, List
import openai
import json
import os
import streamlit as st

# 설정
openai.api_key = os.getenv("OPENAI_API_KEY")
MEMORY_FILE = "memory_store.json"

# -----------------------------
# 타입 정의 (Python 3.11 스타일)
# -----------------------------
class Message(TypedDict):
    role: str
    content: str

class MemoryEntry(TypedDict):
    topic: str
    summary: str
    created_at: str

# -----------------------------
# 기억 저장소 (요약 기반 구조, 파일 저장)
# -----------------------------
class MemoryStore:
    def __init__(self, file_path: str = MEMORY_FILE):
        self.file_path = file_path
        self.memory: List[MemoryEntry] = self.load()

    def load(self) -> List[MemoryEntry]:
        if os.path.exists(self.file_path):
            with open(self.file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []

    def save_to_file(self) -> None:
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(self.memory, f, ensure_ascii=False, indent=2)

    def save(self, topic: str, summary: str) -> None:
        self.memory.append({
            "topic": topic,
            "summary": summary,
            "created_at": datetime.now().isoformat()
        })
        self.save_to_file()

    def recall(self, query: str) -> str:
        for mem in reversed(self.memory):
            if mem["topic"] in query or query in mem["summary"]:
                return mem["summary"]
        return ""

# -----------------------------
# GPT 호출 함수 (multi-turn 대응)
# -----------------------------
def gpt(messages: List[Message], temperature: float = 0.5) -> str:
    try:
        response = openai.chat.completions.create(
            model="gpt-4",
            messages=messages,
            temperature=temperature
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[오류] GPT 호출 실패: {e}"
    
def gpt_stream(messages: List[Message], temperature: float = 0.5):
    try:
        response = openai.chat.completions.create(
            model="gpt-4",
            messages=messages,
            temperature=temperature,
            stream=True  # ✅ 스트리밍 활성화
        )
        full_response = ""
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                yield content  # ✅ 한 토큰씩 yield
                full_response += content
        return full_response
    except Exception as e:
        yield f"[오류] GPT 호출 실패: {e}"

# -----------------------------
# 문장 요약 함수
# -----------------------------
def summarize(text: str) -> str:
    prompt = f"다음 내용을 1~2문장으로 요약해줘:\n{text}"
    return gpt([{"role": "user", "content": prompt}], temperature=0.3)

# -----------------------------
# Streamlit UI
# -----------------------------
memory = MemoryStore()
if "message_history" not in st.session_state:
    st.session_state.message_history: List[Message] = []

st.title("🧠 기억 저장소 기반 멀티턴 챗봇")

memory = MemoryStore()
if "message_history" not in st.session_state:
    st.session_state.message_history: List[Message] = []

with st.form("chat_form", clear_on_submit=True):  # 👈 clear_on_submit 옵션 사용
    user_input = st.text_input("👤 메시지를 입력하세요:", key="user_input_form")
    submitted = st.form_submit_button("보내기")

if submitted and user_input:
    if "기억해줘" in user_input:
        content = user_input.replace("기억해줘", "").strip()
        if content:
            topic = gpt([{"role": "user", "content": f"이 문장의 주제를 한 단어로 추출해줘: {content}"}], temperature=0.2)
            summary = summarize(content)
            memory.save(topic, summary)
            st.success(f"기억 저장 완료! (주제: {topic})")
    else:
        context = memory.recall(user_input)
        if context:
            st.session_state.message_history.append({"role": "system", "content": f"참고 정보: {context}"})

        st.session_state.message_history.append({"role": "user", "content": user_input})
        st.session_state.message_history = st.session_state.message_history[-20:]

        # ✅ 스트리밍 결과 수집만, 바로 출력하지 않음
        assistant_response = ""
        for chunk in gpt_stream(st.session_state.message_history):
            assistant_response += chunk

        # ✅ 응답 기록만 추가하고 출력은 아래 루프에서
        st.session_state.message_history.append({"role": "assistant", "content": assistant_response})

# 대화 출력
for msg in st.session_state.message_history:
    role_icon = "🙂" if msg["role"] == "user" else ("📌" if msg["role"] == "system" else "🤖")
    st.markdown(f"**{role_icon} {msg['role']}**: {msg['content']}")
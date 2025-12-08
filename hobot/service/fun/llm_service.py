from __future__ import annotations
from dotenv import load_dotenv
from datetime import datetime
from typing import List, TypedDict, Union, Literal, Any # Union, Literal, Any 추가
import openai
import google.generativeai as genai
import streamlit as st
import json
import os
import io # 이미지 처리용
import base64 # Base64 인코딩용
from PIL import Image # Pillow 라이브러리 (Gemini 이미지 처리용)

# -----------------------------
# 환경 설정
# -----------------------------
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
MEMORY_FILE = "memory_store.json"

# -----------------------------
# 타입 정의 (멀티모달 지원을 위해 확장)
# -----------------------------
# OpenAI API의 content 형식과 유사하게 정의
class TextContentPart(TypedDict):
    type: Literal["text"]
    text: str

class ImageURLContentPart(TypedDict):
    type: Literal["image_url"]
    image_url: dict # {"url": str, "detail": str} (detail은 'high', 'low', 'auto')

# 대화 기록에 저장될 메시지의 content 형식
# 일반 문자열이거나, 텍스트와 이미지를 포함하는 리스트일 수 있음
ChatContent = Union[str, List[Union[TextContentPart, ImageURLContentPart]]]

class ChatMessage(TypedDict):
    role: str
    content: ChatContent

class MemoryEntry(TypedDict):
    topic: str
    summary: str
    created_at: str

# -----------------------------
# 기억 저장소 (요약 기반 구조, SQLite 저장)
# (이미지 입력 기능은 기억 저장소에 직접 연결되지 않습니다. 텍스트만 저장합니다.)
# -----------------------------
from service.database.memory_db import MemoryStore as SQLiteMemoryStore
from service.llm_monitoring import track_llm_call

# SQLite 기반 MemoryStore 사용
class MemoryStore(SQLiteMemoryStore):
    def __init__(self, file_path: str = None):
        # file_path는 호환성을 위해 받지만 사용하지 않음
        super().__init__()

# -----------------------------
# LLM 호출을 위한 메시지 형식 변환 유틸리티
# -----------------------------
def _prepare_llm_messages(messages: List[ChatMessage]) -> List[Any]:
    """
    내부 ChatMessage 형식을 OpenAI 또는 Gemini API가 요구하는 형식으로 변환합니다.
    """
    prepared_messages = []
    for msg in messages:
        if st.session_state.llm_provider == "ChatGPT":
            # OpenAI는 content가 문자열이거나, [{type: 'text'}, {type: 'image_url'}] 리스트 형태
            if isinstance(msg['content'], str):
                prepared_messages.append({"role": msg['role'], "content": msg['content']})
            else: # List[Union[TextContentPart, ImageURLContentPart]]
                prepared_messages.append({"role": msg['role'], "content": msg['content']})
        elif st.session_state.llm_provider == "Gemini":
            # Gemini는 messages 리스트의 각 요소가 {"role": "user", "parts": [text_string, Image_object]} 형태
            gemini_parts = []
            if isinstance(msg['content'], str):
                gemini_parts.append(msg['content'])
            else: # List[Union[TextContentPart, ImageURLContentPart]]
                for part in msg['content']:
                    if part['type'] == "text":
                        gemini_parts.append(part['text'])
                    elif part['type'] == "image_url" and part['image_url']['url'].startswith("data:"):
                        # Base64 디코딩하여 PIL Image 객체로 변환
                        # data:image/jpeg;base64,.... 에서 "data:image/jpeg;base64," 부분을 제거
                        _, encoded_image = part['image_url']['url'].split(",", 1)
                        decoded_image = base64.b64decode(encoded_image)
                        gemini_parts.append(Image.open(io.BytesIO(decoded_image)))

            # Gemini는 role이 'user'와 'model'만 가능하며, assistant는 'model'로 매핑
            role_map = {"user": "user", "assistant": "model", "system": "user"} # 시스템 메시지도 사용자 메시지처럼 프롬프트에 포함 (Gemini Chat API의 한계)
            prepared_messages.append({"role": role_map.get(msg['role'], "user"), "parts": gemini_parts})
    return prepared_messages

# -----------------------------
# GPT 또는 Gemini 호출 함수 (멀티모달 지원)
# -----------------------------
def gpt(messages: List[ChatMessage], temperature: float = 0.5) -> str:
    try:
        prepared_messages = _prepare_llm_messages(messages)
        
        # 프롬프트 추출 (전체 메시지 히스토리에서)
        request_prompt_parts = []
        for msg in messages:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            if isinstance(content, str):
                request_prompt_parts.append(f"{role}: {content}")
            elif isinstance(content, list):
                # 멀티모달 메시지인 경우 텍스트 부분만 추출
                text_parts = [part.get('text', '') for part in content if part.get('type') == 'text']
                if text_parts:
                    request_prompt_parts.append(f"{role}: {' '.join(text_parts)}")
        request_prompt = "\n".join(request_prompt_parts)

        # 모델명과 제공자 가져오기
        model_name = st.session_state.get('llm_model', 'unknown')
        provider = st.session_state.get('llm_provider', 'unknown')
        
        # LLM 호출 추적
        with track_llm_call(
            model_name=model_name,
            provider=provider,
            service_name="llm_service",
            request_prompt=request_prompt
        ) as tracker:
            if st.session_state.llm_provider == "ChatGPT":
                # OpenAI는 content 필드에 문자열 또는 리스트를 직접 받음
                response = openai.chat.completions.create(
                    model=st.session_state.llm_model,
                    messages=prepared_messages, # _prepare_llm_messages에서 OpenAI 형식으로 변환됨
                    temperature=temperature
                )
                result = response.choices[0].message.content.strip()
                
                # 토큰 사용량 추출 (OpenAI 응답에 포함됨)
                if hasattr(response, 'usage'):
                    tracker.set_token_usage(
                        prompt_tokens=response.usage.prompt_tokens if hasattr(response.usage, 'prompt_tokens') else 0,
                        completion_tokens=response.usage.completion_tokens if hasattr(response.usage, 'completion_tokens') else 0,
                        total_tokens=response.usage.total_tokens if hasattr(response.usage, 'total_tokens') else 0
                    )
                
                tracker.set_response(result)
                return result
            elif st.session_state.llm_provider == "Gemini":
                # Gemini는 generate_content 함수에 List[Parts] 형태로 메시지를 전달
                # prepared_messages는 이미 Gemini Chat API의 형식에 맞게 변환되어 있음
                model = genai.GenerativeModel(st.session_state.llm_model)

                # Gemini의 chat 기능은 'send_message'를 통해 이루어지므로,
                # chat session을 생성하고 기존 메시지들을 추가한 뒤 마지막 메시지를 보냅니다.
                chat_session = model.start_chat(history=prepared_messages[:-1])
                response = chat_session.send_message(prepared_messages[-1]['parts'])
                result = response.text.strip()
                
                # Gemini는 토큰 사용량 정보를 별도로 제공하지 않을 수 있음
                # 사용 가능한 경우 추가
                if hasattr(response, 'usage_metadata'):
                    tracker.set_token_usage(
                        prompt_tokens=response.usage_metadata.prompt_token_count if hasattr(response.usage_metadata, 'prompt_token_count') else 0,
                        completion_tokens=response.usage_metadata.candidates_token_count if hasattr(response.usage_metadata, 'candidates_token_count') else 0,
                        total_tokens=response.usage_metadata.total_token_count if hasattr(response.usage_metadata, 'total_token_count') else 0
                    )
                
                tracker.set_response(result)
                return result
    except Exception as e:
        return f"[오류] LLM 호출 실패: {e}"

def gpt_stream(messages: List[ChatMessage], temperature: float = 0.5):
    try:
        prepared_messages = _prepare_llm_messages(messages)
        
        # 프롬프트 추출 (전체 메시지 히스토리에서)
        request_prompt_parts = []
        for msg in messages:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            if isinstance(content, str):
                request_prompt_parts.append(f"{role}: {content}")
            elif isinstance(content, list):
                # 멀티모달 메시지인 경우 텍스트 부분만 추출
                text_parts = [part.get('text', '') for part in content if part.get('type') == 'text']
                if text_parts:
                    request_prompt_parts.append(f"{role}: {' '.join(text_parts)}")
        request_prompt = "\n".join(request_prompt_parts)

        # 모델명과 제공자 가져오기
        model_name = st.session_state.get('llm_model', 'unknown')
        provider = st.session_state.get('llm_provider', 'unknown')
        
        # LLM 호출 추적
        with track_llm_call(
            model_name=model_name,
            provider=provider,
            service_name="llm_service_stream",
            request_prompt=request_prompt
        ) as tracker:
            if st.session_state.llm_provider == "ChatGPT":
                response = openai.chat.completions.create(
                    model=st.session_state.llm_model,
                    messages=prepared_messages, # _prepare_llm_messages에서 OpenAI 형식으로 변환됨
                    temperature=temperature,
                    stream=True
                )
                full_response = ""
                for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        yield content
                        full_response += content
                
                # 스트리밍 완료 후 응답 설정
                tracker.set_response(full_response)
                return full_response
            elif st.session_state.llm_provider == "Gemini":
                # Gemini는 현재 스트리밍 미지원 (send_message는 스트리밍이 아님) → 전체 응답 반환
                # 하지만 gemini-1.5-pro, gemini-1.5-flash 등은 `stream=True` 파라미터를 지원할 수 있으니
                # 여기에 해당 로직을 추가할 수도 있습니다.
                # 이 코드에서는 편의상 스트리밍 미지원으로 처리하여 전체 응답 반환
                # (실제 API는 .generate_content(..., stream=True) 지원)
                model = genai.GenerativeModel(st.session_state.llm_model)
                chat_session = model.start_chat(history=prepared_messages[:-1])

                # Gemini의 스트리밍은 `response.parts`를 순회하는 방식
                full_response = ""
                for chunk in chat_session.send_message(prepared_messages[-1]['parts'], stream=True):
                    if chunk.text: # 텍스트만 처리, 이미지나 다른 파트 무시
                        yield chunk.text
                        full_response += chunk.text
                
                # 스트리밍 완료 후 응답 설정
                tracker.set_response(full_response)
                return full_response

    except Exception as e:
        error_msg = f"[오류] LLM 호출 실패: {e}"
        yield error_msg

# -----------------------------
# 문장 요약 함수 (텍스트만 요약)
# -----------------------------
def summarize(text: str) -> str:
    prompt = f"다음 내용을 1~2문장으로 요약해줘:\n{text}"
    # summarize 함수는 텍스트만 처리하므로, ChatMessage 대신 Message(str content)를 사용
    return gpt([{"role": "user", "content": prompt}], temperature=0.3)

# -----------------------------
# Streamlit UI
# -----------------------------
st.set_page_config(page_title="기억 저장 챗봇", page_icon="🧠")
st.title("🧠 기억 저장소 기반 멀티턴 챗봇 (이미지 입력 지원)")

# LLM 선택 UI
st.sidebar.title("🔧 설정")
llm_provider = st.sidebar.radio("LLM 제공자", ["ChatGPT", "Gemini"], key="llm_provider")

if llm_provider == "ChatGPT":
    model = st.sidebar.selectbox("ChatGPT 모델 선택", ["gpt-3.5-turbo", "GPT-4o mini", "GPT-4o"], key="llm_model")
else:
    model = st.sidebar.selectbox("Gemini 모델 선택", ["gemini-2.5-pro-preview-05-06", "gemini-2.5-flash-preview-05-20", "gemini-2.0-flash", "gemini-2.0-flash-lite"], key="llm_model")

# 사이드바 설정
textarea_rows = st.sidebar.slider("입력창 높이 (줄 수)", min_value=2, max_value=20, value=2)

# 기억 저장소
memory = MemoryStore()

# 대화 상태 초기화
if "message_history" not in st.session_state:
    st.session_state.message_history: List[ChatMessage] = []

# 입력 폼
with st.form("chat_form", clear_on_submit=True):
    user_input = st.text_area("👤 메시지를 입력하세요:", height=textarea_rows * 34, key="user_input_form")
    # 이미지 업로드 위젯 추가
    uploaded_file = st.file_uploader("🖼️ 이미지를 업로드하세요:", type=["png", "jpg", "jpeg", "webp"], key="image_uploader")
    submitted = st.form_submit_button("보내기")

# 메시지 처리
if submitted:
    # 텍스트 입력도 없고, 이미지 입력도 없으면 처리하지 않음
    if not user_input and not uploaded_file:
        st.warning("메시지를 입력하거나 이미지를 업로드해주세요.")
        st.stop() # 더 이상 실행하지 않음

    # # 멀티모달 모델 호환성 체크
    # if uploaded_file:
    #     is_multimodal_model_selected = False
    #     if st.session_state.llm_provider == "ChatGPT":
    #         if st.session_state.llm_model in ["gpt-3.5-turbo", "GPT-4o mini", "GPT-4o"]:
    #             is_multimodal_model_selected = True
    #     elif st.session_state.llm_provider == "Gemini":
    #         if st.session_state.llm_model in ["gemini-2.5-pro-preview-05-06", "gemini-2.5-flash-preview-05-20", "gemini-2.0-flash", "gemini-2.0-flash-lite"]:
    #             is_multimodal_model_selected = True

    #     if not is_multimodal_model_selected:
    #         st.warning(f"⚠️ 선택된 모델({st.session_state.llm_model})은 이미지 입력을 지원하지 않습니다. 이미지와 대화하려면 GPT-4o, GPT-4o mini, 또는 Gemini 1.5 Pro/Flash 같은 멀티모달 모델을 선택해주세요.")
    #         # 이미지가 업로드되었으나 호환되지 않는 모델일 경우, 이미지 없이 텍스트만 처리하거나 경고 후 중단할 수 있음.
    #         # 여기서는 경고만 하고 진행은 하되, LLM에서 오류가 발생할 수 있음.
    #         # 더 안전한 방법은 여기서 `st.stop()`을 호출하거나 `uploaded_file = None`으로 설정하는 것.
    #         # 예를 들어, `uploaded_file = None`으로 설정하면 이미지 없이 텍스트만 LLM으로 전달됨.
    #         # uploaded_file = None # 이미지를 사용하지 않도록 강제
    #         pass # 일단 경고만 하고 진행

    # 사용자의 현재 입력 (텍스트 + 이미지)을 위한 content 리스트 생성
    current_user_content: List[Union[TextContentPart, ImageURLContentPart]] = []

    if user_input:
        # "기억해" 키워드 처리 (이미지 기억은 현재 지원하지 않음)
        if "기억해줘" in user_input:
            content_to_memorize = user_input.replace("기억해줘", "").strip()
            if content_to_memorize:
                # 기억할 내용이 텍스트이므로 텍스트만 summarize에 전달
                topic = gpt([{"role": "user", "content": f"이 문장의 주제를 한 단어로 추출해줘: {content_to_memorize}"}], temperature=0.2)
                summary = summarize(content_to_memorize)
                memory.save(topic, summary)
                st.success(f"기억 저장 완료! (주제: {topic})")
                # 기억 저장이 완료된 경우, LLM 호출 없이 대화 종료
                # 이 경우 챗봇은 응답하지 않으므로, 사용자에게 피드백을 주는 것이 좋음
                st.session_state.message_history.append({"role": "system", "content": f"✅ '기억해줘: {content_to_memorize[:30]}...' 저장 완료!"})
                st.experimental_rerun() # UI 업데이트를 위해 다시 로드
            else:
                st.warning("무엇을 기억해야 할지 알려주세요. 예: '기억해 점심은 된장찌개'")
            st.stop() # '기억해줘' 처리는 LLM 호출 없이 종료

        current_user_content.append({"type": "text", "text": user_input})

    if uploaded_file:
        # 파일 내용을 Base64로 인코딩
        bytes_data = uploaded_file.getvalue()
        base64_image = base64.b64encode(bytes_data).decode("utf-8")
        mime_type = uploaded_file.type # 예: 'image/jpeg'

        current_user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}
            # "detail": "high" 또는 "low"를 추가하여 이미지 품질 설정 가능 (OpenAI)
        })

    # 대화 기록에 사용자 메시지 추가
    # current_user_content는 List[Union[TextContentPart, ImageURLContentPart]] 이므로 ChatContent 타입에 맞음
    st.session_state.message_history.append({"role": "user", "content": current_user_content})
    st.session_state.message_history = st.session_state.message_history[-20:] # 최근 20개 메시지만 유지

    # 기억 저장소에서 관련 컨텍스트 불러오기 (텍스트 입력 기반)
    context = memory.recall(user_input if user_input else "") # 텍스트가 없으면 빈 문자열 전달
    if context:
        st.session_state.message_history.append({"role": "system", "content": f"참고 정보: {context}"})

    # LLM으로부터 응답 받기
    assistant_response_content = ""
    for chunk in gpt_stream(st.session_state.message_history):
        assistant_response_content += chunk
    st.session_state.message_history.append({"role": "assistant", "content": assistant_response_content})

# 대화 출력
for msg in st.session_state.message_history:
    role_icon = "🙂" if msg["role"] == "user" else ("📌" if msg["role"] == "system" else "🤖")

    st.markdown(f"**{role_icon} {msg['role']}**:")

    # content가 문자열인 경우 (기존 텍스트 메시지, 시스템 메시지)
    if isinstance(msg['content'], str):
        st.markdown(msg['content'])
    # content가 리스트인 경우 (멀티모달 메시지)
    else:
        for part in msg['content']:
            if part['type'] == "text":
                st.markdown(part['text'])
            elif part['type'] == "image_url":
                try:
                    # Base64 이미지 데이터를 디코딩하여 표시
                    # 'data:image/jpeg;base64,' 부분을 제외하고 실제 Base64 데이터만 추출
                    _, encoded_image = part['image_url']['url'].split(",", 1)
                    st.image(base64.b64decode(encoded_image), use_container_width =True)
                except Exception as e:
                    st.error(f"이미지 로드 오류: {e}")
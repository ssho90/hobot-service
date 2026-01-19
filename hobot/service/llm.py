from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# .env 파일에서 환경 변수 로드
load_dotenv()

# GPT-4o-mini 설정
def llm_gpt4o_mini():
    gpt4o_mini = ChatOpenAI(
    model_name="gpt-4o-mini",  # GPT-4o-mini에 해당하는 모델명
    temperature=0.3,
    max_tokens=2000,
    )

    return gpt4o_mini

# GPT-4o 설정
def llm_gpt4o():
    gpt4o = ChatOpenAI(
        model_name="gpt-4o",  # GPT-4o에 해당하는 모델명
        temperature=0,
        max_tokens=3000,
    )

    return gpt4o

def llm_gemini_pro(model="gemini-3-pro-preview", timeout=60):
    from langchain_google_genai import ChatGoogleGenerativeAI


    llm = ChatGoogleGenerativeAI(
        model=model,
        temperature=0,
        timeout=timeout,
        max_retries=2,
        transport='rest'
    )

    return llm

def llm_gemini_3_pro(model="gemini-3-pro-preview", timeout=60):
    return llm_gemini_pro(model=model, timeout=timeout)

def llm_gemini_flash(model="gemini-3-flash-preview", timeout=60):
    from langchain_google_genai import ChatGoogleGenerativeAI

    llm = ChatGoogleGenerativeAI(
        model=model,
        temperature=0,
        timeout=timeout,
        max_retries=2,
    )

    return llm
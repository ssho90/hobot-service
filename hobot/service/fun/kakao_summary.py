from dotenv import load_dotenv
from langchain.callbacks import get_openai_callback

load_dotenv()

from langchain_core.prompts import ChatPromptTemplate, load_prompt

# ChatPromptTemplate 생성
prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "You are a bot for summurize the conversation. check the following conversation. {daily_news}"),
        ("user", "{question}"),
    ]
)

import llm
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain.memory import ConversationBufferWindowMemory
from service.utils.text_loader import text_loader

docs = text_loader("data/KakaoTalk_20250310_1510_17_085_group.txt")

chain = (
    {"daily_news": lambda x: docs, "question": RunnablePassthrough()}
    | prompt
    | llm.llm_gemini_flash()
    | StrOutputParser()
)

query = "가장 말 많은 사람 10명의 성격을 자세히 분석해줘."

with get_openai_callback() as cb:
    result = chain.invoke(query)
    print(cb)

print("======================== question =========================")
print(query)
print("========================= result ==========================")
print(result)
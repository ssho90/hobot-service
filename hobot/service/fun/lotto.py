from dotenv import load_dotenv
from langchain.callbacks import get_openai_callback

load_dotenv()

from langchain_core.prompts import ChatPromptTemplate, load_prompt

# ChatPromptTemplate 생성
prompt = ChatPromptTemplate.from_messages(
    [
        ("system",
            """
            *** Guidelines
            - 너는 로또 당첨번호를 추천해주는 봇이야.
            - 예전 당첨 번호들의 패턴을 잘 분석해서 앞으로의 당첨 번호를 예측해줘.
            

            *** 당첨 번호 HISTORY
            - {previous_numbers}

            *** OUTPUT FORM
            - Tell me in Korean.
            - Resent your result in a clear, organized manner. Use bullet points or numbered lists when appropriate.
            """),
        ("user", "{question}"), 
    ]
)

import llm
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain.memory import ConversationBufferWindowMemory
from service.utils.text_loader import text_loader

docs = text_loader("data/lotto_history.txt")

chain = (
    {"previous_numbers": lambda x: docs, "question": RunnablePassthrough()}
    | prompt
    | llm.llm_gemini_20_flash()
    | StrOutputParser()
)

query = "로또 당첨번호 추천해줘."

with get_openai_callback() as cb:
    result = chain.invoke(query)
    print(cb)

print("======================== question =========================")
print(query)
print("========================= result ==========================")
print(result)
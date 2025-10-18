from dotenv import load_dotenv
from langchain.callbacks import get_openai_callback

load_dotenv()

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))))

from langchain_core.prompts import ChatPromptTemplate, load_prompt



# ChatPromptTemplate 생성
prompt = ChatPromptTemplate.from_messages(
    [
        ("system",
            """
            *** Guidelines
            - 너는 사용자 질문에 답변을 해주는 봇이야.
            

            *** OUTPUT FORM
            - Tell me in Korean.
            - Resent your result in a clear, organized manner. Use bullet points or numbered lists when appropriate.
            """),
        ("user", "{question}"), 
    ]
)

import service.llm as llm
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

chain = (
    {"question": RunnablePassthrough()}
    | prompt
    | llm.llm_gemini_pro()
    | StrOutputParser()
)

query = "GCP에 ALB를 구성하고 ALB의 backend 뒤에 Network Endpoint Group을 구성한 뒤, 그 뒤에 Google Kubernetes Engine으로 서버를 띄워놨다. 근데 서버에서 api를 호출할때 request header에 x-forwarded-for 헤더가 빠진채로 호출되고있다. 왜그럴까?"

with get_openai_callback() as cb:
    result = chain.invoke(query)
    print(cb)

print("======================== question =========================")
print(query)
print("========================= result ==========================")
print(result)
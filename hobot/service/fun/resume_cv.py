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
            - 너는 회사 지원서 작성을 도와주는 시스템이야.
            - My Resume, 회사 공고를 기반으로 답변을 해라.
            

            *** 회사 공고
            - {data2}            

            *** My Resume
            - {data}

            *** Line Plus 社 직무 관련 질문
            - {data3}


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
from langchain.memory import ConversationBufferWindowMemory
from service.utils.text_loader import text_loader

docs = text_loader("service/fun/data/resume_user.txt")
docs2 = text_loader("service/fun/data/resume_company.txt")
docs3 = text_loader("service/fun/data/resume_sample.txt")

chain = (
    {
        "data": lambda x: docs,
        "data2": lambda x: docs2,
        "data3": lambda x: docs3,
        "question": RunnablePassthrough()
    }
    | prompt
    | llm.llm_gemini_pro("gemini-2.5-pro-preview-03-25")
    | StrOutputParser()
)

query = """


[answer guideline]
- 내 경력기술서를 참고해서 답변해줘
- 답변 시 회사 공고를 참고해.
- 답변은 한국어로 해줘
- KT에 지원하려고한다. KT 및 해당 직무에 지원한 동기와 본인이 기여할 수 있는 부분에 대해 말씀해 주십시오. (최대 300자 입력가능)
- "KT는 현재 AI에 공격적인 투자를 하고 있다. 나는 AI 서비스 개발도 해봤고, 인프라 구축, DevOps도 해봤다. 나의 이런 다양한 경험은 유연한 사고가 필요한 AI 서비스 개발에 큰 도움이 될 것이다." 이런 흐름으로 글을 작성해줘. 줄바꿈 없이 한줄로 작성해줘.

"""

with get_openai_callback() as cb:
    result = chain.invoke(query)
    print(cb)

print("======================== question =========================")
print(query)
print("========================= result ==========================")
print(result) 
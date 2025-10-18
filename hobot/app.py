from dotenv import load_dotenv

load_dotenv(override = True)

from langchain_core.prompts import ChatPromptTemplate, load_prompt
from langchain_openai import ChatOpenAI
from langchain_community.callbacks import get_openai_callback

def daily_news_summary(query):
    # ChatPromptTemplate 생성
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system",
                """
                *** Guidelines
                - You are a bot for daily news announcement. 
                - Since you are an LLM who does not have recent data, please refer to the data I provided for today's news. check the following daily news.
                - Sometimes you can get additional information by Googling. However, leave the source (url).
                

                *** Daily NEWS 
                - {daily_news}

                *** OUTPUT Guide lines
                - Tell me in Korean.
                - Resent your result in a clear, organized manner. Use bullet points or numbered lists when appropriate.
                - Organize the results so they look good on a mobile screen.
                
                *** OUTPUT FORM Example
                ** 오늘의 주요 뉴스 **
                [트럼프 관세]
                - 트럼프 대통령이 강력한 철강 및 알루미늄 관세를 부과하자 캐나다와 유럽이 신속히 보복 조치를 취했습니다.

                [그린란드 선거]
                - 트럼프의 그린란드 병합 위협이 주요 이슈로 부상한 가운데, 중도 우파 야당이 선거에서 승리했습니다.

                [파키스탄 인질 구조]
                - 파키스탄 서부에서 기차가 납치되고 인질로 잡혔던 27명이 구조되었으나, 구조 작전 중 사망했습니다.
                ============================
                """),
            ("user", "{question}"), 
        ]
    )

    from service.news_scrapper import get_daily_news
    import service.llm
    from langchain_core.runnables import RunnablePassthrough
    from langchain_core.documents import Document
    from langchain_core.output_parsers import StrOutputParser

    chain = (
        {"daily_news": lambda x: get_daily_news(), "question": RunnablePassthrough()}
        | prompt
        | service.llm.llm_gpt4o_mini()
        | StrOutputParser()
    )

    with get_openai_callback() as cb:
        result = chain.invoke(query)
        print(cb)

    print("** question =====================")
    print(query)
    print("\n** response =====================")
    print(result)

    return result

def azure_cert():
    # ChatPromptTemplate 생성
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system",
                """
                *** Guidelines
                - You are a system that helps you solve the exam (Microsoft Certified: Azure Administrator Associate).
                - Choose the correct answer from the following options.

                *** Exam Question
                {exam_question}

                *** Following options
                {options}

                *** OUTPUT FORM
                - Just answer the Azure exam questions that users ask.
                """),
            ("user", "{question}"), 
        ]
    )

    from service.news_scrapper import get_daily_news
    import service.llm
    from langchain_core.runnables import RunnablePassthrough
    from langchain_core.documents import Document
    from langchain_core.output_parsers import StrOutputParser

    exam_question = """
You have a Microsoft Entra tenant that contains the following users:

User1 has a Department set to Sales and a Country set to USA
User2 has a Department set to Marketing and a Country set to USA
User3 has a Department set to Sales and a Country set to DE
User4 has a Department set to Marketing and a Country set to DE

You create a group named Group1 that has the following dynamic membership rule.

user.country -eq "USA" -and user.department -eq "Marketing" -or user.department -eq "Sales"

Which users are members of Group1?
    """

    options = """

User1 and User2 only

User1 and User3 only

User2 and User3 only

User1, User2, and User3 only

User1, User2, User3 and User4
    """

    chain = (
        {"exam_question": lambda x: exam_question, "options": lambda x: options, "question": RunnablePassthrough()}
        | prompt
        | service.llm.llm_gpt4o()
        | StrOutputParser()
    )

    query = '''
    what is the correct answer?
    '''

    with get_openai_callback() as cb:
        result = chain.invoke(query)
        print(cb)

    print("** question =====================")
    print(query)
    print("\n** response =====================")
    print(result)

    return result

def common_query():
    # ChatPromptTemplate 생성
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system",
                """
                You are a common bot to answer the question
                """),
            ("user", "{question}"), 
        ]
    )

    from service.news_scrapper import get_daily_news
    import service.llm
    from langchain_core.runnables import RunnablePassthrough
    from langchain_core.documents import Document
    from langchain_core.output_parsers import StrOutputParser

    chain = (
        {"question": RunnablePassthrough()}
        | prompt
        | service.llm.llm_gpt4o()
        | StrOutputParser()
    )

    query = '''
    [DATA1]
    2021.03.14 - 2022.03.14 : 자동매매 수익률 17%, Benchmark 가격 변동률 -25%
2022.03.14 - 2023.03.14 : 자동매매 수익률 21%, Benchmark 가격 변동률 -38%
2023.03.14 - 2024.03.14 : 자동매매 수익률 160%, Benchmark 가격 변동률 214% 
2024.03.14 - 2025.03.14 : 자동매매 수익률 76%, Benchmark 가격 변동률 21%


[DATA2]
2021.03.14 - 2022.03.14 : 자동매매 수익률 20%, Benchmark 가격 변동률 -25%
2022.03.14 - 2023.03.14 : 자동매매 수익률 32%, Benchmark 가격 변동률 -38%
2023.03.14 - 2024.03.14 : 자동매매 수익률 152%, Benchmark 가격 변동률 214% 
2024.03.14 - 2025.03.14 : 자동매매 수익률 85%, Benchmark 가격 변동률 21%

Data1과 Data2는 자동매매로 구현한 Trading Bot의 수익률을 나타냅니다.
Data1과 Data2의 총 수익률을 비교하여 어떤 데이터가 더 좋은 성능을 보였는지 분석해줘.
    '''

    with get_openai_callback() as cb:
        result = chain.invoke(query)
        print(cb)

    print("** question =====================")
    print(query)
    print("\n** response =====================")
    print(result)

    return result

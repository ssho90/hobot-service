from langchain_community.document_loaders import TextLoader

def text_loader(path):
    # 텍스트 로더 생성
    loader = TextLoader(path, encoding="utf-8")

    # 문서 로드
    docs = loader.load()

    return docs
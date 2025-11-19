---
opensearch proxy 접근 참조
https://repost.aws/ko/articles/ARlnlpfQIFSISRopWeP-zuVw/vpc-%EC%99%B8%EB%B6%80%EC%97%90%EC%84%9C-open-search-dashboards%EC%97%90-%EC%97%91%EC%84%B8%EC%8A%A4%ED%95%98%EB%8A%94-%EB%B0%A9%EB%B2%95

---

(13: Permission denied) while connecting to upstream  오류 발생시 redhat os 설정 해줘야됨
: setsebool httpd_can_network_connect on -P
참조: https://deeplify.dev/server/web/permission-denied-while-connecting-to-upstream

---

SentenceTransformer(model_name_or_path = "Linq-AI-Research/Linq-Embed-Mistral", token=hg_api_key) 실행 시 ssl error 발생
직접 모델 다운받아서 사용하기
git clone https://huggingface.co/Linq-AI-Research/Linq-Embed-Mistral
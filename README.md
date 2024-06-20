# NTHURC-Search-PoC
Help 新北市住都中心建立測試 AI Search PoC
- 通過提問詢問 PDF 並**提取相關的資料後產生總結以及輸出相關參考文獻**
- 使用 LLM (**Gemini-1.5-Flash**) 來總結相關資料產生回答
- 使用 **Vertex Search** 來提取 PDF 中與提問相關的資料
- 資料來源自 : **:red[113 年度第 1 次隨到隨辦 土城大安、土城永和、板橋江翠、土城明德 2 號、五股成州、新店央北 及三峽國光等七處青年社會住宅申請須知]**以及**住都中心網站常見問題資料**
- 可以使用 Vertex Search 提供的 **Widget** 也可以通過 **API** 或是 Python Library 來部署在網站中
- 在**企業中的 Use Case** : 可以用來作為外部人員了解公司的管道，也可以作為內部人員輔助工具( 新人 On boarding 輔助系統、客服回答問題 KnowledgeBase、增強企業內部搜尋的能力等相關用途)

## Deploy on GCP : 
- docker 建立 : docker buildx build --platform linux/amd64 -t asia-east1-docker.pkg.dev/nthurc-aisearch-202406/nthurc-search-poc/search_poc_app:latest .
- gcloud auth print-access-token | docker login -u oauth2accesstoken --password-stdin asia-east1-docker.pkg.dev
- docker push asia-east1-docker.pkg.dev/nthurc-aisearch-202406/nthurc-search-poc/search_poc_app
- 測試網站： https://nthurc-search.hkmci.com.tw/
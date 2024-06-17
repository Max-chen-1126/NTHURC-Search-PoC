import streamlit as st
from dotenv import load_dotenv
import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig
from google.cloud import aiplatform
from google.api_core.client_options import ClientOptions
import urllib
import google.cloud.discoveryengine_v1 as discoveryengine


def search_pdf_and_sum(user_query, status, show_context=True):
    """
        搜尋 PDF 文件並生成摘要的函式。

        Args:
            user_query (str): 使用者的查詢。
            status (Status): 用於顯示搜尋狀態的狀態欄。
            show_context (bool, optional): 是否顯示相關內容。預設為 True。

        Returns:
            str: 摘要回答。
            str: 相關內容。

        Raises:
            Exception: 發生錯誤時拋出異常。

    """
    try:
        # 建立 Discovery Engine 的客戶端
        client_options = (ClientOptions(api_endpoint=f"{location}-aiplatform.googleapis.com")
                          if location != "global" else None)
        client = discoveryengine.SearchServiceClient(
            client_options=client_options)
        # 設定服務配置
        serving_config = client.serving_config_path(
            project=project_id, location=location, data_store=engine_id, serving_config="default_config")

        # 發送搜尋請求
        response = client.search(
            request=discoveryengine.SearchRequest(
                query=user_query,
                page_size=2,
                serving_config=serving_config,
                content_search_spec=discoveryengine.SearchRequest.ContentSearchSpec(
                    extractive_content_spec=discoveryengine.SearchRequest.ContentSearchSpec.ExtractiveContentSpec(
                        max_extractive_segment_count=4,
                        return_extractive_segment_score=True,
                        num_previous_segments=1,
                        num_next_segments=1,
                    )
                ),
                query_expansion_spec=discoveryengine.SearchRequest.QueryExpansionSpec(
                    condition=discoveryengine.SearchRequest.QueryExpansionSpec.Condition.AUTO
                ),
                spell_correction_spec=discoveryengine.SearchRequest.SpellCorrectionSpec(
                    mode=discoveryengine.SearchRequest.SpellCorrectionSpec.Mode.AUTO
                )
            )
        )
        status.update(label="Search complete!",
                      state="running", expanded=False)

        # 解析搜尋結果
        results = []
        for result in response.results:
            document = dict(result.document.derived_struct_data)
            if 'extractive_segments' in document.keys():
                document['extractive_segments'] = [
                    dict(segment) for segment in document['extractive_segments']]
            results.append(document)

        # 過濾搜尋結果, 只保留 relevanceScore 大於 0.8 的 segment
        filtered_results = []
        for result in results:
            filtered_segments = []
            for segment in result['extractive_segments']:
                if segment['relevanceScore'] >= 0.80:
                    filtered_segments.append(segment)
            result['extractive_segments'] = filtered_segments
            relevance_score = max(
                (segment["relevanceScore"]
                 for segment in result["extractive_segments"]),
                default=None,
            )
            result['relevanceScore'] = relevance_score
            filtered_results.append(result)

        # 排序，確保 relevanceScore 存在
        filtered_results = sorted(
            [result for result in filtered_results if result.get(
                'relevanceScore') is not None],
            key=lambda x: x['relevanceScore'],
            reverse=True,
        )

        if not filtered_results:  # 如果 filtered_results 為空則回傳 No results
            return 'No results', "No results"

         # 生成摘要，提供給 LLM 作為背景資料
        segments_results = ''
        for r, result in enumerate(filtered_results):
            segments_results += f"\n\nSource Document {r+1} (Relevance Score: {result['relevanceScore']:.3f}):\n\tName: {result['title']}"
            if 'extractive_segments' in result.keys() and result['extractive_segments']:
                for s, segment in enumerate(result['extractive_segments']):
                    content = segment['content']
                    content = content.replace("\n", " ")
                    segments_results += f"\n\tSegment {s+1} (page = {segment['pageNumber']}): {content}"

    except Exception as e:
        if "max() arg is an empty sequence" in str(e):  # 檢查是否為 max() 錯誤
            st.error(f"No relevant results found.")
            return 'No results', "No results"  # 捕獲其他可能的錯誤
        else:
            st.error(f"An error occurred: {e}")
            return 'No results', "No results"

    # 使用 Gemini-1.5-Flash 模型生成回答
    textgen_model = GenerativeModel("gemini-1.5-flash")
    generation_config = GenerationConfig(
        temperature=0.1,
        top_p=0.8,
        top_k=5,
        candidate_count=1,
        max_output_tokens=2048,
    )
    safety_config = [
        vertexai.generative_models.SafetySetting(
            category=vertexai.generative_models.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
            threshold=vertexai.generative_models.HarmBlockThreshold.BLOCK_ONLY_HIGH,
        ),
        vertexai.generative_models.SafetySetting(
            category=vertexai.generative_models.HarmCategory.HARM_CATEGORY_HARASSMENT,
            threshold=vertexai.generative_models.HarmBlockThreshold.BLOCK_ONLY_HIGH,
        ),
    ]
    prompt = f"你目前是新北市政府住宅及都市更新中心的社會住宅問答機器人，主要負責回答關於社會住宅申請以及規範的一些疑問，基於使用者提出的問題，我會提供你一些與社會住宅相關的檔案，我希望你只能基於我提供的這些檔案找出答案並進行回答，並且如果你無法回答或是提供的檔案內並沒有答案，請你誠實的告訴我你無法回答這題。\n\n 檔案片段：{segments_results}。\n\n 問題：{user_query}，\n\n 請以務必繁體中文以及 Markdown 語法輸出結果，並只使用文件內內容進行回答，請盡量使用文件中內容豐富回答以幫助提問者完整理解，請一步一步思考，這對我的職業生涯非常重要，請務必認真看待。\n\n提供簡短且準確地回答: Let's work step by step."

    prediction = textgen_model.generate_content(
        prompt, generation_config=generation_config, safety_settings=safety_config)

    if show_context == True:
        if prediction and prediction.candidates:  # 檢查是否存在預測和候選項
            candidate = prediction.candidates[0]  # 獲取第一個候選項
            if candidate.content and candidate.content.parts:  # 檢查是否存在內容和部分
                # 拼接所有部分的文本
                first_answer = "".join(
                    [part.text for part in candidate.content.parts])
                answer = f'''### :blue[Answer]\n{first_answer}\n\n'''
            else:
                answer = ""  # Handle the case where content or parts are missing
        else:
            answer = ""  # Handle the case where content or parts are missing

        text = ""
        for r, result in enumerate(response.results):

            if r > 0:
                text += '\n'
            doc = dict(result.document.derived_struct_data)

            # get document title:
            if 'title' in doc.keys():
                title = doc['title']
                print(title)
            else:
                title = doc['link'].split('/')[-1]

            # get document hyperlink
            if 'link' in doc.keys():
                if doc['link'].startswith('gs://'):
                    link = 'https://storage.cloud.google.com/' + \
                        urllib.parse.quote(doc['link'].replace('gs://', ''))
            else:
                link = ''  # this should not happen

            # construct title with link
            if link:
                title_link = f'[{title}]({link})'
            else:
                title_link = title

            text += f"{r+1}. {title_link}"
            if 'extractive_segments' in doc.keys():
                for e, extract in enumerate(doc['extractive_segments']):

                    # construct page with link
                    if link:
                        page_link = f"[page = {extract['pageNumber']}]({link}#page={extract['pageNumber']})"
                    else:
                        page_link = f"page = {extract['pageNumber']}"

                    len_extract = len(extract['content'])
                    part = extract["content"][0:min(
                        [250, len_extract])].replace("\n", " ")

                    if len_extract > len(part):
                        part_suffix = f' ... ({len_extract - 250} more characters)'
                    else:
                        part_suffix = ''

                    text += f'''\n\t- Segment {e+1} (Relevance Score: {extract['relevanceScore']:.3f}) ({page_link}): {part}{part_suffix}'''
        st.write("完成總結及提供參考文獻")
    return answer, text


def main():
    """
    主函式，用於設定網頁標題、佈局和側邊欄，並處理使用者的輸入和搜尋操作。
    """

    st.set_page_config(page_title="社會住宅申請須知 AI 問答 ",
                       page_icon="🔍", layout='wide')
    st.title(":violet[社會住宅申請須知 AI 問答 🔍]")

    with st.sidebar:
        url = 'https://storage.googleapis.com/image-text-generate-test/unnamed.png'

        with st.expander("🤖 **關於 AI 搜尋**", expanded=True):
            st.markdown('''
                    - 通過提問詢問 PDF 並**提取相關的資料後產生總結以及輸出相關參考文獻**
                    - 使用 LLM (**Gemini-1.5-Flash**) 來總結相關資料產生回答
                    - 使用 **Vertex Search** 來提取 PDF 中與提問相關的資料
                    - 資料來源自 : **:red[113 年度第 1 次隨到隨辦 土城大安、土城永和、板橋江翠、土城明德 2 號、五股成州、新店央北 及三峽國光等七處青年社會住宅申請須知]**以及**:red[住都中心網站常見問題資料]**
                    - 可以使用 Vertex Search 提供的 **Widget** 也可以通過 **API** 或是 Python Library 來部署在網站中
                    - 在**企業中的 Use Case** : 可以用來作為外部人員了解公司的管道，也可以作為內部人員輔助工具( 新人 On boarding 輔助系統、客服回答問題 KnowledgeBase、增強企業內部搜尋的能力等相關用途)
                    ''')
        st.divider()
        st.markdown('''
            ### :blue[關於 Master Concept] :
            - 思想科技 Master Concept 致力於提供科技服務與雲端顧問諮詢，為世界級的領導品牌改善客戶體驗。
            - 擁有超過 120 位夥伴在數位轉型過程中為亞太地區上千間的企業客戶服務，我們團隊為橫跨各產業的客戶提供專業雲端策略、技術導入與整合支援、專業培訓以及平台升級。
            - 聯絡我們：
                - [官網](https://hkmci.com/zh-hant/)
                - [聯絡我們](https://hkmci.com/zh-hant/%E8%81%AF%E7%B9%AB%E6%88%91%E5%80%91/)
        ''')
        st.image(url, caption='Master Concept', use_column_width=True)

    vertexai.init(project=project_id, location=region)
    aiplatform.init(project=project_id, location=region)

    with st.expander("📍 **測試案例**", expanded=False):
        st.markdown("""
                        相關的一些測試問題：
                        1. 申請土城明德2號社宅的套房型月租金為多少？
                        2. 申請時需要檢附哪些文件？
                        3. 本案社宅的遞補名冊有效期間為多久？
                        4. 本案有哪些房型的社宅可供申請？
                        5. 本案的申請期限為何？可以郵寄申請嗎？
                        """)
    st.markdown('---')
    user_query = st.text_input("提問")
    button = st.button('搜尋')
    if button:
        st.markdown('## 🤖 :orange[社宅小助手] : \n\n')
        with st.status('搜尋中...') as status:
            st.write("開始搜尋相關資料")
            answer, text = search_pdf_and_sum(
                user_query, status, show_context=True)
            status.update(label="完成", state="complete", expanded=False)
        if answer != 'No results' or text != 'No results':
            st.markdown(answer)
            with st.expander("📎 來源", expanded=False):
                st.write(text)
        else:
            st.warning("很抱歉，沒有找到相關資料, 請重新輸入與新北市社會住宅申請以及規範相關的問題")


if __name__ == "__main__":
    load_dotenv()
    project_id = "nthurc-aisearch-202406"
    location = "global"
    engine_id = "pdf-data-search_1718003912950"
    region = "asia-east1"
    main()

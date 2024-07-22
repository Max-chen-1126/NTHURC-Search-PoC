import streamlit as st
from dotenv import load_dotenv
from google.cloud import aiplatform
from google.api_core.client_options import ClientOptions
import urllib.parse
import google.cloud.discoveryengine_v1alpha as discoveryengine
from typing import List, Optional, Tuple
from google.api_core import exceptions
from langchain_core.messages import AIMessage, HumanMessage
import os


def searchWithSummary(
    project_id: str,
    location: str,
    data_store_id: str,
    search_queries: List[str],
    conversation_id: Optional[str] = None,
) -> Tuple[str, str]:  # type: ignore
    """
    在對話中搜尋與給定查詢相關的資訊。

    參數:
        project_id (str): 專案 ID。
        location (str): 數據存儲的位置。
        data_store_id (str): 數據存儲的 ID。
        search_queries (List[str]): 搜尋查詢列表。
        conversation_id (str, optional): 對話 ID。預設為 None。

    返回:
        Tuple[str, str]: 包含摘要文本和格式化的提取答案列表的元組。

    異常:
        Exception: 當 API 調用失敗時拋出。
    """
    try:
        client = _create_client(location)
        conversation_name = _get_or_create_conversation(
            client, project_id, location, data_store_id, conversation_id)

        for search_query in search_queries:
            request = _create_converse_request(
                client, conversation_name, project_id, location, data_store_id, search_query)
            response = client.converse_conversation(request)

            if response.reply.summary.summary_skipped_reasons:
                return "⚠️ 抱歉，請檢查您的問題是否與社宅相關，需要進一步處理請聯繫 **09123456789**", ""

            summary_text = response.reply.summary.summary_text
            extractive_answers = _format_extractive_answers(
                response.reply.summary.summary_with_metadata.references)  # type: ignore

            return summary_text, "\n ".join(extractive_answers)

    except exceptions.GoogleAPICallError as e:
        print(f"API 調用錯誤: {e}")
        return "發生錯誤，請稍後再試或聯繫支援人員。", ""
    except Exception as e:
        print(f"未預期的錯誤: {e}")
        return "發生未知錯誤，請聯繫支援人員。", ""


def _create_client(location: str) -> discoveryengine.ConversationalSearchServiceClient:
    """創建並返回 ConversationalSearchServiceClient。"""
    client_options = ClientOptions(
        api_endpoint=f"{location}-discoveryengine.googleapis.com") if location != "global" else None
    return discoveryengine.ConversationalSearchServiceClient(client_options=client_options)


def _get_or_create_conversation(
    client: discoveryengine.ConversationalSearchServiceClient,
    project_id: str,
    location: str,
    data_store_id: str,
    conversation_id: Optional[str]
) -> str:
    """獲取現有對話或創建新對話。"""
    if conversation_id:
        return client.conversation_path(project=project_id, location=location, data_store=data_store_id, conversation=conversation_id)

    conversation = client.create_conversation(
        parent=client.data_store_path(
            project=project_id, location=location, data_store=data_store_id),
        conversation=discoveryengine.Conversation(),
    )
    st.session_state["conversation_id"] = conversation.name.split('/')[-1]
    print(conversation.name)
    return conversation.name


def _create_converse_request(
    client: discoveryengine.ConversationalSearchServiceClient,
    conversation_name: str,
    project_id: str,
    location: str,
    data_store_id: str,
    search_query: str
) -> discoveryengine.ConverseConversationRequest:
    """創建 ConverseConversationRequest 對象。"""
    return discoveryengine.ConverseConversationRequest(
        name=conversation_name,
        safe_search=True,
        query=discoveryengine.TextInput(input=search_query),
        serving_config=client.serving_config_path(
            project=project_id,
            location=location,
            data_store=data_store_id,
            serving_config="default_config",
        ),
        summary_spec=discoveryengine.SearchRequest.ContentSearchSpec.SummarySpec(
            summary_result_count=3,
            include_citations=True,
            model_spec=discoveryengine.SearchRequest.ContentSearchSpec.SummarySpec.ModelSpec(
                version="gemini-1.5-flash-001/answer_gen/v1"  # "preview"
            ),
            model_prompt_spec=discoveryengine.SearchRequest.ContentSearchSpec.SummarySpec.ModelPromptSpec(
                preamble="""
                你是新北市政府住宅及都市更新中心的社會住宅申請問答助手。你的任務是專門回答與社會住宅申請程序和條件相關的問題。請遵循以下指引：
                個性與表達方式：
                    保持溫和、耐心的態度
                    使用口語化、淺顯易懂的方式解釋複雜概念
                    避免使用艱澀的專業術語，改用日常用語
                回答範圍：
                    嚴格限制在社會住宅申請相關問題
                    僅回答有明確書面記載的資訊
                    不討論社宅剩餘戶數等即時性資訊
                    不涉及申請流程以外的話題
                資訊來源與回答方式：
                    僅使用提供的官方參考資料
                    將正式文件內容轉換為口語化表達
                    簡化複雜規定，但確保資訊準確無誤
                    如遇超出參考資料範圍的問題，坦誠表示無法回答
                語言要求：
                    使用繁體中文回答所有問題
                回答態度：
                    認真對待每個問題，視為重要工作
                    仔細思考並確認資訊正確性後再回答
                互動指引：
                    鼓勵使用者提出具體問題
                    適時詢問是否需要進一步解釋
                    引導使用者至官方管道尋求更多協助 (官網 : https://www.nthurc.org.tw/ , 官方電話: (02) 2957-1999  )
                請記住，你的角色是協助民眾了解社會住宅申請流程，而非提供個人建議或即時資訊。保持專業、友善，並始終以幫助申請者為目標。
                """
            ),
            language_code="zh-TW",
            ignore_adversarial_query=True,
            ignore_non_summary_seeking_query=True,
        ),
    )


def _format_extractive_answers(references) -> List[str]:
    """格式化提取的答案。"""
    extractive_answers = []
    for i, reference in enumerate(references, 1):
        name = "申請須知(上)" if reference.title == "<4D6963726F736F667420576F7264202D20313133A67EABD7B2C431A6B8C048A8ECC048BFEC28A467ABB0A46AA677A142A467ABB0A5C3A94DA142A4ADAAD1A6A8A67BA142B773A9B1A5A1A55FA4CEA454AE6CB0EAA5FA292DA5D3BDD0B6B7AABE>" else reference.title
        link = 'https://storage.cloud.google.com/' + urllib.parse.quote(
            reference.uri.replace('gs://', '')) if reference.uri.startswith('gs://') else ""
        ref = f"[{i}] : [{name}]({link})"
        extractive_answers.append(ref)
    return extractive_answers


def load_environment_variables() -> Tuple[str, str, str, str]:
    """載入環境變數"""
    load_dotenv()
    return (
        os.getenv("PROJECT_ID", "nthurc-aisearch-202406"),
        os.getenv("LOCATION", "global"),
        os.getenv("ENGINE_ID", "pdf-data-search_1718003912950"),
        os.getenv("REGION", "asia-east1")
    )


def setup_page_config():
    """設置頁面配置"""
    st.set_page_config(
        page_title="社會住宅申請須知 AI 問答",
        page_icon="🔍",
        layout='wide'
    )
    st.title(":violet[社會住宅申請須知 AI 問答 🔍]")


def setup_sidebar():
    """設置側邊欄"""
    with st.sidebar:
        url = 'https://storage.googleapis.com/image-text-generate-test/unnamed.png'

        with st.expander("🤖 **關於 AI 搜尋**", expanded=False):
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


def setup_test_cases():
    """設置測試案例"""
    with st.expander("📍 **測試案例**", expanded=True):
        st.markdown("""
        相關的一些測試問題：
        1. 社會住宅的申請流程是什麼？需要哪些基本文件？
        2. 青年社會住宅戶租金訂定原則為何？是否需另外繳交管理費？
        3. 如果申請人的戶籍所在地在外縣市，是否能申請新北市的社會住宅？
        4. 承租社會住宅後是否可以將房屋轉租或用於商業用途？違反規定會有什麼後果？
        5. 目前接受政府其他租金補貼者，是否可以再申請青年社會住宅？入住後原租金補貼資格會怎麼處理？
        """)


def display_chat_history(chat_history: List):
    """顯示聊天歷史"""
    for message in chat_history:
        if isinstance(message, AIMessage):
            with st.chat_message("AI"):
                st.markdown(message.content)
        elif isinstance(message, HumanMessage):
            with st.chat_message("Human"):
                st.markdown(message.content)


def handle_user_input(
    user_query: str,
    chat_history: List,
    project_id: str,
    location: str,
    engine_id: str
) -> Tuple[str, str]:
    """處理用戶輸入並返回 AI 回應"""
    try:
        conversation_id = st.session_state.get("conversation_id")
        response, refs = searchWithSummary(
            project_id, location, engine_id, [user_query], conversation_id
        )
        return response, refs
    except Exception as e:
        st.error(f"處理查詢時發生錯誤：{str(e)}")
        return "抱歉，處理您的查詢時發生錯誤。請稍後再試。", ""


def main():
    """
    主函數，用於設定網頁標題、佈局和側邊欄，並處理使用者的輸入和搜尋操作。
    """
    project_id, location, engine_id, region = load_environment_variables()

    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []

    setup_page_config()
    setup_sidebar()
    setup_test_cases()

    try:
        aiplatform.init(project=project_id, location=region)
    except Exception as e:
        st.error(f"初始化 AI 平台時發生錯誤：{str(e)}")
        return

    display_chat_history(st.session_state.chat_history)

    user_query = st.chat_input("輸入您的問題...")
    if user_query and user_query.strip() != "":
        st.session_state.chat_history.append(HumanMessage(content=user_query))
        with st.chat_message("Human"):
            st.markdown(user_query)

        with st.chat_message("AI"):
            response, refs = handle_user_input(
                user_query, st.session_state.chat_history, project_id, location, engine_id)
            st.markdown(response)
            if refs:
                st.caption("📚參考資料 : \n" + refs)

        st.session_state.chat_history.append(AIMessage(content=response))


if __name__ == "__main__":
    main()

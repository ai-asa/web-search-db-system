# 標準ライブラリ
import json
import logging
import os
import time
from pathlib import Path
from typing import List, Optional

# サードパーティライブラリ
import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv

# 自作モジュール
from src.chat.openai_adapter import OpenaiAdapter
from src.chat.get_prompt import (
    get_article_selection_prompt,
    get_article_grouping_prompt,
    get_article_content_summarize_prompt,
    get_article_search_keywords_prompt,
    get_article_detail_prompt,
    get_article_similarity_check_prompt,
    get_article_merge_prompt,
    get_article_retention_period_prompt,
    get_initial_article_analysis_prompt,
    get_relevance_validation_prompt
)
from src.websearch.web_search import WebSearch
from src.tiktoken.token_counter import count_tokens
from src.webscraping.yahoo_news_scraper import YahooNewsScraper
from src.firestore.firestore_adapter import FirestoreAdapter
from src.webscraping.web_scraping import WebScraper

# グローバルインスタンスの初期化
openai_adapter = OpenaiAdapter()
web_search = WebSearch()
yahoo_news_scraper = YahooNewsScraper()
web_scraper = WebScraper()
firestore_adapter = FirestoreAdapter()

# 認証情報のパスを設定
credentials_path = str(Path("secret-key") / f"{os.getenv('CLOUD_FIRESTORE_JSON')}.json")
cred = credentials.Certificate(credentials_path)

# Firebase初期化（既に初期化されていない場合のみ）
if not firebase_admin._apps:
    app = firebase_admin.initialize_app(cred)
db = firestore.client()


"""処理の詳細
・Yahooニュースの国内、国際、経済の3トピックの記事名と概要URLを全件取得
・概要ページから本記事とピックアップ記事のタイトルとURLを全件取得
・Firestoreの取得済み記事を除外する → 過去に一度でも取得した記事は除外する
・AIで保険営業に関係しそうな記事の判定
・選択した記事のタイトルとURLをデータベースに保存 → ここでもデータベースに保存済みの記事は除外する
・取得した記事を内容によってグループ分け
# グループ記事について
・新しい記事を2つだけAIで読み込んで本質情報が含まれているかを判断する
→ 含まれていない場合、そのグループトピックは除外する
→ 含まれている場合、以下の処理を行う
・グループの記事数が5件以下の場合はピックアップ記事を含め、全件を分割読込して、AIで本質情報を抽出する
→ 5件以上の場合は、ピックアップ記事を除外し、メイン記事全件を分割読込して、AIで本質情報を抽出する
・本質情報が含まれていないグループは削除する
# 単体記事について
・メイント記事のみを読み込んで、AIで本質情報が記事に存在するかを分析する
→ 存在し、ピックアップ記事がある場合は、メインとサブの両方を読み込んでAIによる本質情報の抽出を行う
→ 存在し、ピックアップ記事がない場合は、本質情報について検索キーワードをAI生成し、検索結果のスクレイピングで、対象情報を整理する
・本質情報が存在しない記事は削除する
・各グループまたは各記事毎に取得した本質情報(extracted_info)と全文情報(combined_content)をAIに渡して、詳細な本質情報とターゲット顧客を生成
・ターゲット顧客情報についてベクトル埋め込みを行い、データベース上を検索して、類似情報を取得(0.65>あたり)
・同一の時系列記事がある場合は、新たに追記と古い情報の削除による更新データをAIで生成
・今回作成された本質情報を、一斉に保存期間をAIに判断させて、データベースに保存

# 使用方法
・ユーザーの入力情報をベクトル埋め込み
・データベース上を検索して、類似情報を取得(0.65>あたり)
・理由を添えて本質情報を選定
・記事毎にアイスブレイク用のテキストを生成
"""
def setup_logging():
    """ロギングの設定"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def display_results(results: dict):
    """
    スクレイピング結果を表示します

    Args:
        results (dict): カテゴリごとの記事リスト
    """
    for category, articles in results.items():
        print(f"\n【{category}】の記事一覧:")
        print(f"取得記事数: {len(articles)}件")
        for article in articles[:5]:  # 最初の5件のみ表示
            print(f"- {article['title']}")
            print(f"  URL: {article['url']}")
        if len(articles) > 5:
            print(f"  ... 他 {len(articles) - 5}件")

def scrape_news_articles() -> dict:
    """
    Yahoo Newsから記事をスクレイピングします

    Returns:
        dict: カテゴリごとの記事リスト
    """
    logger = logging.getLogger(__name__)
    logger.info("Starting to scrape Yahoo News categories...")
    return yahoo_news_scraper.scrape_all_categories(save_results=True)

def filter_new_articles(articles_by_category: dict) -> list:
    """
    既存の記事を除外し、新規記事のみをフィルタリングします

    Args:
        articles_by_category (dict): カテゴリごとの記事リスト

    Returns:
        list: 新規記事のリスト
    """
    logger = logging.getLogger(__name__)
    logger.info("Fetching existing articles from Firestore...")
    existing_articles = firestore_adapter.get_discovered_articles(db)
    existing_urls = {article['url'] for article in existing_articles}

    new_articles = []
    for category, articles in articles_by_category.items():
        for article in articles:
            if article['url'] not in existing_urls:
                new_articles.append(article)
                logger.info(f"Found new article: {article['title']}")

    return new_articles

def process_article_batch(batch_articles: list, batch_start: int) -> list:
    """
    記事バッチを処理し、関連する記事を選別します

    Args:
        batch_articles (list): 処理する記事のバッチ
        batch_start (int): バッチの開始インデックス

    Returns:
        list: 選別された記事のリスト
    """
    logger = logging.getLogger(__name__)
    numbered_articles = []
    article_text = ""

    for i, article in enumerate(batch_articles, batch_start + 1):
        numbered_articles.append({
            "number": i,
            "title": article["title"],
            "url": article["url"]
        })
        article_text += f"{i}. {article['title']}\n"

    selection_prompt = get_article_selection_prompt()
    selection_response = openai_adapter.openai_chat(
        openai_model="gpt-4o",
        prompt=selection_prompt + "\n\n" + article_text
    )

    try:
        selection_start = selection_response.find("<selected_articles>") + len("<selected_articles>")
        selection_end = selection_response.find("</selected_articles>")
        selected_numbers_str = selection_response[selection_start:selection_end].strip()

        selected_numbers_str = selected_numbers_str.replace('[', '').replace(']', '')
        selected_numbers = []
        if selected_numbers_str:
            for num_str in selected_numbers_str.replace(',', ' ').split():
                try:
                    num = int(num_str.strip())
                    selected_numbers.append(num)
                except ValueError as ve:
                    logger.warning(f"Invalid number format found: {num_str}")
                    continue

        reasoning_start = selection_response.find("<reasoning>") + len("<reasoning>")
        reasoning_end = selection_response.find("</reasoning>")
        selection_reasoning = selection_response[reasoning_start:reasoning_end].strip()

        if not selected_numbers:
            logger.info("\n選別結果：")
            logger.info("保険営業の時事ネタとして適切な記事は見つかりませんでした。")
            logger.info(f"\n理由：\n{selection_reasoning}")
            return []

        logger.info("\n選別結果：")
        logger.info(f"保険営業の時事ネタとして {len(selected_numbers)} 件の記事が選択されました。")

        batch_selected_articles = []
        for num in selected_numbers:
            article = next((a for a in numbered_articles if a["number"] == num), None)
            if article:
                batch_selected_articles.append({
                    "title": article["title"],
                    "url": article["url"]
                })
                logger.info(f"\n{article['number']}. {article['title']}")
                logger.info(f"   URL: {article['url']}")

        logger.info(f"\n選択理由：\n{selection_reasoning}")
        return batch_selected_articles

    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"Error processing selection: {str(e)}")
        logger.error(f"Raw response: {selection_response}")
        return []

def select_relevant_articles(new_articles: list, batch_size: int = 50) -> list:
    """
    新規記事から関連する記事を選別します

    Args:
        new_articles (list): 新規記事のリスト
        batch_size (int, optional): バッチサイズ. デフォルトは50

    Returns:
        list: 選別された記事のリスト。既存のデータベースに存在しない記事のみを含む
    """
    logger = logging.getLogger(__name__)
    logger.info("Starting article selection process...")
    all_selected_articles = []

    for batch_start in range(0, len(new_articles), batch_size):
        batch_end = min(batch_start + batch_size, len(new_articles))
        batch_articles = new_articles[batch_start:batch_end]
        
        logger.info(f"Processing batch {batch_start//batch_size + 1} ({batch_start+1} to {batch_end} of {len(new_articles)} articles)")
        batch_selected_articles = process_article_batch(batch_articles, batch_start)
        all_selected_articles.extend(batch_selected_articles)

    # 選別された記事をデータベースに保存し、新規記事のみを取得
    if all_selected_articles:
        logger.info(f"Saving {len(all_selected_articles)} selected articles to referenced articles...")
        new_referenced_articles = save_new_referenced_articles(all_selected_articles)
        logger.info(f"Found {len(new_referenced_articles)} new articles that were not in the database.")
        return new_referenced_articles

    return []

def save_new_referenced_articles(selected_articles: list) -> list:
    """
    選別された新規記事を参照記事として保存します

    Args:
        selected_articles (list): 選別された記事のリスト

    Returns:
        list: 新規参照記事のリスト。既存のデータベースに存在しない記事のみを含む
    """
    logger = logging.getLogger(__name__)
    if not selected_articles:
        return []

    logger.info("過去の参照記事を取得中...")
    referenced_articles = firestore_adapter.get_referenced_articles(db)
    referenced_urls = {article['url'] for article in referenced_articles}

    new_referenced_articles = [
        article for article in selected_articles
        if article['url'] not in referenced_urls
    ]

    if new_referenced_articles:
        logger.info(f"{len(new_referenced_articles)}件の新規参照記事を保存中...")
        firestore_adapter.save_referenced_articles_batch(db, new_referenced_articles)
        logger.info("新規参照記事の保存が完了しました。")
    else:
        logger.info("新規の参照記事はありませんでした。")

    return new_referenced_articles

def process_article_groups(selected_articles: list) -> dict:
    """
    選別された記事から、同一内容の記事をグループ化します

    Args:
        selected_articles (list): 選別された記事のリスト

    Returns:
        dict: グループ化された記事の情報
    """
    logger = logging.getLogger(__name__)
    numbered_articles = []
    article_text = ""

    for i, article in enumerate(selected_articles, 1):
        numbered_articles.append({
            "number": i,
            "title": article["title"],
            "url": article["url"]
        })
        article_text += f"{i}. {article['title']}\n"

    grouping_prompt = get_article_grouping_prompt()
    grouping_response = openai_adapter.openai_chat(
        openai_model="gpt-4o",
        prompt=grouping_prompt + "\n\n" + article_text
    )

    try:
        reasoning_start = grouping_response.find("<reasoning>") + len("<reasoning>")
        reasoning_end = grouping_response.find("</reasoning>")
        grouping_reasoning = grouping_response[reasoning_start:reasoning_end].strip()

        groups_start = grouping_response.find("<grouped_articles>") + len("<grouped_articles>")
        groups_end = grouping_response.find("</grouped_articles>")
        groups_str = grouping_response[groups_start:groups_end].strip()

        groups = json.loads(groups_str)

        logger.info("\nグループ化結果：")
        logger.info(f"\n理由：\n{grouping_reasoning}")
        
        # 各グループの記事を表示
        for group_name, group_info in groups.items():
            if group_name == "others":
                logger.info(f"\n【その他の個別記事】:")
            else:
                logger.info(f"\n【{group_info['title']}】:")
            
            for num in group_info['articles']:
                article = next((a for a in numbered_articles if a["number"] == num), None)
                if article:
                    logger.info(f"- {article['title']}")
                    logger.info(f"  URL: {article['url']}")

        # グループ化された記事の情報を返す
        return {
            "reasoning": grouping_reasoning,
            "groups": groups,
            "articles": numbered_articles
        }

    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"Error processing groups: {str(e)}")
        logger.error(f"Raw response: {grouping_response}")
        return None

def process_article_urls_and_remove_duplicates(grouped_results: dict) -> dict:
    """
    各グループ内の記事のURLを取得し、重複するピックアップ記事を削除します

    Args:
        grouped_results (dict): グループ化された記事の情報

    Returns:
        dict: 重複を除去した記事グループの情報
    """
    logger = logging.getLogger(__name__)
    
    # 全記事のURLとタイトルを保持する辞書
    all_urls = {}
    
    # グループごとに処理
    for group_name, group_info in grouped_results["groups"].items():
        logger.info(f"\n【{group_name}のURL処理を開始】")
        
        # グループ内の記事番号から実際の記事情報を取得
        group_articles = []
        for num in group_info["articles"]:
            article = next((a for a in grouped_results["articles"] if a["number"] == num), None)
            if article:
                # 記事URLからメイン記事とピックアップ記事を取得
                article_urls = yahoo_news_scraper.scrape_article_urls(article["url"])
                
                # メイン記事の情報を保存
                if article_urls["main_article"]:
                    main_article = article_urls["main_article"][0]
                    article_info = {
                        "original_url": article["url"],
                        "main_article": main_article,
                        "pickup_articles": []
                    }
                    
                    # ピックアップ記事の重複チェックと保存
                    for pickup in article_urls["pickup_articles"]:
                        # その他グループの場合は重複チェックを行わない
                        if group_name == "others":
                            article_info["pickup_articles"].append(pickup)
                        else:
                            # メイン記事やピックアップ記事と重複していないか確認
                            if pickup["url"] not in all_urls:
                                article_info["pickup_articles"].append(pickup)
                                all_urls[pickup["url"]] = pickup["title"]
                    
                    # メイン記事のURLを記録
                    all_urls[main_article["url"]] = main_article["title"]
                    group_articles.append(article_info)
                    
                    logger.info(f"処理完了: {article['title']}")
                    logger.info(f"- メイン記事: {main_article['title']}")
                    logger.info(f"- ピックアップ記事数: {len(article_info['pickup_articles'])}件")
        
        # グループの記事情報を更新
        group_info["processed_articles"] = group_articles
    
    return grouped_results

def analyze_individual_article(article: dict, logger: logging.Logger) -> Optional[dict]:
    """
    個別記事の分析を行います

    Args:
        article (dict): 記事情報
        logger (logging.Logger): ロガーインスタンス

    Returns:
        Optional[dict]: 分析結果を含む記事情報。本質情報がない場合はNone
    """
    url = article["main_article"]["url"]
    logger.info(f"記事のスクレイピング: {article['main_article']['title']}")
    
    article_content = None  # 初期値を設定
    
    # URLに基づいて適切なスクレイパーを使用
    if "news.yahoo.co.jp" in url:
        contents = yahoo_news_scraper.scrape_article_contents([url])
        if contents and url in contents:
            article_content = contents[url]
    else:
        contents = web_scraper.scrape_multiple_urls([url],save_json=False,save_markdown=False)
        if contents and url in contents:
            article_content = {
                "title": contents[url].get("title", "タイトルなし"),
                "content": contents[url].get("content", "")
            }
    
    # 記事の内容が取得できた場合、分析を実行
    if article_content:
        # 記事本文を保存
        article["main_article"]["content"] = article_content["content"]

        analysis_result = analyze_individual_article_content(article_content, logger)
        if analysis_result:
            if analysis_result["has_essential_info"]:
                article["analysis"] = analysis_result
                logger.info("分析結果: 本質情報あり")
                logger.info(f"ターゲット顧客: {analysis_result['target_customers']}")
                logger.info(f"本質情報: {analysis_result['extracted_info']}")
                logger.info(f"理由: {analysis_result['reasoning']}")
                return article
            else:
                logger.info("分析結果: 本質情報なし - 記事を除外")
                logger.info(f"理由: {analysis_result['reasoning']}")
                return None
    
    logger.warning("記事の内容が取得できませんでした")
    return None

def analyze_individual_article_content(article_content: dict, logger: logging.Logger) -> Optional[dict]:
    """
    個別記事の内容をAIで分析します

    Args:
        article_content (dict): 分析する記事内容
        logger (logging.Logger): ロガーインスタンス

    Returns:
        Optional[dict]: 分析結果。エラー時はNone
    """
    if not article_content:
        logger.error("記事内容が空です")
        return None

    # 分析用のテキストを準備
    analysis_text = ""
    try:
        title = article_content.get("title", "タイトルなし")
        content_text = article_content.get("content", "")
        analysis_text += f"\n記事:\n"
        analysis_text += f"タイトル: {title}\n"
        analysis_text += f"本文:\n{content_text}\n"
        
        # 第1段階：初期分析
        openai = OpenaiAdapter()
        initial_prompt = get_initial_article_analysis_prompt()
        initial_response = openai.openai_chat(
            openai_model="gpt-4o",
            prompt=initial_prompt + "\n\n" + analysis_text
        )
        
        if not initial_response:
            logger.error("AIからの初期分析の応答が空です")
            return None

        # 分析結果の解析
        initial_result = extract_tagged_json(initial_response, "analysis", logger)
        if not initial_result:
            logger.error("初期分析結果の解析に失敗しました")
            return None

        # 必要なキーの存在確認
        conversation_starter = initial_result.get("conversation_starter", {})
        insurance_relevance = initial_result.get("insurance_relevance", {})
        
        # 第1段階：会話の導入と保険との関連性の確認
        if not (conversation_starter.get("is_appropriate", False) and insurance_relevance.get("is_usable", False)):
            logger.info("初期分析: 会話の導入または保険との関連性が不適切と判断されました")
            reasons = []
            if not conversation_starter.get("is_appropriate", False):
                reasons.append(f"会話の導入として不適切: {conversation_starter.get('reasoning', '理由不明')}")
            if not insurance_relevance.get("is_usable", False):
                reasons.append(f"保険との関連性が不適切: {insurance_relevance.get('reasoning', '理由不明')}")
            return {
                "has_essential_info": False,
                "reasoning": " / ".join(reasons)
            }

        # 第2段階：保険との関連性の再検証
        validation_prompt = get_relevance_validation_prompt().format(
            extracted_info=initial_result.get("extracted_info", ""),
            reasoning=insurance_relevance.get("reasoning", ""),
            conversation_example=insurance_relevance.get("conversation_example", "")
        )
        
        validation_response = openai.openai_chat(
            openai_model="gpt-4o",
            prompt=validation_prompt
        )
        
        if not validation_response:
            logger.error("AIからの検証応答が空です")
            return None

        # 検証結果の解析
        validation_result = extract_tagged_json(validation_response, "validation", logger)
        if not validation_result:
            logger.error("検証結果の解析に失敗しました")
            return None

        if validation_result.get("is_valid", False):
            logger.info("検証結果: 保険商品との関連性が確認されました")
            return {
                "extracted_info": initial_result.get("extracted_info", ""),
                "target_customers": validation_result.get("target_customers", ""),
                "reasoning": validation_result.get("reasoning", ""),
                "has_essential_info": True
            }
        else:
            logger.info("検証結果: 保険商品との関連性が否定されました")
            return {
                "has_essential_info": False,
                "reasoning": validation_result.get("reasoning", "検証失敗")
            }
            
    except Exception as e:
        logger.error(f"分析処理でエラーが発生しました: {str(e)}")
        return None

def extract_tagged_json(response: str, tag: str, logger: logging.Logger) -> Optional[dict]:
    """
    タグで囲まれたJSON文字列を抽出し、辞書に変換します

    Args:
        response (str): レスポンス文字列
        tag (str): 抽出するタグ名
        logger (logging.Logger): ロガーインスタンス

    Returns:
        Optional[dict]: 抽出された辞書。失敗時はNone
    """
    try:
        start_tag = f"<{tag}>"
        end_tag = f"</{tag}>"
        start_idx = response.find(start_tag)
        end_idx = response.find(end_tag)
        
        if start_idx < 0 or end_idx < 0:
            logger.error(f"{tag}タグが見つかりませんでした")
            return None
            
        json_str = response[start_idx + len(start_tag):end_idx].strip()
        return json.loads(json_str)
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON解析エラー: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"予期せぬエラー: {str(e)}")
        return None

def analyze_others_group(group_info: dict, logger: logging.Logger) -> dict:
    """
    その他グループの記事を分析します

    Args:
        group_info (dict): その他グループの情報
        logger (logging.Logger): ロガーインスタンス

    Returns:
        dict: 分析後のグループ情報
    """
    logger.info("\n【その他の記事】の分析を開始")
    analyzed_articles = []
    
    for article in group_info["processed_articles"]:
        analyzed_article = analyze_individual_article(article, logger)
        if analyzed_article:
            analyzed_articles.append(analyzed_article)
    
    group_info["processed_articles"] = analyzed_articles
    return group_info

def analyze_article_group(group_name: str, group_info: dict, logger: logging.Logger) -> Optional[dict]:
    """
    記事グループの分析を行います

    Args:
        group_name (str): グループ名
        group_info (dict): グループ情報
        logger (logging.Logger): ロガーインスタンス

    Returns:
        Optional[dict]: 分析結果を含むグループ情報。
                       othersグループの場合は有効な記事が1つでもあればその記事群を含むグループ情報、
                       それ以外のグループの場合は本質情報があれば記事群を含むグループ情報。
                       どちらの場合も条件を満たさない場合はNone。
    """
    # その他グループは個別に分析
    if group_name == "others":
        analysis_result = analyze_others_group(group_info, logger)
        try:
            # analyze_others_groupで既に無効な記事は除外されているので、
            # 記事が存在するかどうかだけを確認
            if analysis_result.get("processed_articles", []):
                return analysis_result
            return None
        except Exception as e:
            logger.error(f"その他グループの分析中にエラーが発生: {str(e)}")
            return None

    # 以下、通常グループの処理
    logger.info(f"\n【{group_info['title']}】の分析を開始")
    
    # 最新の2件の記事を取得
    latest_articles = group_info.get("processed_articles", [])[:2]
    article_contents = []
    
    for article in latest_articles:
        url = article["main_article"]["url"]
        logger.info(f"記事のスクレイピング: {article['main_article']['title']}")
        
        # URLに基づいて適切なスクレイパーを使用
        if "news.yahoo.co.jp" in url:
            contents = yahoo_news_scraper.scrape_article_contents([url])
            if contents and url in contents:
                article_contents.append(contents[url])
        else:
            contents = web_scraper.scrape_multiple_urls([url],save_json=False,save_markdown=False)
            if contents and url in contents:
                article_contents.append({
                    "title": contents[url].get("title", "タイトルなし"),
                    "content": contents[url].get("content", "")
                })
    
    # 記事の内容が取得できた場合、分析を実行
    if len(article_contents) > 0:
        analysis_result = analyze_article_contents(article_contents, logger)
        if analysis_result:
            if analysis_result["has_essential_info"]:
                group_info["analysis"] = analysis_result
                logger.info("分析結果: 本質情報あり")
                logger.info(f"ターゲット顧客: {analysis_result['target_customers']}")
                logger.info(f"本質情報: {analysis_result['extracted_info']}")
                logger.info(f"理由: {analysis_result['reasoning']}")
                return group_info
            else:
                logger.info("分析結果: 本質情報なし - グループを除外")
                logger.info(f"理由: {analysis_result['reasoning']}")
                return None
    
    logger.warning("記事の内容が取得できませんでした - グループを保持")
    return group_info

def analyze_article_contents(article_contents: List[dict], logger: logging.Logger) -> Optional[dict]:
    """
    記事内容をAIで分析します

    Args:
        article_contents (List[dict]): 分析する記事内容のリスト
        logger (logging.Logger): ロガーインスタンス

    Returns:
        Optional[dict]: 分析結果。エラー時はNone
    """
    if not article_contents:
        logger.error("記事内容が空です")
        return None

    # 分析用のテキストを準備
    analysis_text = ""
    try:
        for i, content in enumerate(article_contents, 1):
            title = content.get("title", "タイトルなし")
            content_text = content.get("content", "")
            analysis_text += f"\n記事{i}:\n"
            analysis_text += f"タイトル: {title}\n"
            analysis_text += f"本文:\n{content_text}\n"
        
        # 第1段階：初期分析
        openai = OpenaiAdapter()
        initial_prompt = get_initial_article_analysis_prompt()
        initial_response = openai.openai_chat(
            openai_model="gpt-4o",
            prompt=initial_prompt + "\n\n" + analysis_text
        )
        
        if not initial_response:
            logger.error("AIからの初期分析の応答が空です")
            return None

        # 分析結果の解析
        initial_result = extract_tagged_json(initial_response, "analysis", logger)
        if not initial_result:
            logger.error("初期分析結果の解析に失敗しました")
            return None

        # 必要なキーの存在確認
        conversation_starter = initial_result.get("conversation_starter", {})
        insurance_relevance = initial_result.get("insurance_relevance", {})
        
        if not (conversation_starter.get("is_appropriate", False) and insurance_relevance.get("is_usable", False)):
            logger.info("初期分析: 会話の導入または保険との関連性が不適切と判断されました")
            reasons = []
            if not conversation_starter.get("is_appropriate", False):
                reasons.append(f"会話の導入として不適切: {conversation_starter.get('reasoning', '理由不明')}")
            if not insurance_relevance.get("is_usable", False):
                reasons.append(f"保険との関連性が不適切: {insurance_relevance.get('reasoning', '理由不明')}")
            return {
                "has_essential_info": False,
                "reasoning": " / ".join(reasons)
            }

        # 第2段階：関連性の検証
        validation_prompt = get_relevance_validation_prompt().format(
            extracted_info=initial_result.get("extracted_info", ""),
            reasoning=insurance_relevance.get("reasoning", ""),
            conversation_example=insurance_relevance.get("conversation_example", "")
        )
        
        validation_response = openai.openai_chat(
            openai_model="gpt-4o",
            prompt=validation_prompt
        )
        
        if not validation_response:
            logger.error("AIからの検証応答が空です")
            return None

        # 検証結果の解析
        validation_result = extract_tagged_json(validation_response, "validation", logger)
        if not validation_result:
            logger.error("検証結果の解析に失敗しました")
            return None

        if validation_result.get("is_valid", False):
            logger.info("検証結果: 保険商品との関連性が確認されました")
            return {
                "extracted_info": initial_result.get("extracted_info", ""),
                "target_customers": validation_result.get("target_customers", ""),
                "reasoning": validation_result.get("reasoning", ""),
                "has_essential_info": True
            }
        else:
            logger.info("検証結果: 保険商品との関連性が否定されました")
            return {
                "has_essential_info": False,
                "reasoning": validation_result.get("reasoning", "検証失敗")
            }
            
    except Exception as e:
        logger.error(f"分析処理でエラーが発生しました: {str(e)}")
        return None

def process_group_article_contents(group_info: dict, logger: logging.Logger) -> str:
    """
    グループ内の記事内容を処理し、必要に応じて要約を行います

    Args:
        group_info (dict): グループ情報
        logger (logging.Logger): ロガーインスタンス

    Returns:
        str: 処理された記事内容
    """
    combined_content = ""
    current_token_count = 0

    # メイン記事の数を確認
    main_articles_count = len(group_info["processed_articles"])
    include_pickups = main_articles_count <= 5

    for article in group_info["processed_articles"]:
        # 処理する記事のリストを作成
        articles_to_process = [article["main_article"]]
        if include_pickups:
            articles_to_process.extend(article["pickup_articles"])

        for target_article in articles_to_process:
            url = target_article["url"]
            logger.info(f"記事のスクレイピング: {target_article['title']}")

            # URLに基づいて適切なスクレイパーを使用
            article_content = ""
            if "news.yahoo.co.jp" in url:
                contents = yahoo_news_scraper.scrape_article_contents([url])
                if contents and url in contents:
                    article_content = contents[url]["content"]
            else:
                contents = web_scraper.scrape_multiple_urls([url], save_json=False, save_markdown=False)
                if contents and url in contents:
                    article_content = contents[url].get("content", "")

            if article_content:
                # 記事内容のトークン数をカウント
                new_content = f"\n【記事タイトル】{target_article['title']}\n{article_content}\n"
                new_content_tokens = count_tokens(new_content)

                # トークン数が20000を超える場合、現在の内容を要約
                if current_token_count + new_content_tokens > 20000 and combined_content:
                    logger.info("トークン数が20000を超えるため、中間要約を実行します")
                    
                    # 要約の実行
                    summarize_prompt = get_article_content_summarize_prompt()
                    summary_response = openai_adapter.openai_chat(
                        openai_model="gpt-4o",
                        prompt=summarize_prompt + "\n\n" + combined_content
                    )
                    
                    # 要約結果の抽出
                    summary_start = summary_response.find("<summary>") + len("<summary>")
                    summary_end = summary_response.find("</summary>")
                    if summary_start >= 0 and summary_end >= 0:
                        combined_content = f"<summary>{summary_response[summary_start:summary_end].strip()}</summary>"
                        current_token_count = count_tokens(combined_content)

                # 新しい内容を追加
                combined_content += new_content
                current_token_count += new_content_tokens

    return combined_content

def process_others_article_contents(article: dict, logger: logging.Logger) -> str:
    """
    othersグループの個別記事の内容を処理し、必要に応じて要約を行います

    Args:
        article (dict): 記事情報
        logger (logging.Logger): ロガーインスタンス

    Returns:
        str: 処理された記事内容
    """
    combined_content = ""
    current_token_count = 0
    
    # メイン記事の処理
    main_article = article["main_article"]
    logger.info(f"メイン記事の処理: {main_article['title']}")
    
    # analyze_individual_article関数ですでに取得済みのメイン記事本文を使用
    if "content" in main_article and main_article["content"]:
        main_article_content = main_article["content"]
        # メイン記事内容を追加
        main_content = f"\n【メイン記事タイトル】{main_article['title']}\n{main_article_content}\n"
        combined_content += main_content
        current_token_count = count_tokens(combined_content)
    else:
        logger.warning(f"メイン記事の内容が見つかりません: {main_article['title']}")
    
    # ピックアップ記事の処理
    pickup_articles = article.get("pickup_articles", [])
    
    # ピックアップ記事がない場合、検索キーワードを生成して情報を取得
    if not pickup_articles and "analysis" in article and "extracted_info" in article["analysis"]:
        logger.info("ピックアップ記事がないため、検索キーワードを生成します")
        
        # 検索キーワードの生成
        extracted_info = article["analysis"]["extracted_info"]
        search_prompt = get_article_search_keywords_prompt().format(extracted_info=extracted_info)
        
        search_response = openai_adapter.openai_chat(
            openai_model="gpt-4o",
            prompt=search_prompt
        )
        
        # 検索キーワードの抽出
        keywords = []
        if search_response:
            start_idx = search_response.find("<search_keywords>") + len("<search_keywords>")
            end_idx = search_response.find("</search_keywords>")
            if start_idx >= 0 and end_idx >= 0:
                keywords_str = search_response[start_idx:end_idx].strip()
                try:
                    keywords = json.loads(keywords_str)
                except Exception as e:
                    logger.error(f"検索キーワードのJSONパースに失敗しました: {e}")
        
        # 検索キーワードを使用してウェブ検索
        if keywords:
            for keyword in keywords[:2]:  # 最大2つのキーワードで検索
                logger.info(f"検索キーワード: {keyword}")
                search_results = web_search.search_and_standardize(
                    query=keyword,
                    max_results=3,
                    scrape_urls=False
                )
                
                if search_results and search_results["search_results"]:
                    for result in search_results["search_results"]:
                        pickup_articles.append({
                            "title": result["title"],
                            "url": result["link"],
                            "snippet": result.get("snippet", "")
                        })

    # ピックアップ記事のスクレイピングと処理
    if pickup_articles:
        logger.info(f"ピックアップ記事数: {len(pickup_articles)}")
        for pickup in pickup_articles:
            pickup_url = pickup["url"]
            logger.info(f"ピックアップ記事のスクレイピング: {pickup['title']}")
            
            # ピックアップ記事のコンテンツを取得
            pickup_content = ""
            if "news.yahoo.co.jp" in pickup_url:
                contents = yahoo_news_scraper.scrape_article_contents([pickup_url])
                if contents and pickup_url in contents:
                    pickup_content = contents[pickup_url]["content"]
            else:
                contents = web_scraper.scrape_multiple_urls([pickup_url], save_json=False, save_markdown=False)
                if contents and pickup_url in contents:
                    pickup_content = contents[pickup_url].get("content", "")
            
            if pickup_content:
                # ピックアップ記事内容のトークン数をカウント
                new_content = f"\n【関連記事タイトル】{pickup['title']}\n{pickup_content}\n"
                new_content_tokens = count_tokens(new_content)
                
                # トークン数が20000を超える場合、現在の内容を要約
                if current_token_count + new_content_tokens > 20000 and combined_content:
                    logger.info("トークン数が20000を超えるため、中間要約を実行します")
                    
                    # 要約の実行
                    summarize_prompt = get_article_content_summarize_prompt()
                    summary_response = openai_adapter.openai_chat(
                        openai_model="gpt-4o",
                        prompt=summarize_prompt + "\n\n" + combined_content
                    )
                    
                    # 要約結果の抽出
                    summary_start = summary_response.find("<summary>") + len("<summary>")
                    summary_end = summary_response.find("</summary>")
                    if summary_start >= 0 and summary_end >= 0:
                        combined_content = f"<summary>{summary_response[summary_start:summary_end].strip()}</summary>"
                        current_token_count = count_tokens(combined_content)
                
                # 新しい内容を追加
                combined_content += new_content
                current_token_count += new_content_tokens
    
    return combined_content

def process_similar_articles(detail_article: dict, logger: logging.Logger) -> dict:
    """
    類似記事の処理を行い、必要に応じて記事を結合します。

    Args:
        detail_article (dict): 処理対象の記事情報
        logger (logging.Logger): ロガーインスタンス

    Returns:
        dict: 処理後の記事情報
    """
    try:
        # ベクトル表現の取得
        embedding = openai_adapter.embedding([detail_article['target_customers']])[0]
        detail_article['embedding'] = embedding

        # 類似度検索の実行（類似度付きで結果が返される）
        similar_articles = firestore_adapter.get_valid_essential_info(db, query_vector=embedding)
        
        # 類似度0.7以上の記事を処理
        articles_to_merge = []
        articles_to_delete = []
        
        for article in similar_articles:
            # get_valid_essential_infoから返される類似度を使用
            similarity = article.get('similarity', 0)
            
            if similarity >= 0.65:
                # 類似性チェック用のプロンプト生成
                check_prompt = get_article_similarity_check_prompt().format(
                    title1=detail_article['title'],
                    content1=detail_article['content'],
                    title2=article['title'],
                    content2=article['content']
                )
                
                # AIによる類似性判断
                check_response = openai_adapter.openai_chat(
                    openai_model="gpt-4o",
                    prompt=check_prompt
                )
                
                if check_response:
                    check_start = check_response.find("<similarity_check>")
                    check_end = check_response.find("</similarity_check>")
                    
                    if check_start >= 0 and check_end >= 0:
                        check_json = check_response[check_start + len("<similarity_check>"):check_end].strip()
                        check_result = json.loads(check_json)
                        
                        if check_result.get('is_similar'):
                            articles_to_merge.append(article)
                            articles_to_delete.append({
                                'title': article['title'],
                                'content': article['content']
                            })
        
        # 類似記事がある場合は結合処理を実行
        if articles_to_merge:
            # 結合用の記事情報を準備
            articles_info = [
                {
                    'title': detail_article['title'],
                    'content': detail_article['content'],
                    "target_customers": detail_article['target_customers'],
                    'usage_example': detail_article['usage_example']
                }
            ]
            articles_info.extend([{
                'title': article['title'],
                'content': article['content'],
                'target_customers': article['target_customers'],
                'usage_example': article['usage_example']
            } for article in articles_to_merge])
            
            # 結合用のプロンプト生成
            merge_prompt = get_article_merge_prompt().format(
                articles_info=json.dumps(articles_info, ensure_ascii=False, indent=2)
            )
            
            # AIによる記事結合
            merge_response = openai_adapter.openai_chat(
                openai_model="gpt-4o",
                prompt=merge_prompt
            )
            
            if merge_response:
                merge_start = merge_response.find("<merged_article>")
                merge_end = merge_response.find("</merged_article>")
                
                if merge_start >= 0 and merge_end >= 0:
                    merge_json = merge_response[merge_start + len("<merged_article>"):merge_end].strip()
                    merged_article = json.loads(merge_json)
                    
                    # 新しいベクトル表現の取得
                    new_embedding = openai_adapter.embedding([merged_article['usage_example']])[0]
                    
                    # 結合結果で元の記事情報を更新
                    detail_article.update({
                        'title': merged_article['title'],
                        'content': merged_article['content'],
                        'usage_example': merged_article['usage_example'],
                        'target_customers': merged_article['target_customers'],
                        'embedding': new_embedding
                    })
                    
                    # 古い記事の削除
                    firestore_adapter.delete_essential_info_batch(db, articles_to_delete)
                    
                    logger.info(f"記事を結合しました: {detail_article['title']}")
    
    except Exception as e:
        logger.error(f"類似記事の処理中にエラーが発生しました: {e}")
    
    return detail_article

def generate_detail_article(combined_content: str, extracted_info: str, logger: logging.Logger) -> dict:
    """
    記事の詳細情報を生成し、類似記事との結合処理を行います。

    Args:
        combined_content (str): 結合された記事内容
        extracted_info (str): 抽出された本質的な情報
        logger (logging.Logger): ロガーインスタンス

    Returns:
        dict: 生成された詳細記事情報
    """
    if not combined_content or not extracted_info:
        logger.error("記事内容または抽出情報が空です")
        return None

    # プロンプトの準備
    detail_prompt = get_article_detail_prompt().format(
        extracted_info=extracted_info,
        combined_content=combined_content
    )
    
    # AIによる詳細情報記事の生成
    detail_response = openai_adapter.openai_chat(
        openai_model="gpt-4o",
        prompt=detail_prompt
    )
    
    # 生成結果の解析
    if not detail_response:
        logger.error("AIからの応答が空です")
        return None

    # タグの位置を特定
    detail_start = detail_response.find("<detail_article>")
    detail_end = detail_response.find("</detail_article>")
    
    if detail_start < 0 or detail_end < 0:
        logger.error("AIの応答から必要なタグが見つかりませんでした")
        return None
        
    # タグの中身を抽出
    detail_json = detail_response[detail_start + len("<detail_article>"):detail_end].strip()
    
    try:
        detail_article = json.loads(detail_json)
        
        # 必要なキーの存在確認
        required_keys = ["title", "content", "target_customers", "usage_example"]
        if not all(key in detail_article for key in required_keys):
            logger.error("生成された記事に必要な情報が含まれていません")
            return None
        
        # 類似記事の処理
        detail_article = process_similar_articles(detail_article, logger)
            
        return detail_article
            
    except json.JSONDecodeError as e:
        logger.error(f"JSON解析エラー: {e}")
        return None
    except Exception as e:
        logger.error(f"予期せぬエラー: {e}")
        return None

def analyze_article_groups(processed_results: dict, logger: logging.Logger) -> dict:
    """
    全ての記事グループを分析します

    Args:
        processed_results (dict): 処理済みの記事グループ情報
        logger (logging.Logger): ロガーインスタンス

    Returns:
        dict: 分析後の記事グループ情報
    """
    logger.info("\n記事グループの分析を開始します...")
    analyzed_groups = {}
    
    for group_name, group_info in processed_results["groups"].items():
        analyzed_group = analyze_article_group(group_name, group_info, logger)
        if analyzed_group:
            # グループ名に応じて適切な処理を実行
            if group_name == "others":
                logger.info("\n【その他の記事】の記事内容の処理を開始")
                # othersグループの各記事を個別に処理
                for i, article in enumerate(analyzed_group["processed_articles"]):
                    logger.info(f"\n個別記事 {i+1}/{len(analyzed_group['processed_articles'])} の処理を開始")
                    combined_content = process_others_article_contents(article, logger)
                    article["combined_content"] = combined_content
                    
                    # 詳細情報記事の生成
                    if "analysis" in article and "extracted_info" in article["analysis"]:
                        detail_article = generate_detail_article(
                            combined_content,
                            article["analysis"]["extracted_info"],
                            logger
                        )
                        if detail_article:
                            article["detail_article"] = detail_article
            else:
                logger.info(f"\n【{group_info['title']}】の記事内容の処理を開始")
                combined_content = process_group_article_contents(analyzed_group, logger)
                analyzed_group["combined_content"] = combined_content
                
                # グループの詳細情報記事の生成
                if "analysis" in analyzed_group and "extracted_info" in analyzed_group["analysis"]:
                    detail_article = generate_detail_article(
                        combined_content,
                        analyzed_group["analysis"]["extracted_info"],
                        logger
                    )
                    if detail_article:
                        analyzed_group["detail_article"] = detail_article
                        
            analyzed_groups[group_name] = analyzed_group
    
    processed_results["groups"] = analyzed_groups
    return processed_results

def determine_retention_periods(articles: list, logger: logging.Logger) -> list:
    """
    記事の保持期間を判断します

    Args:
        articles (list): 判断対象の記事リスト
        logger (logging.Logger): ロガーインスタンス

    Returns:
        list: 保持期間が設定された記事リスト
    """
    logger.info("\n記事の保持期間の判断を開始します...")
    
    # 記事を5個ずつのバッチに分割
    batch_size = 5
    for i in range(0, len(articles), batch_size):
        batch = articles[i:i + batch_size]
        
        # 判断用のテキストを準備
        article_text = ""
        for j, article in enumerate(batch, 1):
            article_text += f"{j}. {article['title']}\n"
        
        # AIによる判断
        retention_prompt = get_article_retention_period_prompt()
        retention_response = openai_adapter.openai_chat(
            openai_model="gpt-4o",
            prompt=retention_prompt + "\n\n" + article_text
        )
        
        try:
            # 判断結果の解析
            periods_start = retention_response.find("<retention_periods>") + len("<retention_periods>")
            periods_end = retention_response.find("</retention_periods>")
            periods_json = retention_response[periods_start:periods_end].strip()
            periods_data = json.loads(periods_json)
            
            # 各記事に保持期間を設定
            for period_info in periods_data["article_periods"]:
                article_idx = period_info["number"] - 1
                if 0 <= article_idx < len(batch):
                    batch[article_idx]["retention_period_days"] = period_info["days"]
                    logger.info(f"記事「{batch[article_idx]['title']}」の保持期間: {period_info['days']}日")
                    logger.info(f"理由: {period_info['reasoning']}")
        
        except Exception as e:
            logger.error(f"保持期間の判断中にエラーが発生しました: {e}")
            # エラーが発生した場合はデフォルトの保持期間（7日）を設定
            for article in batch:
                article["retention_period_days"] = 7
    
    return articles

def process_and_save_articles(analyzed_results: dict, logger: logging.Logger):
    """
    記事の処理と保存を行います

    Args:
        analyzed_results (dict): 分析済みの記事グループ情報
        logger (logging.Logger): ロガーインスタンス
    """
    logger.info("\n記事の処理と保存を開始します...")
    
    # 保存対象の記事を収集
    articles_to_save = []
    
    for group_name, group_info in analyzed_results["groups"].items():
        if group_name == "others":
            # othersグループは記事ごとに処理
            for article in group_info["processed_articles"]:
                if "detail_article" in article:
                    articles_to_save.append(article["detail_article"])
        else:
            # 通常のグループは1つの記事として処理
            if "detail_article" in group_info:
                articles_to_save.append(group_info["detail_article"])
    
    if articles_to_save:
        # 保持期間の判断
        articles_with_periods = determine_retention_periods(articles_to_save, logger)
        
        # データベースへの保存
        logger.info(f"\n{len(articles_with_periods)}件の記事をデータベースに保存します...")
        firestore_adapter.save_essential_info_batch(db, articles_with_periods)
        logger.info("記事の保存が完了しました")

def display_analysis_results(processed_results: dict, logger: logging.Logger):
    """
    処理結果を表示します

    Args:
        processed_results (dict): 処理済みの記事グループ情報
        logger (logging.Logger): ロガーインスタンス
    """
    logger.info("\n処理結果のサマリー：")
    
    for group_name, group_info in processed_results["groups"].items():
        if group_name == "others":
            logger.info("\n【個別記事グループ】")
            for article in group_info["processed_articles"]:
                logger.info(f"\nメイン記事：{article['main_article']['title']}")
                logger.info(f"URL：{article['main_article']['url']}")
                
                if "analysis" in article:
                    logger.info("\n分析結果:")
                    logger.info(f"判断理由: {article['analysis']['reasoning']}")
                    if "extracted_info" in article["analysis"]:
                        logger.info("\n抽出された情報:")
                        logger.info(article["analysis"]["extracted_info"])
                
                if article['pickup_articles']:
                    logger.info(f"\n関連記事（{len(article['pickup_articles'])}件）：")
                    for pickup in article['pickup_articles']:
                        logger.info(f"- {pickup['title']}")
                        logger.info(f"  URL：{pickup['url']}")
                else:
                    logger.info("\n関連記事：なし")
                
                if "combined_content" in article:
                    logger.info("\n記事内容の要約：")
                    logger.info(article["combined_content"])
                
                if "detail_article" in article:
                    logger.info("\n生成された詳細情報記事：")
                    logger.info(f"タイトル：{article['detail_article']['title']}")
                    logger.info(f"本文：\n{article['detail_article']['content']}")
                    logger.info(f"アイスブレイクとしての活用方法：\n{article['detail_article']['usage_example']}")
                    if "retention_period_days" in article["detail_article"]:
                        logger.info(f"保持期間：{article['detail_article']['retention_period_days']}日")
                
                logger.info("-" * 80)
        else:
            logger.info(f"\n【{group_info['title']}】")
            if "analysis" in group_info:
                logger.info("\n分析結果:")
                logger.info(f"判断理由: {group_info['analysis']['reasoning']}")
                if "extracted_info" in group_info["analysis"]:
                    logger.info("\n抽出された情報:")
                    logger.info(group_info["analysis"]["extracted_info"])
            
            logger.info("\n記事一覧：")
            for article in group_info["processed_articles"]:
                logger.info(f"\nメイン記事：{article['main_article']['title']}")
                logger.info(f"URL：{article['main_article']['url']}")
                
                if article['pickup_articles']:
                    logger.info(f"\n関連記事（{len(article['pickup_articles'])}件）：")
                    for pickup in article['pickup_articles']:
                        logger.info(f"- {pickup['title']}")
                        logger.info(f"  URL：{pickup['url']}")
                else:
                    logger.info("\n関連記事：なし")
            
            if "combined_content" in group_info:
                logger.info("\n記事内容の要約：")
                logger.info(group_info["combined_content"])
            
            if "detail_article" in group_info:
                logger.info("\n生成された詳細情報記事：")
                logger.info(f"タイトル：{group_info['detail_article']['title']}")
                logger.info(f"本文：\n{group_info['detail_article']['content']}")
                logger.info(f"アイスブレイクとしての活用方法：\n{group_info['detail_article']['usage_example']}")
                if "retention_period_days" in group_info["detail_article"]:
                    logger.info(f"保持期間：{group_info['detail_article']['retention_period_days']}日")
            
            logger.info("-" * 80)

# contentに日付や情報源、時系列の情報が含まれていないため、信頼感の無い情報にみえる
# 保険に活用できる話題かどうかの見積もりが甘く、飛躍した関連性を見出してい待っている
# referenced_articlesにデータが保存されていない　→　修正済み。テスト未実施
# usage_exampleが「どういった顧客に」の部分を「社会保障に興味がある顧客」のように具体性を伴わない手抜きの情報にしている
# →　各プロンプトの見直しが必要

def main():
    """メイン処理"""
    setup_logging()
    logger = logging.getLogger(__name__)

    try:
        # 記事収集パイプライン
        scraped_articles = scrape_news_articles()
        new_articles = filter_new_articles(scraped_articles)

        if new_articles:
            # 新規記事の保存
            firestore_adapter.save_discovered_articles_batch(db, new_articles)
            logger.info(f"Saved {len(new_articles)} new articles in batch")

            # 記事の選別と処理
            selected_articles = select_relevant_articles(new_articles)
            if selected_articles:
                # 記事のグループ化と分析
                grouped_results = process_article_groups(selected_articles)
                if grouped_results:
                    # 記事URLの処理と重複除去
                    processed_results = process_article_urls_and_remove_duplicates(grouped_results)
                    
                    # 記事グループの分析
                    analyzed_results = analyze_article_groups(processed_results, logger)
                    

                    # 結果の表示
                    # display_analysis_results(analyzed_results, logger)
                    
                    # 記事の処理と保存
                    process_and_save_articles(analyzed_results, logger)

    except Exception as e:
        logger.error(f"Error occurred: {str(e)}", exc_info=True)
        raise

if __name__ == "__main__":
    main() 
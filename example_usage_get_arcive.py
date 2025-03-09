from src.chat.openai_adapter import OpenaiAdapter
from src.chat.get_prompt import (
    get_customer_info_analysis_prompt,
    get_icebreak_suggestion_prompt,
    get_search_keywords_prompt,
    get_web_research_summarize_prompt,
    get_article_selection_prompt,
    get_article_grouping_prompt,
    get_article_group_analysis_prompt,
    get_individual_article_analysis_prompt,
    get_article_content_summarize_prompt,
    get_article_search_keywords_prompt,
    get_article_detail_prompt
)
from src.websearch.web_search import WebSearch
from src.tiktoken import count_tokens
import json
from dotenv import load_dotenv
import os
import time
import logging
from src.webscraping.yahoo_news_scraper import YahooNewsScraper
import json
import firebase_admin
from firebase_admin import firestore
from firebase_admin import credentials
from src.firestore.firestore_adapter import FirestoreAdapter 
from pathlib import Path
from src.webscraping.web_scraping import WebScraper
from typing import List, Optional

# 認証情報のパスを設定
credentials_path = str(Path("secret-key") / f"{os.getenv('CLOUD_FIRESTORE_JSON')}.json")
cred = credentials.Certificate(credentials_path)
app = firebase_admin.initialize_app(cred)
db = firestore.client()


# 開発対象

# 保険に関連する可能性のある記事を蓄積する機能を考える
# アイスブレイク用のニュース記事収集システム
# ・スクレイピング先のサイトを選定しておく
# yahoo newsをスクレイピングする → 国内、国際、経済の3トピック
# ・スクレイピング結果から、ニュース記事(とURL)を選定する→AI使用
# 詳細
# ・全ページの記事を取得
# ・記事のタイトルとURLを取得
# ・データベースで取得済みの記事を除外する → 過去に一度でも取得した記事は除外する
# ・AIで関係しそうな記事の選択
# ・選択した記事のタイトルとURLをデータベースに保存
# ・記事の選定を行う → 記事の内容被り対策
# 特定のURLから「・・・記事全文を読む」のURLを取得
# 同様のページから、関連記事のURLを取得

# グループトピックについて
# 2つだけ記事を読み込んで、本質情報が含まれているかを判断する
# 含まれていない場合、そのグループトピックは除外する
# 含まれている場合、以下の処理を行う
# 同じグループの記事数が複数ある場合、被るサブトピックは全て排除する
# →　5件以下の場合はサブトピックを含め、全件を分割読込して、本質情報を抽出する　→　最後に本質情報について十分な情報があるかも判断し、無い場合は検索キーワードの抽出、検索による補完
# →　5件以上の場合は、サブトピックを除外し、全件を分割読込して、本質情報を抽出する
# 単体トピックについて
# →　メイントピックの記事のみを読み込んで、保険営業アイスブレイクに使える時事ネタを得たいという視点における本質情報が記事に存在するかを分析する
# →　存在し、サブトピックがある場合は、メインとサブの両方を読み込んでAIによる本質情報の抽出を行う。十分な情報があるかどうかも同時に判断し、十分な情報がない場合は、検索キーワードの抽出、検索による補完
# →　存在し、サブトピックがない場合は、本質情報について検索キーワードをAI生成し、検索結果のスクレイピングで、対象情報を整理する



# ・各グループまたは各記事毎に取得した本質情報(extracted_info)と全文情報(combined_content)をAIに渡して、詳細な本質情報を生成
# ・情報についてベクトル埋め込みを行い、データベース上を検索して、類似情報を取得(0.7>あたり)
# ・同一の時系列情報だった場合は、新たに追記と古い情報の削除による更新データをAIで生成
# ・今回作成された本質情報を、一斉に保存期間をAIに判断させて、データベースに保存

# 使用時
# ・ユーザーの入力情報を基にベクトル検索
# ・理由を添えて本質情報を選定
# ・記事毎にアイスブレイク用のテキストを生成

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

def scrape_news_articles(yns: YahooNewsScraper) -> dict:
    """
    Yahoo Newsから記事をスクレイピングします

    Args:
        yns (YahooNewsScraper): YahooNewsScraperインスタンス

    Returns:
        dict: カテゴリごとの記事リスト
    """
    logger = logging.getLogger(__name__)
    logger.info("Starting to scrape Yahoo News categories...")
    return yns.scrape_all_categories(save_results=True)

def filter_new_articles(articles_by_category: dict, fa: FirestoreAdapter) -> list:
    """
    既存の記事を除外し、新規記事のみをフィルタリングします

    Args:
        articles_by_category (dict): カテゴリごとの記事リスト
        fa (FirestoreAdapter): FirestoreAdapterインスタンス

    Returns:
        list: 新規記事のリスト
    """
    logger = logging.getLogger(__name__)
    logger.info("Fetching existing articles from Firestore...")
    existing_articles = fa.get_discovered_articles(db)
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

    openai = OpenaiAdapter()
    selection_prompt = get_article_selection_prompt()
    selection_response = openai.openai_chat(
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
        list: 選別された記事のリスト
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

    return all_selected_articles

def save_new_referenced_articles(selected_articles: list, fa: FirestoreAdapter):
    """
    選別された新規記事を参照記事として保存します

    Args:
        selected_articles (list): 選別された記事のリスト
        fa (FirestoreAdapter): FirestoreAdapterインスタンス
    """
    logger = logging.getLogger(__name__)
    if not selected_articles:
        return

    logger.info("過去の参照記事を取得中...")
    referenced_articles = fa.get_referenced_articles(db)
    referenced_urls = {article['url'] for article in referenced_articles}

    new_referenced_articles = [
        article for article in selected_articles
        if article['url'] not in referenced_urls
    ]

    if new_referenced_articles:
        logger.info(f"{len(new_referenced_articles)}件の新規参照記事を保存中...")
        fa.save_referenced_articles_batch(db, new_referenced_articles)
        logger.info("新規参照記事の保存が完了しました。")
    else:
        logger.info("新規の参照記事はありませんでした。")

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

    openai = OpenaiAdapter()
    grouping_prompt = get_article_grouping_prompt()
    grouping_response = openai.openai_chat(
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

def process_article_urls_and_remove_duplicates(grouped_results: dict, yns: YahooNewsScraper) -> dict:
    """
    各グループ内の記事のURLを取得し、重複するピックアップ記事を削除します

    Args:
        grouped_results (dict): グループ化された記事の情報
        yns (YahooNewsScraper): YahooNewsScraperインスタンス

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
                article_urls = yns.scrape_article_urls(article["url"])
                
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

def analyze_individual_article(article: dict, yns: YahooNewsScraper, web_scraper: WebScraper, logger: logging.Logger) -> Optional[dict]:
    """
    個別記事の分析を行います

    Args:
        article (dict): 記事情報
        yns (YahooNewsScraper): YahooNewsScraperインスタンス
        web_scraper (WebScraper): WebScraperインスタンス
        logger (logging.Logger): ロガーインスタンス

    Returns:
        Optional[dict]: 分析結果を含む記事情報。本質情報がない場合はNone
    """
    url = article["main_article"]["url"]
    logger.info(f"記事のスクレイピング: {article['main_article']['title']}")
    
    # URLに基づいて適切なスクレイパーを使用
    if "news.yahoo.co.jp" in url:
        contents = yns.scrape_article_contents([url])
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
    # 分析用のテキストを準備
    analysis_text = f"タイトル: {article_content['title']}\n"
    analysis_text += f"本文:\n{article_content['content']}"
    
    # AIによる分析
    try:
        openai = OpenaiAdapter()
        analysis_prompt = get_individual_article_analysis_prompt()
        analysis_response = openai.openai_chat(
            openai_model="gpt-4o",
            prompt=analysis_prompt + "\n\n" + analysis_text
        )
        
        # 分析結果の解析
        analysis_start = analysis_response.find("<analysis>") + len("<analysis>")
        analysis_end = analysis_response.find("</analysis>")
        return json.loads(analysis_response[analysis_start:analysis_end].strip())
    except Exception as e:
        logger.error(f"分析処理でエラーが発生しました: {str(e)}")
        return None

def analyze_others_group(group_info: dict, yns: YahooNewsScraper, web_scraper: WebScraper, logger: logging.Logger) -> dict:
    """
    その他グループの記事を分析します

    Args:
        group_info (dict): その他グループの情報
        yns (YahooNewsScraper): YahooNewsScraperインスタンス
        web_scraper (WebScraper): WebScraperインスタンス
        logger (logging.Logger): ロガーインスタンス

    Returns:
        dict: 分析後のグループ情報
    """
    logger.info("\n【その他の記事】の分析を開始")
    analyzed_articles = []
    
    for article in group_info["processed_articles"]:
        analyzed_article = analyze_individual_article(article, yns, web_scraper, logger)
        if analyzed_article:
            analyzed_articles.append(analyzed_article)
    
    group_info["processed_articles"] = analyzed_articles
    return group_info

def analyze_article_group(group_name: str, group_info: dict, yns: YahooNewsScraper, web_scraper: WebScraper, logger: logging.Logger) -> Optional[dict]:
    """
    記事グループの分析を行います

    Args:
        group_name (str): グループ名
        group_info (dict): グループ情報
        yns (YahooNewsScraper): YahooNewsScraperインスタンス
        web_scraper (WebScraper): WebScraperインスタンス
        logger (logging.Logger): ロガーインスタンス

    Returns:
        Optional[dict]: 分析結果を含むグループ情報。本質情報がない場合はNone
    """
    # その他グループは個別に分析
    if group_name == "others":
        return analyze_others_group(group_info, yns, web_scraper, logger)

    logger.info(f"\n【{group_info['title']}】の分析を開始")
    
    # 最新の2件の記事を取得
    latest_articles = group_info["processed_articles"][:2]
    article_contents = []
    
    for article in latest_articles:
        url = article["main_article"]["url"]
        logger.info(f"記事のスクレイピング: {article['main_article']['title']}")
        
        # URLに基づいて適切なスクレイパーを使用
        if "news.yahoo.co.jp" in url:
            contents = yns.scrape_article_contents([url])
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
    # 分析用のテキストを準備
    analysis_text = ""
    for i, content in enumerate(article_contents, 1):
        analysis_text += f"\n記事{i}:\n"
        analysis_text += f"タイトル: {content['title']}\n"
        analysis_text += f"本文:\n{content['content']}\n"
    
    # AIによる分析
    try:
        openai = OpenaiAdapter()
        analysis_prompt = get_article_group_analysis_prompt()
        analysis_response = openai.openai_chat(
            openai_model="gpt-4o",
            prompt=analysis_prompt + "\n\n" + analysis_text
        )
        
        # 分析結果の解析
        analysis_start = analysis_response.find("<analysis>") + len("<analysis>")
        analysis_end = analysis_response.find("</analysis>")
        return json.loads(analysis_response[analysis_start:analysis_end].strip())
    except Exception as e:
        logger.error(f"分析処理でエラーが発生しました: {str(e)}")
        return None

def process_group_article_contents(group_info: dict, yns: YahooNewsScraper, web_scraper: WebScraper, logger: logging.Logger) -> str:
    """
    グループ内の記事内容を処理し、必要に応じて要約を行います

    Args:
        group_info (dict): グループ情報
        yns (YahooNewsScraper): YahooNewsScraperインスタンス
        web_scraper (WebScraper): WebScraperインスタンス
        logger (logging.Logger): ロガーインスタンス

    Returns:
        str: 処理された記事内容
    """
    from src.tiktoken.token_counter import count_tokens
    from src.chat.get_prompt import get_article_content_summarize_prompt
    from src.chat.openai_adapter import OpenaiAdapter

    combined_content = ""
    current_token_count = 0
    openai = OpenaiAdapter()

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
                contents = yns.scrape_article_contents([url])
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
                    summary_response = openai.openai_chat(
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

def process_others_article_contents(article: dict, yns: YahooNewsScraper, web_scraper: WebScraper, logger: logging.Logger) -> str:
    """
    othersグループの個別記事の内容を処理し、必要に応じて要約を行います

    Args:
        article (dict): 記事情報
        yns (YahooNewsScraper): YahooNewsScraperインスタンス
        web_scraper (WebScraper): WebScraperインスタンス
        logger (logging.Logger): ロガーインスタンス

    Returns:
        str: 処理された記事内容
    """
    from src.tiktoken.token_counter import count_tokens
    from src.chat.get_prompt import get_article_content_summarize_prompt, get_article_search_keywords_prompt
    from src.chat.openai_adapter import OpenaiAdapter
    from src.websearch.web_search import WebSearch

    combined_content = ""
    current_token_count = 0
    openai = OpenaiAdapter()
    
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
        
        search_response = openai.openai_chat(
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
                    import json
                    keywords = json.loads(keywords_str)
                except Exception as e:
                    logger.error(f"検索キーワードのJSONパースに失敗しました: {e}")
        
        # 検索キーワードを使用してウェブ検索
        if keywords:
            web_search = WebSearch()
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
                contents = yns.scrape_article_contents([pickup_url])
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
                    summary_response = openai.openai_chat(
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

def generate_detail_article(combined_content: str, extracted_info: str, openai: OpenaiAdapter, logger: logging.Logger) -> dict:
    """
    記事内容から詳細な情報記事を生成します

    Args:
        combined_content (str): 記事の結合内容
        extracted_info (str): 抽出された本質的な情報
        openai (OpenaiAdapter): OpenAIアダプターインスタンス
        logger (logging.Logger): ロガーインスタンス

    Returns:
        dict: 生成された詳細情報記事
    """
    try:
        # 入力値の検証
        if not combined_content or not extracted_info:
            logger.error("記事内容または抽出情報が空です")
            return None

        # プロンプトの準備
        detail_prompt = get_article_detail_prompt().format(
            extracted_info=extracted_info,
            combined_content=combined_content
        )
        
        # AIによる詳細情報記事の生成
        detail_response = openai.openai_chat(
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
            import json
            detail_article = json.loads(detail_json)
            
            # 必要なキーの存在確認
            required_keys = ["title", "content", "icebreak_usage"]
            if not all(key in detail_article for key in required_keys):
                logger.error("生成された記事に必要な情報が含まれていません")
                return None
                
            logger.info("詳細情報記事の生成が完了しました")
            return detail_article
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析エラー: {str(e)}")
            return None
            
    except Exception as e:
        logger.error(f"詳細情報記事の生成中にエラーが発生しました: {str(e)}")
        return None

def analyze_article_groups(processed_results: dict, yns: YahooNewsScraper, logger: logging.Logger) -> dict:
    """
    全ての記事グループを分析します

    Args:
        processed_results (dict): 処理済みの記事グループ情報
        yns (YahooNewsScraper): YahooNewsScraperインスタンス
        logger (logging.Logger): ロガーインスタンス

    Returns:
        dict: 分析後の記事グループ情報
    """
    logger.info("\n記事グループの分析を開始します...")
    web_scraper = WebScraper()
    analyzed_groups = {}
    openai = OpenaiAdapter()
    
    for group_name, group_info in processed_results["groups"].items():
        analyzed_group = analyze_article_group(group_name, group_info, yns, web_scraper, logger)
        if analyzed_group:
            # グループ名に応じて適切な処理を実行
            if group_name == "others":
                logger.info("\n【その他の記事】の記事内容の処理を開始")
                # othersグループの各記事を個別に処理
                for i, article in enumerate(analyzed_group["processed_articles"]):
                    logger.info(f"\n個別記事 {i+1}/{len(analyzed_group['processed_articles'])} の処理を開始")
                    combined_content = process_others_article_contents(article, yns, web_scraper, logger)
                    article["combined_content"] = combined_content
                    
                    # 詳細情報記事の生成
                    if "analysis" in article and "extracted_info" in article["analysis"]:
                        detail_article = generate_detail_article(
                            combined_content,
                            article["analysis"]["extracted_info"],
                            openai,
                            logger
                        )
                        if detail_article:
                            article["detail_article"] = detail_article
            else:
                logger.info(f"\n【{group_info['title']}】の記事内容の処理を開始")
                combined_content = process_group_article_contents(analyzed_group, yns, web_scraper, logger)
                analyzed_group["combined_content"] = combined_content
                
                # グループの詳細情報記事の生成
                if "analysis" in analyzed_group and "extracted_info" in analyzed_group["analysis"]:
                    detail_article = generate_detail_article(
                        combined_content,
                        analyzed_group["analysis"]["extracted_info"],
                        openai,
                        logger
                    )
                    if detail_article:
                        analyzed_group["detail_article"] = detail_article
                        
            analyzed_groups[group_name] = analyzed_group
    
    processed_results["groups"] = analyzed_groups
    return processed_results

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
            logger.info(f"\n【個別記事グループ】")
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
                    logger.info("関連記事：なし")
                
                # 記事内容の要約を表示
                if "combined_content" in article:
                    logger.info("\n記事内容の要約：")
                    logger.info(article["combined_content"])
                # 詳細情報記事の表示
                if "detail_article" in article:
                    logger.info("\n生成された詳細情報記事：")
                    logger.info(f"タイトル：{article['detail_article']['title']}")
                    logger.info(f"\n本文：\n{article['detail_article']['content']}")
                    logger.info(f"\nアイスブレイクとしての活用方法：\n{article['detail_article']['icebreak_usage']}")
                
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
                    logger.info("関連記事：なし")
            
            if "combined_content" in group_info:
                logger.info("\n記事内容の要約：")
                logger.info(group_info["combined_content"])
            # 詳細情報記事の表示
            if "detail_article" in group_info:
                logger.info("\n生成された詳細情報記事：")
                logger.info(f"タイトル：{group_info['detail_article']['title']}")
                logger.info(f"\n本文：\n{group_info['detail_article']['content']}")
                logger.info(f"\nアイスブレイクとしての活用方法：\n{group_info['detail_article']['icebreak_usage']}")
            
            logger.info("-" * 80)

def main():
    """メイン処理"""
    setup_logging()
    logger = logging.getLogger(__name__)

    try:
        # 初期化
        yns = YahooNewsScraper()
        fa = FirestoreAdapter()

        # 記事収集パイプライン
        scraped_articles = scrape_news_articles(yns)
        new_articles = filter_new_articles(scraped_articles, fa)

        if new_articles:
            # 新規記事の保存
            fa.save_discovered_articles_batch(db, new_articles)
            logger.info(f"Saved {len(new_articles)} new articles in batch")

            # 記事の選別と処理
            selected_articles = select_relevant_articles(new_articles)
            if selected_articles:
                # 選択された記事をDB保存
                
                # 記事のグループ化と分析
                grouped_results = process_article_groups(selected_articles)
                if grouped_results:
                    # 記事URLの処理と重複除去
                    processed_results = process_article_urls_and_remove_duplicates(grouped_results, yns)
                    
                    # 記事グループの分析
                    analyzed_results = analyze_article_groups(processed_results, yns, logger)
                    
                    # 結果の表示
                    display_analysis_results(analyzed_results, logger)

    except Exception as e:
        logger.error(f"Error occurred: {str(e)}", exc_info=True)
        raise

if __name__ == "__main__":
    main() 
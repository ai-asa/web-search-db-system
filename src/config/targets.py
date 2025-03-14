"""
スクレイピング対象のサイトとその設定を管理するモジュール
"""

# Yahoo!ニュースの設定
YAHOO_NEWS = {
    "国内": {
        "base_url": "https://news.yahoo.co.jp/topics/domestic",
        "feed_selector": "#uamods-topics > ul"
    },
    "国際": {
        "base_url": "https://news.yahoo.co.jp/topics/world",
        "feed_selector": "#uamods-topics > ul"
    },
    "経済": {
        "base_url": "https://news.yahoo.co.jp/topics/business",
        "feed_selector": "#uamods-topics > ul"
    }
}

# スクレイピングの設定
SCRAPING_CONFIG = {
    "page_pattern": "?page={}",   # ページネーションのパターン
    "article_selectors": {
        "title": "#uamods > header > h1",
        "body": "#uamods > div.article_body.highLightSearchTarget"
    }
}

def get_yahoo_news_config():
    """Yahoo!ニュースの設定を取得する"""
    return YAHOO_NEWS

def get_scraping_config():
    """スクレイピングの設定を取得する"""
    return SCRAPING_CONFIG
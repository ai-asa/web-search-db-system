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
}

def get_yahoo_news_config():
    """Yahoo!ニュースの設定を取得する"""
    return YAHOO_NEWS

def get_scraping_config():
    """スクレイピングの設定を取得する"""
    return SCRAPING_CONFIG

# ココがポイントの記事があればスクレイピングする
# 本質情報の検索キーワードでウェブサイトを検索して、ヒットしたものをスクレイピング

#uamods-pickup > div.sc-gdv5m1-0.cuVskI
#uamods-pickup > section > ul
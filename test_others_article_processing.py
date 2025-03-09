import unittest
import logging
import json
import sys
from unittest.mock import patch, MagicMock, mock_open

from src.webscraping.yahoo_news_scraper import YahooNewsScraper
from src.webscraping.web_scraping import WebScraper
from src.chat.openai_adapter import OpenaiAdapter
from src.websearch.web_search import WebSearch

# テスト対象の関数をインポート
from example_usage_get_arcive import (
    process_others_article_contents,
    analyze_article_groups
)

class TestOthersArticleProcessing(unittest.TestCase):
    """othersグループの記事処理機能のテスト"""

    def setUp(self):
        """テスト前の準備"""
        # ロガーの設定
        self.logger = logging.getLogger("test_logger")
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        self.logger.addHandler(handler)
        
        # モックオブジェクトの作成
        self.yns_mock = MagicMock(spec=YahooNewsScraper)
        self.web_scraper_mock = MagicMock(spec=WebScraper)
        
        # テスト用の記事データ
        self.test_article = {
            "main_article": {
                "title": "テスト記事タイトル",
                "url": "https://news.yahoo.co.jp/test/article1",
                "content": "これはテスト記事の本文です。テスト用のコンテンツが含まれています。"
            },
            "pickup_articles": [
                {
                    "title": "関連記事1",
                    "url": "https://news.yahoo.co.jp/test/pickup1"
                }
            ],
            "analysis": {
                "has_essential_info": True,
                "extracted_info": "テスト記事の重要情報",
                "reasoning": "テスト用の理由",
                "conversation_starters": ["テスト会話1", "テスト会話2"],
                "insurance_bridges": ["保険展開1", "保険展開2"]
            }
        }
        
        # テスト用のグループデータ
        self.test_groups = {
            "groups": {
                "others": {
                    "title": "その他の記事",
                    "processed_articles": [
                        self.test_article
                    ]
                },
                "group1": {
                    "title": "グループ1",
                    "processed_articles": [
                        {
                            "main_article": {
                                "title": "グループ1記事",
                                "url": "https://news.yahoo.co.jp/test/group1"
                            },
                            "pickup_articles": []
                        }
                    ]
                }
            }
        }

    @patch('example_usage_get_arcive.WebScraper')
    @patch('example_usage_get_arcive.count_tokens')
    def test_process_others_article_contents_with_existing_content(self, mock_count_tokens, mock_web_scraper_class):
        """既存のメイン記事コンテンツを使用するケースのテスト"""
        # モックの設定
        mock_count_tokens.return_value = 100
        
        # YahooNewsScraperのモック設定
        self.yns_mock.scrape_article_contents.return_value = {
            "https://news.yahoo.co.jp/test/pickup1": {
                "title": "関連記事1",
                "content": "これは関連記事1の本文です。"
            }
        }
        
        # 関数の実行
        result = process_others_article_contents(
            self.test_article,
            self.yns_mock,
            self.web_scraper_mock,
            self.logger
        )
        
        # 検証
        self.assertIn("テスト記事タイトル", result)
        self.assertIn("これはテスト記事の本文です", result)
        self.assertIn("関連記事1", result)
        
        # メイン記事のコンテンツが再取得されていないことを確認
        self.yns_mock.scrape_article_contents.assert_called_once_with(["https://news.yahoo.co.jp/test/pickup1"])
        self.web_scraper_mock.scrape_multiple_urls.assert_not_called()

    def test_process_others_article_contents_without_pickup_articles(self):
        """ピックアップ記事がない場合のテスト"""
        # テスト用の記事データ（ピックアップ記事なし）
        test_article_no_pickup = {
            "main_article": {
                "title": "テスト記事タイトル",
                "url": "https://news.yahoo.co.jp/test/article1",
                "content": "これはテスト記事の本文です。テスト用のコンテンツが含まれています。"
            },
            "pickup_articles": [],
            "analysis": {
                "has_essential_info": True,
                "extracted_info": "テスト記事の重要情報",
                "reasoning": "テスト用の理由",
                "conversation_starters": ["テスト会話1", "テスト会話2"],
                "insurance_bridges": ["保険展開1", "保険展開2"]
            }
        }
        
        # OpenAIのモック
        mock_openai = MagicMock()
        mock_openai.openai_chat.return_value = """
        <search_keywords>
        [
          "テスト キーワード1",
          "テスト キーワード2",
          "テスト キーワード3"
        ]
        </search_keywords>
        """
        
        # WebSearchのモック
        mock_web_search = MagicMock()
        mock_web_search.search_and_standardize.return_value = {
            "search_results": [
                {
                    "title": "検索結果1",
                    "link": "https://example.com/result1",
                    "snippet": "検索結果1のスニペット"
                },
                {
                    "title": "検索結果2",
                    "link": "https://example.com/result2",
                    "snippet": "検索結果2のスニペット"
                }
            ]
        }
        
        # WebScraperのモック
        self.web_scraper_mock.scrape_multiple_urls.return_value = {
            "https://example.com/result1": {
                "content": "検索結果1の内容"
            },
            "https://example.com/result2": {
                "content": "検索結果2の内容"
            }
        }
        
        # count_tokensのモック
        mock_count_tokens = MagicMock(return_value=100)
        
        # 関数の実行
        with patch('src.chat.openai_adapter.OpenaiAdapter', return_value=mock_openai):
            with patch('src.websearch.web_search.WebSearch', return_value=mock_web_search):
                with patch('src.tiktoken.token_counter.count_tokens', mock_count_tokens):
                    result = process_others_article_contents(
                        test_article_no_pickup,
                        self.yns_mock,
                        self.web_scraper_mock,
                        self.logger
                    )
        
        # 検証
        self.assertIn("テスト記事タイトル", result)
        self.assertIn("これはテスト記事の本文です", result)
        
        # 検索キーワードが生成されたことを確認
        mock_openai.openai_chat.assert_called()
        
        # 検索が実行されたことを確認
        mock_web_search.search_and_standardize.assert_called()
        
        # 検索結果がスクレイピングされたことを確認
        self.web_scraper_mock.scrape_multiple_urls.assert_called()

    @patch('example_usage_get_arcive.process_others_article_contents')
    @patch('example_usage_get_arcive.process_group_article_contents')
    @patch('example_usage_get_arcive.analyze_article_group')
    @patch('example_usage_get_arcive.WebScraper')
    def test_analyze_article_groups(self, mock_web_scraper_class, mock_analyze_article_group, mock_process_group, mock_process_others):
        """analyze_article_groups関数のテスト"""
        # モックの設定
        mock_web_scraper = mock_web_scraper_class.return_value
        
        # analyze_article_groupのモック
        def side_effect(group_name, group_info, yns, web_scraper, logger):
            if group_name == "others":
                return self.test_groups["groups"]["others"]
            else:
                return self.test_groups["groups"]["group1"]
        
        mock_analyze_article_group.side_effect = side_effect
        
        # process_others_article_contentsのモック
        mock_process_others.return_value = "othersグループの処理結果"
        
        # process_group_article_contentsのモック
        mock_process_group.return_value = "通常グループの処理結果"
        
        # 関数の実行
        result = analyze_article_groups(
            self.test_groups,
            self.yns_mock,
            self.logger
        )
        
        # 検証
        # othersグループの処理が呼ばれたことを確認
        mock_process_others.assert_called_once()
        
        # 通常グループの処理が呼ばれたことを確認
        mock_process_group.assert_called_once()
        
        # othersグループの各記事にcombined_contentが設定されていることを確認
        self.assertEqual(
            result["groups"]["others"]["processed_articles"][0]["combined_content"],
            "othersグループの処理結果"
        )
        
        # 通常グループにcombined_contentが設定されていることを確認
        self.assertEqual(
            result["groups"]["group1"]["combined_content"],
            "通常グループの処理結果"
        )

    def test_token_limit_and_summarization(self):
        """トークン制限と要約処理のテスト"""
        # OpenAIのモック
        mock_openai = MagicMock()
        mock_openai.openai_chat.return_value = """
        <summary>
        これは要約されたコンテンツです。
        </summary>
        """
        
        # YahooNewsScraperのモック設定
        self.yns_mock.scrape_article_contents.return_value = {
            "https://news.yahoo.co.jp/test/pickup1": {
                "title": "関連記事1",
                "content": "これは関連記事1の本文です。" * 1000  # 長いコンテンツ
            }
        }
        
        # count_tokensのモック
        mock_count_tokens = MagicMock()
        mock_count_tokens.side_effect = [100, 25000, 500]
        
        # 関数の実行
        with patch('src.chat.openai_adapter.OpenaiAdapter', return_value=mock_openai):
            with patch('src.tiktoken.token_counter.count_tokens', mock_count_tokens):
                result = process_others_article_contents(
                    self.test_article,
                    self.yns_mock,
                    self.web_scraper_mock,
                    self.logger
                )
        
        # 検証
        # 要約が実行されたことを確認
        mock_openai.openai_chat.assert_called_once()
        
        # 要約結果が含まれていることを確認
        self.assertIn("<summary>", result)
        self.assertIn("これは要約されたコンテンツです。", result)

if __name__ == '__main__':
    unittest.main() 
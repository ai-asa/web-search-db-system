import unittest
from unittest.mock import Mock, patch
from src.webscraping.yahoo_news_scraper import YahooNewsScraper
from example_usage_get_arcive import process_article_urls_and_remove_duplicates, process_group_article_contents, analyze_article_groups
import logging
import sys
from src.webscraping.web_scraping import WebScraper

class TestArticleProcessing(unittest.TestCase):
    def setUp(self):
        """各テストケース実行前の準備"""
        # ロガーの設定
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)

        # モックの設定
        self.yns = Mock(spec=YahooNewsScraper)
        self.web_scraper = Mock(spec=WebScraper)

        # テスト開始のログ
        self.logger.info("\n" + "=" * 50)
        self.logger.info(f"テスト開始: {self._testMethodName}")
        self.logger.info("=" * 50)

    def tearDown(self):
        """各テストケース実行後の処理"""
        # テスト終了のログ
        self.logger.info("\n" + "-" * 50)
        self.logger.info(f"テスト終了: {self._testMethodName}")
        self.logger.info("-" * 50)

    def test_process_normal_group(self):
        """通常グループでの重複除去処理のテスト"""
        self.logger.info("通常グループのテストを実行")
        
        # テスト用のグループ化された記事データ（通常グループのみ）
        grouped_results = {
            "reasoning": "テスト用の理由",
            "articles": [
                {"number": 1, "title": "記事1", "url": "http://test1.com"},
                {"number": 2, "title": "記事2", "url": "http://test2.com"}
            ],
            "groups": {
                "group1": {
                    "title": "グループ1",
                    "articles": [1, 2]
                }
            }
        }

        # YahooNewsScraperのモックを作成
        mock_scraper = Mock(spec=YahooNewsScraper)
        
        # スクレイパーの戻り値を設定
        mock_responses = {
            "http://test1.com": {
                "main_article": [{"title": "メイン記事1", "url": "http://main1.com"}],
                "pickup_articles": [
                    {"title": "ピックアップ1", "url": "http://pickup1.com"},
                    {"title": "ピックアップ2", "url": "http://pickup2.com"}
                ]
            },
            "http://test2.com": {
                "main_article": [{"title": "メイン記事2", "url": "http://main2.com"}],
                "pickup_articles": [
                    {"title": "ピックアップ2", "url": "http://pickup2.com"},  # 重複
                    {"title": "ピックアップ3", "url": "http://pickup3.com"}
                ]
            }
        }
        
        def mock_scrape_article_urls(url):
            self.logger.info(f"記事URLの取得: {url}")
            return mock_responses[url]
            
        mock_scraper.scrape_article_urls.side_effect = mock_scrape_article_urls

        # 関数を実行
        self.logger.info("process_article_urls_and_remove_duplicates関数を実行")
        result = process_article_urls_and_remove_duplicates(grouped_results, mock_scraper)

        # group1の処理結果を検証
        group1_articles = result["groups"]["group1"]["processed_articles"]
        
        # 記事1の検証
        self.logger.info("記事1の検証")
        self.assertEqual(len(group1_articles[0]["pickup_articles"]), 2)
        self.assertEqual(group1_articles[0]["main_article"]["url"], "http://main1.com")
        self.logger.info(f"記事1のピックアップ記事数: {len(group1_articles[0]['pickup_articles'])}")
        
        # 記事2の検証（重複したピックアップ記事が除外されているか）
        self.logger.info("記事2の検証")
        self.assertEqual(len(group1_articles[1]["pickup_articles"]), 1)
        self.assertEqual(group1_articles[1]["pickup_articles"][0]["url"], "http://pickup3.com")
        self.logger.info(f"記事2のピックアップ記事数: {len(group1_articles[1]['pickup_articles'])}")
        self.logger.info(f"記事2の非重複ピックアップ記事URL: {group1_articles[1]['pickup_articles'][0]['url']}")

    def test_process_others_group(self):
        """othersグループでの重複チェックスキップのテスト"""
        self.logger.info("othersグループのテストを実行")
        
        # テスト用のグループ化された記事データ（othersグループのみ）
        grouped_results = {
            "reasoning": "テスト用の理由",
            "articles": [
                {"number": 1, "title": "記事3", "url": "http://test3.com"}
            ],
            "groups": {
                "others": {
                    "title": "その他",
                    "articles": [1]
                }
            }
        }

        # YahooNewsScraperのモックを作成
        mock_scraper = Mock(spec=YahooNewsScraper)
        
        # スクレイパーの戻り値を設定
        mock_response = {
            "main_article": [{"title": "メイン記事3", "url": "http://main3.com"}],
            "pickup_articles": [
                {"title": "ピックアップ1", "url": "http://pickup1.com"},  # 既に他で使用されているURL
                {"title": "ピックアップ4", "url": "http://pickup4.com"}
            ]
        }
        
        def mock_scrape_article_urls(url):
            self.logger.info(f"記事URLの取得: {url}")
            return mock_response
            
        mock_scraper.scrape_article_urls.side_effect = mock_scrape_article_urls

        # 関数を実行
        self.logger.info("process_article_urls_and_remove_duplicates関数を実行")
        result = process_article_urls_and_remove_duplicates(grouped_results, mock_scraper)

        # othersグループの処理結果を検証
        others_articles = result["groups"]["others"]["processed_articles"]
        
        # 重複チェックがスキップされ、全てのピックアップ記事が保持されているか確認
        self.logger.info("othersグループの記事を検証")
        self.assertEqual(len(others_articles[0]["pickup_articles"]), 2)
        self.logger.info(f"othersグループのピックアップ記事数: {len(others_articles[0]['pickup_articles'])}")
        for i, pickup in enumerate(others_articles[0]["pickup_articles"]):
            self.logger.info(f"ピックアップ記事{i+1}: {pickup['url']}")

    def test_process_empty_main_article(self):
        """メイン記事が取得できない場合のテスト"""
        self.logger.info("メイン記事が空の場合のテストを実行")
        
        # テスト用のグループ化された記事データ
        grouped_results = {
            "reasoning": "テスト用の理由",
            "articles": [
                {"number": 1, "title": "記事1", "url": "http://test1.com"}
            ],
            "groups": {
                "group1": {
                    "title": "グループ1",
                    "articles": [1]
                }
            }
        }

        # YahooNewsScraperのモックを作成
        mock_scraper = Mock(spec=YahooNewsScraper)
        
        # スクレイパーの戻り値を設定
        mock_response = {
            "main_article": [],
            "pickup_articles": [
                {"title": "ピックアップ1", "url": "http://pickup1.com"}
            ]
        }
        
        def mock_scrape_article_urls(url):
            self.logger.info(f"記事URLの取得: {url}")
            return mock_response
            
        mock_scraper.scrape_article_urls.side_effect = mock_scrape_article_urls

        # 関数を実行
        self.logger.info("process_article_urls_and_remove_duplicates関数を実行")
        result = process_article_urls_and_remove_duplicates(grouped_results, mock_scraper)

        # group1の処理結果を検証
        group1_articles = result["groups"]["group1"]["processed_articles"]
        
        # メイン記事が空の場合、その記事の情報が追加されていないことを確認
        self.logger.info("メイン記事が空の場合の処理を検証")
        self.assertEqual(len(group1_articles), 0)
        self.logger.info(f"処理された記事数: {len(group1_articles)}")

    def test_process_group_with_less_than_five_articles(self):
        """5個以下のメイン記事を持つグループの処理テスト"""
        # テストデータの準備
        group_info = {
            "title": "テストグループ1",
            "processed_articles": [
                {
                    "main_article": {
                        "title": "メイン記事1",
                        "url": "https://news.yahoo.co.jp/articles/1"
                    },
                    "pickup_articles": [
                        {"title": "ピックアップ1-1", "url": "https://news.yahoo.co.jp/articles/pickup1"},
                        {"title": "ピックアップ1-2", "url": "https://example.com/pickup2"}
                    ]
                },
                {
                    "main_article": {
                        "title": "メイン記事2",
                        "url": "https://example.com/article2"
                    },
                    "pickup_articles": [
                        {"title": "ピックアップ2-1", "url": "https://news.yahoo.co.jp/articles/pickup3"}
                    ]
                }
            ]
        }

        # Yahoo Newsのスクレイピング結果のモック
        self.yns.scrape_article_contents.return_value = {
            "https://news.yahoo.co.jp/articles/1": {"content": "Yahoo記事1の本文"},
            "https://news.yahoo.co.jp/articles/pickup1": {"content": "Yahooピックアップ1の本文"},
            "https://news.yahoo.co.jp/articles/pickup3": {"content": "Yahooピックアップ3の本文"}
        }

        # 一般Webサイトのスクレイピング結果のモック
        self.web_scraper.scrape_multiple_urls.return_value = {
            "https://example.com/article2": {"content": "一般記事2の本文"},
            "https://example.com/pickup2": {"content": "一般ピックアップ2の本文"}
        }

        # 関数の実行
        result = process_group_article_contents(group_info, self.yns, self.web_scraper, self.logger)

        # 検証
        self.assertIn("Yahoo記事1の本文", result)
        self.assertIn("一般記事2の本文", result)
        self.assertIn("Yahooピックアップ1の本文", result)
        self.assertIn("一般ピックアップ2の本文", result)
        self.assertIn("Yahooピックアップ3の本文", result)

    def test_process_group_with_more_than_five_articles(self):
        """5個より多いメイン記事を持つグループの処理テスト"""
        # テストデータの準備（6個のメイン記事）
        group_info = {
            "title": "テストグループ2",
            "processed_articles": [
                {
                    "main_article": {
                        "title": f"メイン記事{i}",
                        "url": f"https://news.yahoo.co.jp/articles/{i}"
                    },
                    "pickup_articles": [
                        {"title": f"ピックアップ{i}-1", "url": f"https://news.yahoo.co.jp/articles/pickup{i}"}
                    ]
                } for i in range(1, 7)
            ]
        }

        # Yahoo Newsのスクレイピング結果のモック
        yahoo_contents = {
            f"https://news.yahoo.co.jp/articles/{i}": {"content": f"Yahoo記事{i}の本文"}
            for i in range(1, 7)
        }
        self.yns.scrape_article_contents.return_value = yahoo_contents

        # 関数の実行
        result = process_group_article_contents(group_info, self.yns, self.web_scraper, self.logger)

        # 検証
        for i in range(1, 7):
            self.assertIn(f"Yahoo記事{i}の本文", result)
            # ピックアップ記事の内容が含まれていないことを確認
            self.assertNotIn(f"pickup{i}", result)

    @patch('src.tiktoken.token_counter.count_tokens')
    def test_process_group_with_token_limit(self, mock_count_tokens):
        """トークン制限を超える場合のテスト"""
        # トークンカウントのモック
        mock_count_tokens.side_effect = lambda text: 25000 if "あ" * 1000 in text else 100

        # テストデータの準備
        group_info = {
            "title": "テストグループ3",
            "processed_articles": [
                {
                    "main_article": {
                        "title": f"メイン記事{i}",
                        "url": f"https://news.yahoo.co.jp/articles/{i}"
                    },
                    "pickup_articles": []
                } for i in range(1, 4)
            ]
        }

        # 長い記事内容を生成
        long_content = "あ" * 10000
        self.yns.scrape_article_contents.return_value = {
            f"https://news.yahoo.co.jp/articles/{i}": {"content": long_content}
            for i in range(1, 4)
        }

        # OpenAIアダプターのモック
        with patch('src.chat.openai_adapter.OpenaiAdapter') as mock_openai:
            mock_openai_instance = Mock()
            mock_openai.return_value = mock_openai_instance
            mock_openai_instance.openai_chat.return_value = "<summary>要約された内容</summary>"

            # 関数の実行
            result = process_group_article_contents(group_info, self.yns, self.web_scraper, self.logger)

            # 検証
            self.assertRegex(result, r'<summary>.*</summary>')  # 要約タグの存在を確認
            # 要約APIが呼び出されたことを確認
            self.assertTrue(mock_openai_instance.openai_chat.called)
            # 要約が2回行われたことを確認（3つの長い記事で2回の要約が必要）
            self.assertEqual(mock_openai_instance.openai_chat.call_count, 2)

    def test_analyze_article_groups(self):
        """記事グループ全体の分析処理のテスト"""
        # テストデータの準備
        processed_results = {
            "groups": {
                "group1": {
                    "title": "グループ1",
                    "processed_articles": [
                        {
                            "main_article": {
                                "title": "メイン記事1",
                                "url": "https://news.yahoo.co.jp/articles/1"
                            },
                            "pickup_articles": []
                        }
                    ]
                },
                "others": {
                    "title": "その他",
                    "processed_articles": [
                        {
                            "main_article": {
                                "title": "個別記事1",
                                "url": "https://example.com/article1"
                            },
                            "pickup_articles": []
                        }
                    ]
                }
            }
        }

        # Yahoo Newsのスクレイピング結果のモック
        self.yns.scrape_article_contents.return_value = {
            "https://news.yahoo.co.jp/articles/1": {"content": "Yahoo記事1の本文"}
        }

        # 分析結果のモック
        with patch('example_usage_get_arcive.analyze_article_group') as mock_analyze:
            mock_analyze.side_effect = lambda name, info, yns, web_scraper, logger: info

            # 関数の実行
            result = analyze_article_groups(processed_results, self.yns, self.logger)

            # 検証
            self.assertIn("combined_content", result["groups"]["group1"])
            self.assertNotIn("combined_content", result["groups"]["others"])

if __name__ == '__main__':
    unittest.main() 
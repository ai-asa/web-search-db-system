import unittest
from unittest.mock import Mock, patch
import json
import logging
from src.webscraping.yahoo_news_scraper import YahooNewsScraper
from src.webscraping.web_scraping import WebScraper
from example_usage_get_arcive import (
    analyze_article_group,
    analyze_article_contents,
    analyze_article_groups,
    display_analysis_results,
    analyze_individual_article_content,
    analyze_individual_article,
    analyze_others_group
)

class TestArticleAnalysis(unittest.TestCase):
    def setUp(self):
        """テストの前準備"""
        self.logger = logging.getLogger(__name__)
        
        # テスト用の記事データ
        self.test_article_contents = [
            {
                "title": "台風による被害が拡大、保険請求が急増",
                "content": "台風による建物被害が各地で報告され、損害保険会社への保険金請求が急増しています。"
                          "特に住宅保険と火災保険の請求が目立ち、保険会社は24時間体制で対応にあたっています。"
            },
            {
                "title": "自然災害への備え、保険見直しの動き",
                "content": "昨今の自然災害の増加を受けて、保険の見直しを検討する人が増えています。"
                          "特に住宅保険の補償内容の確認や、新規加入の相談が増加しているとのことです。"
            }
        ]
        
        # テスト用のグループ情報
        self.test_group_info = {
            "title": "台風被害関連のニュース",
            "processed_articles": [
                {
                    "main_article": {
                        "title": "台風被害の記事1",
                        "url": "https://news.yahoo.co.jp/articles/1"
                    },
                    "pickup_articles": []
                },
                {
                    "main_article": {
                        "title": "台風被害の記事2",
                        "url": "https://news.yahoo.co.jp/articles/2"
                    },
                    "pickup_articles": []
                }
            ]
        }
        
        # テスト用の処理済み結果
        self.test_processed_results = {
            "groups": {
                "group1": self.test_group_info,
                "others": {
                    "title": "その他の記事",
                    "processed_articles": []
                }
            }
        }

    @patch('example_usage_get_arcive.OpenaiAdapter')
    def test_analyze_article_contents(self, mock_openai):
        """記事内容の分析テスト"""
        # OpenAIの応答をモック
        mock_instance = mock_openai.return_value
        mock_instance.openai_chat.return_value = '''
        <analysis>
        {
            "has_essential_info": true,
            "reasoning": "自然災害と保険に関する具体的な情報が含まれている",
            "potential_topics": [
                "最近の自然災害への備えについて",
                "保険の見直しの重要性"
            ]
        }
        </analysis>
        '''
        
        # 分析実行
        result = analyze_article_contents(self.test_article_contents, self.logger)
        
        # 検証
        self.assertIsNotNone(result)
        self.assertTrue(result["has_essential_info"])
        self.assertEqual(len(result["potential_topics"]), 2)
        mock_instance.openai_chat.assert_called_once()

    @patch('example_usage_get_arcive.OpenaiAdapter')
    def test_analyze_article_contents_error(self, mock_openai):
        """記事内容の分析エラーケースのテスト"""
        # OpenAIでエラーが発生する場合
        mock_instance = mock_openai.return_value
        mock_instance.openai_chat.side_effect = Exception("API Error")
        
        # 分析実行
        result = analyze_article_contents(self.test_article_contents, self.logger)
        
        # 検証
        self.assertIsNone(result)

    @patch('example_usage_get_arcive.analyze_article_contents')
    def test_analyze_article_group(self, mock_analyze_contents):
        """記事グループの分析テスト"""
        # YahooNewsScraperとWebScraperのモック
        mock_yns = Mock(spec=YahooNewsScraper)
        mock_web_scraper = Mock(spec=WebScraper)
        
        # Yahoo記事のスクレイピング結果をモック
        mock_yns.scrape_article_contents.return_value = {
            "https://news.yahoo.co.jp/articles/1": self.test_article_contents[0],
            "https://news.yahoo.co.jp/articles/2": self.test_article_contents[1]
        }
        
        # 分析結果をモック
        mock_analyze_contents.return_value = {
            "has_essential_info": True,
            "reasoning": "テスト理由",
            "potential_topics": ["テストトピック1", "テストトピック2"]
        }
        
        # 分析実行
        result = analyze_article_group(
            "group1",
            self.test_group_info,
            mock_yns,
            mock_web_scraper,
            self.logger
        )
        
        # 検証
        self.assertIsNotNone(result)
        self.assertIn("analysis", result)
        self.assertTrue(result["analysis"]["has_essential_info"])
        mock_yns.scrape_article_contents.assert_called()
        mock_analyze_contents.assert_called_once()

    def test_analyze_article_group_others(self):
        """othersグループの分析テスト"""
        mock_yns = Mock(spec=YahooNewsScraper)
        mock_web_scraper = Mock(spec=WebScraper)
        
        # othersグループの分析実行
        result = analyze_article_group(
            "others",
            {"title": "その他", "processed_articles": []},
            mock_yns,
            mock_web_scraper,
            self.logger
        )
        
        # 検証
        self.assertIsNotNone(result)
        mock_yns.scrape_article_contents.assert_not_called()

    @patch('example_usage_get_arcive.analyze_article_group')
    def test_analyze_article_groups(self, mock_analyze_group):
        """全記事グループの分析テスト"""
        # グループ分析の結果をモック
        mock_analyze_group.side_effect = lambda name, info, yns, web_scraper, logger: (
            info if name == "others" else {
                **info,
                "analysis": {
                    "has_essential_info": True,
                    "reasoning": "テスト理由",
                    "potential_topics": ["テストトピック"]
                }
            }
        )
        
        # 分析実行
        result = analyze_article_groups(
            self.test_processed_results,
            Mock(spec=YahooNewsScraper),
            self.logger
        )
        
        # 検証
        self.assertIn("groups", result)
        self.assertEqual(len(result["groups"]), 2)
        self.assertIn("analysis", result["groups"]["group1"])
        mock_analyze_group.assert_called()

    def test_display_analysis_results(self):
        """分析結果の表示テスト"""
        # ロガーをモック
        mock_logger = Mock(spec=logging.Logger)
        
        # 表示実行
        display_analysis_results(self.test_processed_results, mock_logger)
        
        # 検証
        mock_logger.info.assert_called()
        # 少なくとも1回以上のinfo呼び出しがあることを確認
        self.assertGreater(mock_logger.info.call_count, 0)

    def test_analyze_individual_article_content(self):
        """個別記事内容の分析テスト"""
        # テスト用の記事内容
        article_content = {
            "title": "健康診断の受診率が向上、予防医療への関心高まる",
            "content": "今年度の健康診断受診率が前年比10%増加し、70%に達したことが分かりました。"
                      "特に30-40代の受診率が大きく伸び、健康への意識が高まっていることが伺えます。"
                      "専門家は「予防医療の重要性が広く認識されてきた」と分析しています。"
        }
        
        # OpenAIの応答をモック
        with patch('example_usage_get_arcive.OpenaiAdapter') as mock_openai:
            mock_instance = mock_openai.return_value
            mock_instance.openai_chat.return_value = '''
            <analysis>
            {
                "has_essential_info": true,
                "reasoning": "健康管理と予防に関する具体的な情報が含まれている",
                "conversation_starters": [
                    "最近の健康診断は受けられましたか？",
                    "健康管理について気をつけていることはありますか？"
                ],
                "insurance_bridges": [
                    "健康診断で早期発見できても、治療費の心配があると思います",
                    "医療保険で経済的な備えをすることで安心して予防医療に取り組めます"
                ]
            }
            </analysis>
            '''
            
            # 分析実行
            result = analyze_individual_article_content(article_content, self.logger)
            
            # 検証
            self.assertIsNotNone(result)
            self.assertTrue(result["has_essential_info"])
            self.assertEqual(len(result["conversation_starters"]), 2)
            self.assertEqual(len(result["insurance_bridges"]), 2)
            mock_instance.openai_chat.assert_called_once()

    def test_analyze_individual_article(self):
        """個別記事の分析テスト"""
        # テスト用の記事情報
        test_article = {
            "main_article": {
                "title": "健康診断に関する記事",
                "url": "https://news.yahoo.co.jp/articles/health1"
            },
            "pickup_articles": []
        }
        
        # YahooNewsScraperとWebScraperのモック
        mock_yns = Mock(spec=YahooNewsScraper)
        mock_web_scraper = Mock(spec=WebScraper)
        
        # Yahoo記事のスクレイピング結果をモック
        mock_yns.scrape_article_contents.return_value = {
            "https://news.yahoo.co.jp/articles/health1": {
                "title": "健康診断の受診率が向上",
                "content": "健康診断の受診率が向上しているというニュース"
            }
        }
        
        # 分析結果をモック
        with patch('example_usage_get_arcive.analyze_individual_article_content') as mock_analyze:
            mock_analyze.return_value = {
                "has_essential_info": True,
                "reasoning": "テスト理由",
                "conversation_starters": ["テスト会話1"],
                "insurance_bridges": ["テスト展開1"]
            }
            
            # 分析実行
            result = analyze_individual_article(
                test_article,
                mock_yns,
                mock_web_scraper,
                self.logger
            )
            
            # 検証
            self.assertIsNotNone(result)
            self.assertIn("analysis", result)
            self.assertTrue(result["analysis"]["has_essential_info"])
            mock_yns.scrape_article_contents.assert_called_once()
            mock_analyze.assert_called_once()

    def test_analyze_individual_article_non_yahoo(self):
        """Yahoo以外の個別記事の分析テスト"""
        # テスト用の記事情報
        test_article = {
            "main_article": {
                "title": "健康に関する記事",
                "url": "https://other-news.com/health1"
            },
            "pickup_articles": []
        }
        
        # YahooNewsScraperとWebScraperのモック
        mock_yns = Mock(spec=YahooNewsScraper)
        mock_web_scraper = Mock(spec=WebScraper)
        
        # WebScraperの結果をモック
        mock_web_scraper.scrape_multiple_urls.return_value = {
            "https://other-news.com/health1": {
                "title": "健康に関する記事",
                "content": "健康に関する一般的なニュース記事"
            }
        }
        
        # 分析結果をモック
        with patch('example_usage_get_arcive.analyze_individual_article_content') as mock_analyze:
            mock_analyze.return_value = {
                "has_essential_info": True,
                "reasoning": "テスト理由",
                "conversation_starters": ["テスト会話1"],
                "insurance_bridges": ["テスト展開1"]
            }
            
            # 分析実行
            result = analyze_individual_article(
                test_article,
                mock_yns,
                mock_web_scraper,
                self.logger
            )
            
            # 検証
            self.assertIsNotNone(result)
            self.assertIn("analysis", result)
            self.assertTrue(result["analysis"]["has_essential_info"])
            mock_yns.scrape_article_contents.assert_not_called()
            mock_web_scraper.scrape_multiple_urls.assert_called_once()
            mock_analyze.assert_called_once()

    def test_analyze_others_group(self):
        """その他グループの分析テスト"""
        # テスト用のグループ情報
        test_group_info = {
            "title": "その他の記事",
            "processed_articles": [
                {
                    "main_article": {
                        "title": "記事1",
                        "url": "https://news.yahoo.co.jp/articles/1"
                    },
                    "pickup_articles": []
                },
                {
                    "main_article": {
                        "title": "記事2",
                        "url": "https://other-news.com/2"
                    },
                    "pickup_articles": []
                }
            ]
        }
        
        # YahooNewsScraperとWebScraperのモック
        mock_yns = Mock(spec=YahooNewsScraper)
        mock_web_scraper = Mock(spec=WebScraper)
        
        # analyze_individual_articleの結果をモック
        with patch('example_usage_get_arcive.analyze_individual_article') as mock_analyze:
            # 1つ目の記事は本質情報あり、2つ目は本質情報なしと仮定
            mock_analyze.side_effect = [
                {
                    "main_article": {"title": "記事1", "url": "url1"},
                    "pickup_articles": [],
                    "analysis": {
                        "has_essential_info": True,
                        "reasoning": "テスト理由1"
                    }
                },
                None  # 2つ目の記事は本質情報なしとしてNoneを返す
            ]
            
            # 分析実行
            result = analyze_others_group(
                test_group_info,
                mock_yns,
                mock_web_scraper,
                self.logger
            )
            
            # 検証
            self.assertIsNotNone(result)
            self.assertEqual(len(result["processed_articles"]), 1)  # 本質情報のある記事のみ残る
            self.assertIn("analysis", result["processed_articles"][0])
            mock_analyze.assert_called()
            self.assertEqual(mock_analyze.call_count, 2)  # 2つの記事に対して呼び出し

if __name__ == '__main__':
    unittest.main() 
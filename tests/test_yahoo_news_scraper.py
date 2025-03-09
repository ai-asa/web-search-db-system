import unittest
from src.webscraping.yahoo_news_scraper import YahooNewsScraper
import os
from pathlib import Path

class TestYahooNewsScraper(unittest.TestCase):
    def setUp(self):
        """
        テストの前処理
        """
        self.scraper = YahooNewsScraper()
        self.test_url = "https://news.yahoo.co.jp/articles/42f65df81f1c3aba3e5efef984eb748ff7b81c36"
        self.test_output_dir = "test_output"

    # def tearDown(self):
    #     """
    #     テストの後処理（テスト用の出力ディレクトリを削除）
    #     """
    #     if os.path.exists(self.test_output_dir):
    #         for file in Path(self.test_output_dir).glob("*"):
    #             file.unlink()
    #         Path(self.test_output_dir).rmdir()

    def test_scrape_article_contents(self):
        """
        記事内容のスクレイピングをテスト
        """
        # スクレイピングの実行
        results = self.scraper.scrape_article_contents(
            urls=[self.test_url],
            save_results=True,
            output_dir=self.test_output_dir
        )

        # 結果の検証
        self.assertIn(self.test_url, results)
        article = results[self.test_url]
        
        # タイトルの検証
        self.assertIn("title", article)
        self.assertTrue(article["title"].startswith("30代シングルマザー"))
        
        # 本文の検証
        self.assertIn("content", article)
        content = article["content"]
        
        # 本文に含まれるべき主要なフレーズの確認
        expected_phrases = [
            "高校授業料無償化",
            "大阪府大阪市に住む母子家庭のシングルマザー",
            "生活保護申請に行きつきました",
        ]
        for phrase in expected_phrases:
            self.assertIn(phrase, content)

        # ファイルが保存されていることを確認
        output_files = list(Path(self.test_output_dir).glob("*.json"))
        self.assertEqual(len(output_files), 1)

    def test_scrape_article_contents_no_save(self):
        """
        ファイル保存なしでの記事スクレイピングをテスト
        """
        results = self.scraper.scrape_article_contents(
            urls=[self.test_url],
            save_results=False
        )

        # 結果の検証
        self.assertIn(self.test_url, results)

    def test_scrape_article_contents_invalid_url(self):
        """
        無効なURLでのスクレイピングをテスト
        """
        invalid_url = "https://news.yahoo.co.jp/articles/invalid_article_id"
        results = self.scraper.scrape_article_contents(
            urls=[invalid_url],
            save_results=False
        )

        # 結果が空であることを確認
        self.assertEqual(len(results), 0)

    def test_scrape_article_urls(self):
        """
        2つのニュース記事URLに対してスクレイピングをテストします
        """
        test_urls = [
            "https://news.yahoo.co.jp/pickup/6531182",  # 高校進学の記事
            "https://news.yahoo.co.jp/pickup/6531621"   # 退職金税制の記事
        ]

        for url in test_urls:
            print(f"\n=== テスト対象URL: {url} ===")
            results = self.scraper.scrape_article_urls(url)
            
            # メイン記事の表示
            print("\n■ メイン記事:")
            if results['main_article']:
                article = results['main_article'][0]
                print(f"タイトル: {article['title']}")
                print(f"URL: {article['url']}")
            else:
                print("メイン記事が取得できませんでした")
            
            # ピックアップ記事の表示
            print("\n■ ピックアップ記事:")
            if results['pickup_articles']:
                for i, article in enumerate(results['pickup_articles'], 1):
                    print(f"\n記事{i}:")
                    print(f"タイトル: {article['title']}")
                    print(f"URL: {article['url']}")
            else:
                print("ピックアップ記事が取得できませんでした")
            
            # 基本的なアサーション
            self.assertTrue('main_article' in results)
            self.assertTrue('pickup_articles' in results)
            self.assertTrue(isinstance(results['main_article'], list))
            self.assertTrue(isinstance(results['pickup_articles'], list))
            
            if results['main_article']:
                self.assertTrue('title' in results['main_article'][0])
                self.assertTrue('url' in results['main_article'][0])
            
            for article in results['pickup_articles']:
                self.assertTrue('title' in article)
                self.assertTrue('url' in article)

if __name__ == '__main__':
    unittest.main() 
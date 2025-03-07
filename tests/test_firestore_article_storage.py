import unittest
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import os
from datetime import datetime, timezone, timedelta
from src.firestore.firestore_adapter import FirestoreAdapter
import time

class TestFirestoreArticleStorage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """テストクラスの初期化"""
        # Firestore初期化
        if not firebase_admin._apps:
            credentials_path = f"./secret-key/{os.getenv('CLOUD_FIRESTORE_JSON')}"
            cred = credentials.Certificate(credentials_path)
            firebase_admin.initialize_app(cred)
        cls.db = firestore.client()
        cls.firestore_adapter = FirestoreAdapter()

    def setUp(self):
        """各テストケース実行前の準備"""
        # テスト用のドキュメントをクリーンアップ
        self._cleanup_test_documents()
        pass

    def tearDown(self):
        """各テストケース実行後の処理"""
        # テスト用のドキュメントをクリーンアップ
        self._cleanup_test_documents()
        pass

    def _cleanup_test_documents(self):
        """テスト用ドキュメントの初期化"""
        documents = [
            ('articles', 'discovered_articles'),
            ('articles', 'referenced_articles'),
            ('articles', 'essential_info')
        ]
        for collection, document in documents:
            doc_ref = self.db.collection(collection).document(document)
            if doc_ref.get().exists:
                doc_ref.delete()

    def test_save_and_get_discovered_article(self):
        """発見した記事の保存と取得をテスト"""
        # テストデータ
        test_title = "テスト記事タイトル"
        test_url = "https://example.com/test-article"

        # 記事を保存
        self.firestore_adapter.save_discovered_article(self.db, test_title, test_url)

        # 保存した記事を取得
        articles = self.firestore_adapter.get_discovered_articles(self.db)

        # アサーション
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]['title'], test_title)
        self.assertEqual(articles[0]['url'], test_url)
        self.assertTrue('timestamp' in articles[0])

        # 同じドキュメントに追加されることを確認
        second_title = "テスト記事タイトル2"
        second_url = "https://example.com/test-article2"
        self.firestore_adapter.save_discovered_article(self.db, second_title, second_url)

        # 更新された記事リストを取得
        updated_articles = self.firestore_adapter.get_discovered_articles(self.db)
        self.assertEqual(len(updated_articles), 2)
        # 最新の記事が最初に来ることを確認
        self.assertEqual(updated_articles[0]['title'], second_title)

    def test_save_and_get_referenced_article(self):
        """参照した記事の保存と取得をテスト"""
        # テストデータ
        test_title = "参照記事タイトル"
        test_url = "https://example.com/referenced-article"

        # 記事を保存
        self.firestore_adapter.save_referenced_article(self.db, test_title, test_url)

        # 保存した記事を取得
        articles = self.firestore_adapter.get_referenced_articles(self.db)

        # アサーション
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]['title'], test_title)
        self.assertEqual(articles[0]['url'], test_url)
        self.assertTrue('timestamp' in articles[0])

    def test_save_and_get_essential_info(self):
        """本質情報の保存と取得をテスト"""
        # テストデータ
        info_name = "テスト情報"
        text_data = "これはテストデータです"
        retention_days = 7

        # 情報を保存
        self.firestore_adapter.save_essential_info(self.db, info_name, text_data, retention_days)

        # 保存した情報を取得
        info_list = self.firestore_adapter.get_valid_essential_info(self.db)

        # アサーション
        self.assertEqual(len(info_list), 1)
        self.assertEqual(info_list[0]['info_name'], info_name)
        self.assertEqual(info_list[0]['text_data'], text_data)
        self.assertTrue('timestamp' in info_list[0])
        self.assertTrue('expiration_date' in info_list[0])

    def test_cleanup_expired_info(self):
        """期限切れ情報のクリーンアップをテスト"""
        # 期限切れの情報を保存
        self.firestore_adapter.save_essential_info(self.db, "期限切れ情報", "古いデータ", -1)
        # 有効な情報を保存
        self.firestore_adapter.save_essential_info(self.db, "有効な情報", "新しいデータ", 7)

        # クリーンアップを実行
        self.firestore_adapter.cleanup_expired_info(self.db)

        # 残っている情報を取得
        info_list = self.firestore_adapter.get_valid_essential_info(self.db)

        # アサーション
        self.assertEqual(len(info_list), 1)
        self.assertEqual(info_list[0]['info_name'], "有効な情報")

    def test_multiple_articles_ordering(self):
        """複数の記事の保存と順序付けをテスト"""
        # 複数の記事を保存
        articles = [
            {"title": "記事1", "url": "https://example.com/1"},
            {"title": "記事2", "url": "https://example.com/2"},
            {"title": "記事3", "url": "https://example.com/3"}
        ]

        # 記事を時間差で保存
        for article in articles:
            self.firestore_adapter.save_discovered_article(self.db, article['title'], article['url'])
            time.sleep(1)  # タイムスタンプに差をつける

        # 保存した記事を取得
        saved_articles = self.firestore_adapter.get_discovered_articles(self.db)

        # アサーション
        self.assertEqual(len(saved_articles), 3)
        # 最新の記事が最初に来ることを確認
        self.assertEqual(saved_articles[0]['title'], "記事3")
        self.assertEqual(saved_articles[1]['title'], "記事2")
        self.assertEqual(saved_articles[2]['title'], "記事1")

if __name__ == '__main__':
    unittest.main() 
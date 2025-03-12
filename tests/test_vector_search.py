import unittest
from unittest.mock import Mock, patch
import firebase_admin
from firebase_admin import credentials, firestore
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
import numpy as np
from src.firestore.firestore_adapter import FirestoreAdapter
from src.chat.openai_adapter import OpenaiAdapter
import logging

class TestVectorSearch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # ロギングの設定
        logging.basicConfig(level=logging.INFO)
        cls.logger = logging.getLogger(__name__)

        # Firebase初期化（実際のテスト用）
        credentials_path = str(Path("secret-key") / f"{os.getenv('CLOUD_FIRESTORE_JSON')}.json")
        if not firebase_admin._apps:
            cred = credentials.Certificate(credentials_path)
            firebase_admin.initialize_app(cred)
        cls.db = firestore.client()
        
        # アダプターの初期化
        cls.fa = FirestoreAdapter()
        cls.openai = OpenaiAdapter()

    def setUp(self):
        self.logger.info("\n=== テスト開始 ===")

    def tearDown(self):
        self.logger.info("=== テスト終了 ===\n")

    def test_mock_vector_search(self):
        """モックを使用したベクトル検索のテスト"""
        self.logger.info("モックベクトル検索テストを開始します")

        # テストデータの準備
        mock_info_list = [
            {
                "info_name": "テスト情報1",
                "text_data": "これはテスト用の本質情報1です",
                "embedding": [0.1, 0.2, 0.3],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "expiration_date": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
            },
            {
                "info_name": "テスト情報2",
                "text_data": "これはテスト用の本質情報2です",
                "embedding": [0.2, 0.3, 0.4],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "expiration_date": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
            }
        ]

        # Firestoreのモックを作成
        mock_db = Mock()
        mock_doc = Mock()
        mock_doc.get.return_value.exists = True
        mock_doc.get.return_value.to_dict.return_value = {"info_list": mock_info_list}
        mock_db.collection.return_value.document.return_value = mock_doc

        # テスト用のクエリベクトル
        query_vector = [0.15, 0.25, 0.35]

        # ベクトル検索を実行
        results = self.fa.get_valid_essential_info(mock_db, query_vector=query_vector, limit=2)

        # 結果の検証
        self.assertIsNotNone(results)
        self.assertEqual(len(results), 2)
        self.logger.info(f"検索結果数: {len(results)}")
        for i, result in enumerate(results):
            self.logger.info(f"結果{i+1}: {result['info_name']}")
            self.logger.info(f"テキスト: {result['text_data']}")

    @patch('src.chat.openai_adapter.OpenaiAdapter.embedding')
    def test_mock_save_and_search(self, mock_embedding):
        """モックを使用した保存と検索の統合テスト"""
        self.logger.info("モック保存&検索テストを開始します")

        # OpenAI embeddingのモック
        mock_embedding.return_value = [[0.1, 0.2, 0.3], [0.2, 0.3, 0.4]]

        # テストデータ
        test_info = [
            {
                "info_name": "テスト保存情報1",
                "text_data": "保存テスト用の本質情報1です",
                "retention_period_days": 7
            },
            {
                "info_name": "テスト保存情報2",
                "text_data": "保存テスト用の本質情報2です",
                "retention_period_days": 7
            }
        ]

        # テキストデータからembeddingを生成（モック）
        texts = [info["text_data"] for info in test_info]
        embeddings = self.openai.embedding(texts)
        
        # embeddingをテストデータに追加
        for info, embedding in zip(test_info, embeddings):
            info["embedding"] = embedding

        # 現在時刻を取得
        now = datetime.now(timezone.utc)
        
        # 保存用のデータを作成
        saved_info = []
        for info in test_info:
            saved_info.append({
                "info_name": info["info_name"],
                "text_data": info["text_data"],
                "embedding": info["embedding"],
                "timestamp": now.isoformat(),
                "expiration_date": (now + timedelta(days=info["retention_period_days"])).isoformat()
            })

        # Firestoreのモック
        mock_db = Mock()
        mock_doc = Mock()
        mock_doc.get.return_value.exists = True
        mock_doc.get.return_value.to_dict.return_value = {"info_list": saved_info}
        mock_db.collection.return_value.document.return_value = mock_doc

        # 情報の保存
        self.fa.save_essential_info_batch(mock_db, test_info)
        self.logger.info("テストデータを保存しました")

        # 検索の実行
        query_vector = [0.15, 0.25, 0.35]
        results = self.fa.get_valid_essential_info(mock_db, query_vector=query_vector, limit=2)

        # 結果の検証
        self.assertIsNotNone(results)
        self.assertEqual(len(results), 2)  # 2件の結果が期待される
        self.logger.info(f"検索結果数: {len(results)}")
        for i, result in enumerate(results):
            self.logger.info(f"結果{i+1}: {result['info_name']}")
            self.logger.info(f"テキスト: {result['text_data']}")

    def test_real_vector_search(self):
        """実際のAPIを使用したベクトル検索のテスト"""
        self.logger.info("実際のベクトル検索テストを開始します")

        # テストデータの準備
        test_info = [
            {
                "info_name": "気候変動に関する最新情報",
                "text_data": "世界的な気温上昇により、極地の氷が急速に溶解しています。",
                "retention_period_days": 7
            },
            {
                "info_name": "経済動向レポート",
                "text_data": "世界経済は回復基調にあり、各国の株式市場も上昇傾向です。",
                "retention_period_days": 7
            }
        ]

        # テキストデータからembeddingを生成
        texts = [info["text_data"] for info in test_info]
        embeddings = self.openai.embedding(texts)
        self.logger.info("埋め込みベクトルを生成しました")

        # embeddingをテストデータに追加
        for info, embedding in zip(test_info, embeddings):
            info["embedding"] = embedding

        # 情報の保存
        self.fa.save_essential_info_batch(self.db, test_info)
        self.logger.info("テストデータを保存しました")

        # 検索クエリの準備
        search_text = "気候変動の影響について"
        query_embedding = self.openai.embedding([search_text])[0]
        self.logger.info(f"検索クエリ: {search_text}")

        # ベクトル検索を実行
        results = self.fa.get_valid_essential_info(self.db, query_vector=query_embedding, limit=2)

        # 結果の検証
        self.assertIsNotNone(results)
        self.logger.info(f"検索結果数: {len(results)}")
        for i, result in enumerate(results):
            self.logger.info(f"結果{i+1}: {result['info_name']}")
            self.logger.info(f"テキスト: {result['text_data']}")

if __name__ == '__main__':
    unittest.main() 
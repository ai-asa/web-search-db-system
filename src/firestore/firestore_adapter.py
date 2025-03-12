import datetime
import numpy as np
from firebase_admin import firestore
from google.cloud.firestore_v1.vector import Vector
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure

class FirestoreAdapter:

    def __init__(self):
        pass

    def save_discovered_articles_batch(self, db, articles: list):
        """
        発見した記事データを一括で保存します。

        Args:
            db: Firestoreデータベースインスタンス
            articles (list): 記事データのリスト。各要素は{"title": str, "url": str}の形式
        """
        if not articles:
            return

        doc_ref = db.collection('articles').document('discovered_articles')
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        # 新しい記事データの作成
        new_articles = [{
            "title": article["title"],
            "url": article["url"],
            "timestamp": now
        } for article in articles]
        
        # ドキュメントが存在するか確認
        doc = doc_ref.get()
        if doc.exists:
            # 既存の記事リストに一括で追加
            doc_ref.update({
                'articles': firestore.ArrayUnion(new_articles)
            })
        else:
            # 新しいドキュメントを作成
            doc_ref.set({
                'articles': new_articles
            })

    def save_referenced_articles_batch(self, db, articles: list):
        """
        参照した記事データを一括で保存します。

        Args:
            db: Firestoreデータベースインスタンス
            articles (list): 記事データのリスト。各要素は{"title": str, "url": str}の形式
        """
        if not articles:
            return

        doc_ref = db.collection('articles').document('referenced_articles')
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        # 新しい記事データの作成
        new_articles = [{
            "title": article["title"],
            "url": article["url"],
            "timestamp": now
        } for article in articles]
        
        # ドキュメントが存在するか確認
        doc = doc_ref.get()
        if doc.exists:
            # 既存の記事リストに一括で追加
            doc_ref.update({
                'articles': firestore.ArrayUnion(new_articles)
            })
        else:
            # 新しいドキュメントを作成
            doc_ref.set({
                'articles': new_articles
            })

    def save_essential_info_batch(self, db, info_list: list):
        """
        記事から抽出した本質情報を一括で保存します。

        Args:
            db: Firestoreデータベースインスタンス
            info_list (list): 情報のリスト。各要素は{"info_name": str, "text_data": str, "retention_period_days": int}の形式
        """
        if not info_list:
            return

        doc_ref = db.collection('articles').document('essential_info')
        now = datetime.datetime.now(datetime.timezone.utc)
        
        # 新しい情報データの作成
        new_info_list = [{
            "title": info["title"],
            "content": info["content"],
            "usage_example": info["usage_example"],
            "target_customers": info["target_customers"],
            "embedding": Vector(info["embedding"]),
            "timestamp": now.isoformat(),
            "expiration_date": (now + datetime.timedelta(days=info["retention_period_days"])).isoformat()
        } for info in info_list]
        
        # ドキュメントが存在するか確認
        doc = doc_ref.get()
        if doc.exists:
            # 既存の情報リストに一括で追加
            doc_ref.update({
                'info_list': firestore.ArrayUnion(new_info_list)
            })
        else:
            # 新しいドキュメントを作成
            doc_ref.set({
                'info_list': new_info_list
            })

    def initialize_articles_data(self, db):
        """
        記事関連のデータベース構造を初期化します。
        存在しない場合のみ初期化を行います。
        """
        collections = ['discovered_articles', 'referenced_articles', 'essential_info']
        batch = db.batch()
        
        for collection in collections:
            doc_ref = db.collection('articles').document(collection)
            if not doc_ref.get().exists:
                if collection == 'essential_info':
                    batch.set(doc_ref, {'info_list': []})
                else:
                    batch.set(doc_ref, {'articles': []})
        
        batch.commit()

    def get_discovered_articles(self, db):
        """
        発見した記事データを取得します。
        データが存在しない場合は初期化を行います。
        timestampフィールドが存在しない古いデータの場合は、デフォルト値を設定します。
        1週間以上経過したデータは削除されます。

        Args:
            db: Firestoreデータベースインスタンス

        Returns:
            list: 記事データのリスト
        """
        doc_ref = db.collection('articles').document('discovered_articles')
        doc = doc_ref.get()
        
        if not doc.exists:
            self.initialize_articles_data(db)
            return []
            
        articles = doc.to_dict().get('articles', [])
        
        # timestampフィールドが存在しない記事にデフォルト値を設定
        default_timestamp = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc).isoformat()
        for article in articles:
            if 'timestamp' not in article:
                article['timestamp'] = default_timestamp
        
        # 現在時刻を取得
        now = datetime.datetime.now(datetime.timezone.utc)
        one_week_ago = (now - datetime.timedelta(days=7)).isoformat()
        
        # 1週間以内のデータのみをフィルタリング
        valid_articles = [article for article in articles if article.get('timestamp', default_timestamp) > one_week_ago]
        
        # データが削除された場合、データベースを更新
        if len(valid_articles) < len(articles):
            doc_ref.update({
                'articles': valid_articles
            })
        
        return sorted(valid_articles, key=lambda x: x.get('timestamp', default_timestamp), reverse=True)

    def get_referenced_articles(self, db):
        """
        参照した記事データを取得します。
        データが存在しない場合は初期化を行います。
        1週間以上経過したデータは削除されます。

        Args:
            db: Firestoreデータベースインスタンス

        Returns:
            list: 記事データのリスト
        """
        doc_ref = db.collection('articles').document('referenced_articles')
        doc = doc_ref.get()
        
        if not doc.exists:
            self.initialize_articles_data(db)
            return []
            
        articles = doc.to_dict().get('articles', [])
        
        # 現在時刻を取得
        now = datetime.datetime.now(datetime.timezone.utc)
        one_week_ago = (now - datetime.timedelta(days=7)).isoformat()
        
        # 1週間以内のデータのみをフィルタリング
        valid_articles = [article for article in articles if article['timestamp'] > one_week_ago]
        
        # データが削除された場合、データベースを更新
        if len(valid_articles) < len(articles):
            doc_ref.update({
                'articles': valid_articles
            })
        
        return sorted(valid_articles, key=lambda x: x['timestamp'], reverse=True)

    def get_valid_essential_info(self, db, query_vector=None, limit=10):
        """
        有効期限内の本質情報を取得します。
        query_vectorが指定された場合は、ベクトル検索を行います。
        データが存在しない場合は初期化を行います。
        期限切れのデータは削除されます。

        Args:
            db: Firestoreデータベースインスタンス
            query_vector (list, optional): 検索クエリのベクトル。Noneの場合はベクトル検索を行いません。
            limit (int, optional): 取得する結果の最大数。デフォルトは10。

        Returns:
            list: 有効な本質情報のリスト。query_vectorが指定された場合は類似度順にソートされます。
                  各要素に'similarity'フィールドが追加され、0-1の範囲で正規化された類似度が格納されます。
        """
        doc_ref = db.collection('articles').document('essential_info')
        doc = doc_ref.get()
        
        if not doc.exists:
            self.initialize_articles_data(db)
            return []
            
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        info_list = doc.to_dict().get('info_list', [])
        
        # 有効期限内の情報のみをフィルタリング
        valid_info = [info for info in info_list if info['expiration_date'] > now]
        
        # 期限切れのデータが存在する場合、データベースを更新
        if len(valid_info) < len(info_list):
            doc_ref.update({
                'info_list': valid_info
            })

        # ベクトル検索が指定された場合
        if query_vector is not None:
            # クエリベクトルをNumPy配列に変換
            query_array = np.array(query_vector)
            
            # 有効な情報に対してベクトル検索を実行
            results = []
            for info in valid_info:
                # 埋め込みベクトルをNumPy配列に変換
                embedding_array = np.array(info['embedding'])
                # ユークリッド距離を計算（L2ノルム）
                distance = np.linalg.norm(query_array - embedding_array)
                # 距離を0-1の類似度に変換（1が最も類似）
                similarity = 1 / (1 + distance)
                # 情報をコピーして類似度を追加
                info_with_similarity = info.copy()
                info_with_similarity['similarity'] = similarity
                results.append((similarity, info_with_similarity))
            
            # 類似度でソートして上位limit件を返す（類似度の降順）
            results.sort(key=lambda x: x[0], reverse=True)
            return [info for _, info in results[:limit]]
        
        # ベクトル検索が指定されていない場合は、タイムスタンプでソート
        return sorted(valid_info, key=lambda x: x['timestamp'], reverse=True)[:limit]

    def delete_essential_info_batch(self, db, info_list: list):
        """
        本質情報を一括で削除します。

        Args:
            db: Firestoreデータベースインスタンス
            info_list (list): 削除する情報のリスト。各要素は{"title": str, "content": str}の形式
        """
        if not info_list:
            return

        doc_ref = db.collection('articles').document('essential_info')
        doc = doc_ref.get()
        
        if not doc.exists:
            return
            
        current_info_list = doc.to_dict().get('info_list', [])
        
        # 削除対象の情報を特定
        updated_info_list = []
        for info in current_info_list:
            should_keep = True
            for delete_info in info_list:
                if (info['title'] == delete_info['title'] and 
                    info['content'] == delete_info['content']):
                    should_keep = False
                    break
            if should_keep:
                updated_info_list.append(info)
        
        # 更新されたリストで上書き
        doc_ref.update({
            'info_list': updated_info_list
        })
import datetime
from firebase_admin import firestore

class FirestoreAdapter:

    def __init__(self):
        pass

    def set_pending_action(self, db, user_id: str, action_data: dict):
        doc_ref = db.collection('userIds').document(user_id)
        doc_ref.set({'pending_action': action_data}, merge=True)

    def get_pending_action(self, db, user_id: str) -> dict:
        doc_ref = db.collection('userIds').document(user_id)
        doc = doc_ref.get()
        if doc.exists and 'pending_action' in doc.to_dict():
            return doc.to_dict()['pending_action']
        else:
            return None

    def clear_pending_action(self, db, user_id: str):
        doc_ref = db.collection('userIds').document(user_id)
        doc_ref.update({'pending_action': firestore.DELETE_FIELD})

    def set_sub_status(self, db, user_id, current_status, next_status=None, plan_change_date=None,pending_action=None):
        data = {
            "current_sub_status": current_status,
            "pending_action": pending_action,
            "original_sub_status": current_status
        }
        if next_status:
            data["next_sub_status"] = next_status
        if plan_change_date:
            # タイムゾーン情報を含めて ISO フォーマットに変換
            data["plan_change_date"] = plan_change_date.isoformat()
        ref_userIds = db.collection('userIds').document(user_id)
        ref_userIds.set(data, merge=True)

    def set_new_sub(self, db, user_id, botType, new_status=None):
        """
        ・トライアルプランからの切り替え対応
        / 現在のプランを取得し、トライアルプランの場合はisTrialValidをFalseにする
        ・current_sub_status、botType、pending_actionを更新する
        """
        user_ref = db.collection('userIds').document(user_id)
        data = {
            "botType": botType,
            "isTrialValid": True
        }
        
        # new_statusが指定されている場合のみ更新
        if new_status is not None:
            data["current_sub_status"] = new_status
            data["original_sub_status"] = new_status
        
        # 現在トライアルプランの場合の処理
        doc = user_ref.get()
        if doc.exists:
            user_data = doc.to_dict()
            current_sub_status = user_data.get('current_sub_status')
            if current_sub_status == 'try':
                data['isTrialValid'] = False
                
        # 同じリファレンスを使用して保存
        user_ref.set(data, merge=True)

    def get_sub_status(self, db, user_id):
        ref_userIds = db.collection('userIds').document(user_id)
        doc = ref_userIds.get()
        if doc.exists:
            data = doc.to_dict()
            current_sub_status = data.get('current_sub_status', 'free')
            next_sub_status = data.get('next_sub_status')
            plan_change_date_str = data.get('plan_change_date')

            if plan_change_date_str and next_sub_status:
                # plan_change_date を日時オブジェクトに変換（タイムゾーン付き）
                plan_change_date = datetime.datetime.fromisoformat(plan_change_date_str)
                now = datetime.datetime.now(datetime.timezone.utc)

                if now >= plan_change_date:
                    # current_sub_status を更新
                    current_sub_status = next_sub_status
                    # next_sub_status と plan_change_date を削除
                    update_data = {
                        'current_sub_status': current_sub_status,
                        'next_sub_status': firestore.DELETE_FIELD,
                        'plan_change_date': firestore.DELETE_FIELD
                    }
                    ref_userIds.update(update_data)
                    next_sub_status = None
                    plan_change_date_str = None

            return {
                "current_sub_status": current_sub_status,
                "next_sub_status": next_sub_status,
                "plan_change_date": plan_change_date_str
            }
        else:
            # 初回アクセス時の初期データを設定
            data = {
                "current_sub_status": "free"
            }
            ref_userIds.set(data)
            return {
                "current_sub_status": "free",
                "next_sub_status": None,
                "plan_change_date": None
            }

    def set_botType(self, db, userId, botType):
        data = {
            "botType": botType
        }
        # userIdsコレクション内のユーザーIDドキュメントの参照を取得
        ref_userIds = db.collection('userIds').document(userId)
        # userIdsコレクションでユーザーIDとbotTypeを更新
        ref_userIds.set(data, merge=True)
    
    def get_botType(self, db, userId):
        ref_userIds = db.collection('userIds').document(userId)
        doc = ref_userIds.get()
        if doc.exists:
            return doc.to_dict().get('botType')
        else:
            data = {
                "botType": "fr"
            }
            ref_userIds.set(data, merge=True)
            return "fr"

    def update_history(self, db, userId, data_limit, user=None, assistant=None):
        """通常の会話履歴を更新する"""
        userIds_ref = db.collection('userIds').document(userId)
        conversations_ref = userIds_ref.collection('conversations')

        base_time = datetime.datetime.now(datetime.timezone.utc)
        
        if user:
            user_message = {
                "timestamp": base_time.isoformat(),
                "speaker": 'user',
                "content": user
            }
            conversations_ref.add(user_message)

        if assistant:
            assistant_message = {
                "timestamp": (base_time + datetime.timedelta(microseconds=1)).isoformat(),
                "speaker": 'assistant',
                "content": assistant
            }
            conversations_ref.add(assistant_message)

        # ユーザードキュメントが存在しない場合は初期化
        if not userIds_ref.get().exists:
            self.initialize_user_data(db, userId)

        # メッセージを timestamp の降順で取得
        snapshots = conversations_ref.order_by('timestamp', direction=firestore.Query.DESCENDING).get()

        # メッセージの総数が指定数を超える場合、古いメッセージを削除
        if len(snapshots) > data_limit:
            # 10件目以降のメッセージを取得
            messages_to_delete = snapshots[data_limit:]
            # 古いメッセージを削除
            for snapshot in messages_to_delete:
                snapshot.reference.delete()

    def get_history(self, db, userId, data_limit):
        conversations_ref = db.collection('userIds').document(userId).collection('conversations')
        snapshots = conversations_ref.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(data_limit).get()
        messages = [snapshot.to_dict() for snapshot in snapshots]
        return messages

    def _get_initial_fields(self):
        """
        ユーザーデータの初期フィールドを返します。
        """
        return {
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "current_sub_status": "free",
            "next_sub_status": None,
            "plan_change_date": None,
            "botType": "fr",
            "pending_action": None,
            "trial_start": None,
            "trial_end": None,
            "isTrialValid": True,
            "original_sub_status": "free",
            'isAlreadyRP': False,
            'rp_setting': None,
            'isRetryRP': False
        }

    def get_user_data(self, db, user_id, data_limit, rp_data_limit):
        """
        指定した user_id に紐づくすべてのデータを取得します。
        サブステータスのチェックと更新（get_sub_status の処理）も含めています。
        必要なフィールドが欠けている場合は、初期値で補完します。
        """
        user_ref = db.collection('userIds').document(user_id)
        doc = user_ref.get()
        
        if doc.exists:
            user_data = doc.to_dict()
            update_data = {}  # 更新データを格納する辞書
            
            # 必要なフィールドの存在チェックと初期値設定
            initial_fields = self._get_initial_fields()
            
            # 欠けているフィールドを検出し、update_dataに追加
            for field, default_value in initial_fields.items():
                if field not in user_data and field not in ['conversations', 'rp_history']:
                    update_data[field] = default_value
                    user_data[field] = default_value
                    if field == 'original_sub_status':
                        update_data[field] = user_data.get('current_sub_status','free')
                        user_data[field] = user_data.get('current_sub_status','free')
            
            # トライアル期限チェック処理
            current_sub_status = user_data.get('current_sub_status','free')
            is_trial_valid = user_data.get('isTrialValid', True)
            trial_end_str = user_data.get('trial_end')
            next_sub_status = user_data.get('next_sub_status')
            plan_change_date_str = user_data.get('plan_change_date')
            now = datetime.datetime.now(datetime.timezone.utc)
            # 元のステータスに戻す
            original_sub_status = user_data.get('original_sub_status')
            if trial_end_str and  current_sub_status == 'try' and is_trial_valid:
                trial_end = datetime.datetime.fromisoformat(trial_end_str)
                if  now >= trial_end:
                    update_data.update({
                        'current_sub_status': original_sub_status,
                        'isTrialValid': False
                    })
                    user_data['current_sub_status'] = original_sub_status
                    user_data['isTrialValid'] = False
            
            if plan_change_date_str and next_sub_status:
                plan_change_date = datetime.datetime.fromisoformat(plan_change_date_str)
                if now >= plan_change_date:
                    update_data.update({
                        'current_sub_status': next_sub_status,
                        'next_sub_status': firestore.DELETE_FIELD,
                        'plan_change_date': firestore.DELETE_FIELD
                    })
                    user_data['current_sub_status'] = next_sub_status
                    user_data.pop('next_sub_status', None)
                    user_data.pop('plan_change_date', None)
            
            # 更新が必要な場合のみ実行
            if update_data:
                user_ref.update(update_data)
            
            # conversations サブコレクションのデータ取得
            conversations_ref = user_ref.collection('conversations')
            snapshots = conversations_ref.order_by('timestamp', direction=firestore.Query.ASCENDING).limit(data_limit).get()
            conversations = [snapshot.to_dict() for snapshot in snapshots]
            user_data['conversations'] = conversations
            
            # rp_history サブコレクションのデータ取得
            rp_history_ref = user_ref.collection('rp_history')
            rp_snapshots = rp_history_ref.order_by('timestamp', direction=firestore.Query.ASCENDING).limit(rp_data_limit).get()
            rp_history = [snapshot.to_dict() for snapshot in rp_snapshots]
            user_data['rp_history'] = rp_history
            
            return user_data
        else:
            # ユーザーデータが存在しない場合は初期化する
            self.initialize_user_data(db, user_id)
            return self._get_initial_fields()

    def initialize_user_data(self, db, user_id):
        """
        指定した user_id の完全なデータ構造を初期化します。
        既に存在するフィールドは上書きされません。
        """
        initial_data = self._get_initial_fields()
        user_ref = db.collection('userIds').document(user_id)
        # 既存のデータを上書きしないように merge=True を指定
        user_ref.set(initial_data, merge=True)

    def set_trial_period(self, db, user_id):
        """
        ユーザーのトライアル期間を設定します。
        trial_start に現在時刻を、trial_end に3日後の時刻を設定します。
        データベースにはUTCで保存し、戻り値はJST形式で返します。
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        trial_end = now + datetime.timedelta(days=3)

        # データベース保存用のデータ
        data = {
            "current_sub_status": "try",
            "pending_action": None,
            "trial_start": now.isoformat(),
            "trial_end": trial_end.isoformat()
        }
        
        user_ref = db.collection('userIds').document(user_id)
        user_ref.set(data, merge=True)

        # JSTに変換（UTC+9時間）
        jst = datetime.timezone(datetime.timedelta(hours=9))
        now_jst = now.astimezone(jst)
        trial_end_jst = trial_end.astimezone(jst)

        # 戻り値用のデータ（JST）
        return {
            "current_sub_status": "try",
            "pending_action": None,
            "trial_start": now_jst.strftime('%Y年%m月%d日%H時%M分'),
            "trial_end": trial_end_jst.strftime('%Y年%m月%d日%H時%M分')
        }

    def reset_rp_history(self, db, user_id, isResetHistory=False, rp_setting=None, isAlreadyRP: bool = None, isRetryRP: bool = None):
        """RPの会話履歴とRP設定をリセットする
        
        ・必要なフィールド更新は単体のupdateで行い、
        サブコレクションの削除はバッチ書き込みで独立して実行する。
        ・トランザクションは、読み取りと書き込みの整合性が必要な場合に利用すべきで、
        単純な削除処理には不要です。
        """
        doc_ref = db.collection('userIds').document(user_id)
        update_data = {}
        
        if rp_setting is not None:
            update_data['rp_setting'] = rp_setting
        if isAlreadyRP is not None:
            update_data['isAlreadyRP'] = isAlreadyRP
        if isRetryRP is not None:
            update_data['isRetryRP'] = isRetryRP

        # まずドキュメントの更新（フィールドの更新はアトミックなので十分）
        if update_data:
            try:
                doc_ref.update(update_data)
            except Exception as e:
                print(f"Error updating user data: {e}")
                raise

        # サブコレクションのrp_historyの削除は、トランザクション内でなくバッチ処理で独立して実行
        if isResetHistory:
            try:
                batch = db.batch()
                rp_history_ref = doc_ref.collection('rp_history')
                docs = rp_history_ref.get()
                for doc in docs:
                    batch.delete(doc.reference)
                batch.commit()
            except Exception as e:
                print(f"Error deleting rp_history subcollection: {e}")
                raise

    def set_initial_rp(self, db, user_id, rp_setting):
        """初めてのRP設定を保存する"""
        doc_ref = db.collection('userIds').document(user_id)
        doc_ref.update({
            'isAlreadyRP': True,
            'rp_setting': rp_setting,
            'rp_history': []
        })

    def update_rp_history(self, db, userId, rp_data_limit, salesperson=None, customer=None):
        """RPの会話履歴を更新する"""
        userIds_ref = db.collection('userIds').document(userId)
        history_ref = userIds_ref.collection('rp_history')

        base_time = datetime.datetime.now(datetime.timezone.utc)
        
        if salesperson:
            salesperson_message = {
                "timestamp": base_time.isoformat(),
                "speaker": 'salesperson',
                "content": salesperson
            }
            history_ref.add(salesperson_message)

        if customer:
            customer_message = {
                "timestamp": (base_time + datetime.timedelta(microseconds=1)).isoformat(),
                "speaker": 'you',
                "content": customer
            }
            history_ref.add(customer_message)

        # ユーザードキュメントが存在しない場合は初期化
        if not userIds_ref.get().exists:
            self.initialize_user_data(db, userId)

        # メッセージを timestamp の降順で取得
        snapshots = history_ref.order_by('timestamp', direction=firestore.Query.DESCENDING).get()

        # メッセージの総数が指定数を超える場合、古いメッセージを削除
        if len(snapshots) > rp_data_limit:
            # 50件目以降のメッセージを取得
            messages_to_delete = snapshots[rp_data_limit:]
            # 古いメッセージを削除
            for snapshot in messages_to_delete:
                snapshot.reference.delete()

    def get_rp_history(self, db, userId, rp_data_limit):
        conversations_ref = db.collection('userIds').document(userId).collection('rp_history')
        snapshots = conversations_ref.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(rp_data_limit).get()
        messages = [snapshot.to_dict() for snapshot in snapshots]
        return messages

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
            "info_name": info["info_name"],
            "text_data": info["text_data"],
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

    def get_valid_essential_info(self, db):
        """
        有効期限内の本質情報を取得します。
        データが存在しない場合は初期化を行います。
        期限切れのデータは削除されます。

        Args:
            db: Firestoreデータベースインスタンス

        Returns:
            list: 有効な本質情報のリスト
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
        
        return sorted(valid_info, key=lambda x: x['timestamp'], reverse=True)
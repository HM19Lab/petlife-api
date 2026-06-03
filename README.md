# サンプルペッツライフ 在庫API
 
ペットショップの店頭在庫を SKU コード単位で管理する、シンプルな REST API。
**FastAPI** + **pandas** + **Railway** で実装・公開しています。
フロントエンドは別リポジトリ（[petlife-streamlit](https://github.com/HM19Lab/petlife-streamlit)）に Streamlit で実装。
 
---
 
## ライブデモ
 
- **API ルート（ヘルスチェック）**: <https://web-production-3267c.up.railway.app/>
- **全在庫データ**: <https://web-production-3267c.up.railway.app/stock>
- **Swagger UI（自動生成された API ドキュメント）**: <https://web-production-3267c.up.railway.app/docs>

ブラウザで開くと、それぞれ JSON / 対話的なドキュメント画面が表示されます。
 
<!-- スクリーンショットは後で docs/screenshot.png を追加してここに挿入 -->
<img width="1872" height="909" alt="api-swagger" src="https://github.com/user-attachments/assets/374fa421-4e02-496e-a7af-65288a9a70fc" />

---
 
## 概要
 
ペットショップの在庫を、SKU コード単位で管理するための在庫管理 API です。
CSV ファイルを商品マスタとして読み込み、メモリ上の DataFrame で保持しています。
現在庫数と発注点を比較して「**要発注**」フラグを自動計算する業務ロジックを持ちます。
 
> ※ デモ用のため、データの永続化は行っていません。サーバー再起動で CSV の初期値に戻ります。
 
---
 
## 主な機能
 
- 商品マスタの一覧取得（全在庫データの返却）
- SKU コードによる 1 商品ルックアップ
- 在庫数の更新（PUT で現在庫数を上書き）
- **「要発注」フラグの自動判定**（`現在庫数 < 発注点` のとき真）
---
 
## 設計メモ
 
- **フロント／バック分離構成**: フロントエンド（Streamlit）とバックエンド（FastAPI）を別リポジトリ・別サービスでデプロイし、CORS を介して連携している。フロントを差し替えても API は使い回せる。
- **業務ルールを API 側に集約**: 「要発注（現在庫数 < 発注点）」のような業務判定は API 側で計算してレスポンスに含める。フロントは表示に専念する責務分担。
- **データソースは CSV（メモリ保持）**: デモ用途のため、データベース構築や永続化は省略している。再起動で初期値に戻る前提。
---
 
## 技術スタック
 
| 区分 | 内容 |
|---|---|
| 言語 | Python 3 |
| Web フレームワーク | FastAPI |
| バリデーション | Pydantic |
| データ処理 | pandas |
| CORS | FastAPI 標準ミドルウェア（別ドメインのフロントから呼び出し可） |
| ホスティング | Railway |
 
---
 
## API エンドポイント
 
| メソッド | パス | 説明 |
|---|---|---|
| GET | `/` | ヘルスチェック（サービス名・バージョンを返す） |
| GET | `/stock` | 全在庫データ取得 |
| GET | `/stock/{sku_code}` | 1 商品取得（ルックアップ用） |
| PUT | `/stock/{sku_code}` | 在庫数更新 |
 
詳細な仕様（リクエスト／レスポンスのスキーマ）は Swagger UI で確認できます。
<https://web-production-3267c.up.railway.app/docs>
 
---
 
## プロジェクト構成
 
```
petlife-api/
├── main.py           FastAPI アプリ本体（エンドポイント定義）
├── stock.csv         在庫マスタデータ（デモ用）
├── requirements.txt  依存パッケージ
└── Procfile          Railway 用の起動設定
```
 
---
 
## ローカルでの動かし方
 
```bash
# 1. リポジトリをクローン
git clone https://github.com/HM19Lab/petlife-api.git
cd petlife-api
 
# 2. 依存パッケージをインストール
pip install -r requirements.txt
 
# 3. 起動
uvicorn main:app --reload
```
 
起動後、以下のURLにブラウザでアクセスできます。
 
- ヘルスチェック: <http://localhost:8000/>
- Swagger UI: <http://localhost:8000/docs>
---
 
## デプロイ
 
[Railway](https://railway.com/) にデプロイしています。
`Procfile` に起動コマンドを定義し、`main` ブランチへの push で自動デプロイされます。
 
---
 
## 関連リポジトリ
 
- **フロントエンド**: [petlife-streamlit](https://github.com/HM19Lab/petlife-streamlit)
  このAPIを呼び出すStreamlitアプリ。
---
 
## 作成者
 
[@HM19Lab](https://github.com/HM19Lab)

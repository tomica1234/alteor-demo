# Alteor Case Workspace

法律事務所・探偵事務所向けの案件ワークスペースです。個人ダッシュボードから担当案件を選び、案件ごとに「資料登録 → ドラフト作成／整合性確認 → 人の修正・確認」を操作できます。

この版は実際のLLM、クラウドAI、外部OCR、音声認識サービスには接続しません。結果は固定ロジックによるモックです。実案件情報は入力しないでください。

現在はLPを含めず、起動すると案件ワークスペースが直接開きます。

## UIデザイン

画面は、デジタル庁の[デザインシステム](https://design.digital.go.jp/dads/)を参考に、情報の階層、タイポグラフィ、色、ボタン、フォームの見せ方を業務画面向けに整理しています。外部フォントや外部サービスは読み込みません。

## 検証対象

- 書類ドラフトを作成し、担当者が修正・保存する流れ
- 書面と証拠資料の数字、日付、氏名、引用、証拠番号を確認する流れ
- 根拠資料へ戻って原文を確認する体験
- 人による確認、承認、操作履歴の見せ方

## 次フェーズ候補

- スキャンPDFのOCR
- 銀行取引明細の表・Excel化
- 面談・通話記録の要約とアクション抽出

## セットアップ

```bash
npm install
/opt/homebrew/bin/python3.13 -m venv .venv
.venv/bin/python -m pip install -e './backend[dev]'
```

## 起動

```bash
zsh scripts/start_alteor.sh
```

- 画面: `http://127.0.0.1:5174/`
- API: `http://127.0.0.1:8081/docs`

モデルサーバーやモデルファイルは不要です。

## 個別起動

```bash
ALTEOR_OFFLINE_MODE=true ALTEOR_SEED_DEMO_DATA=true \
  .venv/bin/uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8081

npm run dev -- --host 127.0.0.1 --port 5174
```

## 公開時のパスワード

公開する場合は、バックエンドに共有パスワードを設定してください。パスワードを設定すると、案件データを返すAPIはログイン済みのブラウザからのみ利用できます。認証状態はHttpOnly Cookieで保持します。

```bash
export ALTEOR_ACCESS_PASSWORD='公開用の長いパスワード'
export ALTEOR_SESSION_SECRET='十分に長いランダムな文字列'
export ALTEOR_SECURE_COOKIES=true
export ALTEOR_OFFLINE_MODE=true
export ALTEOR_SEED_DEMO_DATA=false
```

本番公開では、`dist/`を静的配信し、同じホストの`/api`をUvicornへリバースプロキシしてください。Viteの開発サーバーは公開用には使用しません。TLS（HTTPS）を有効にし、実案件情報を入れる前にバックアップとアクセスログの運用を決めてください。

`ALTEOR_ACCESS_PASSWORD`が未設定の場合、認証は無効です。公開環境では必ず設定してください。

## 検証

```bash
npm run check
```

フロントエンドのLint・ビルドと、バックエンドのテストを実行します。

# AI News Notify

Anthropic・OpenAI・Google Gemini の新着情報を毎日メールで受け取るシステム。

AWS Lambda で各サイトをクロールし、Gemini-2.5-flash で日本語に翻訳して SES でメール送信する。

## アーキテクチャ

```
EventBridge (毎日 10:00 JST)
    └── Lambda (Python 3.13)
            ├── クロール (Anthropic RSS / OpenAI RSS / Google Gemini HTML)
            ├── DynamoDB で既読フィルタリング (URL ベース、30日 TTL)
            ├── Gemini-2.5-flash で日本語翻訳
            └── SES でメール送信
```

CI/CD は CodePipeline (S3 トリガー) → CodeBuild (SAM build/package) → CloudFormation デプロイ。

## 前提条件

- AWS CLI 設定済み (`ap-northeast-1`)
- SES で送信元メールアドレスの検証済み
- Gemini API Key 取得済み

## デプロイ手順

### 1. Gemini API Key を SSM に登録

```bash
aws ssm put-parameter \
  --name /ai-news-notify/gemini-api-key \
  --value "YOUR_GEMINI_API_KEY" \
  --type SecureString \
  --region ap-northeast-1
```

### 2. SES で送信元メールを認証

```bash
aws ses verify-email-identity \
  --email-address YOUR_FROM_EMAIL \
  --region ap-northeast-1
```

受信した確認メールのリンクをクリックして認証完了。

### 3. CI/CD パイプラインを作成（初回のみ）

```bash
aws cloudformation deploy \
  --template-file pipeline.yaml \
  --stack-name ai-news-notify-pipeline \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    FromEmail=YOUR_FROM_EMAIL \
    ToEmail=YOUR_TO_EMAIL
```

### 4. ソースをアップロードしてデプロイを実行

```bash
zip -r source.zip . -x "*.git*" "*.zip"
aws s3 cp source.zip s3://$(aws sts get-caller-identity --query Account --output text)-ai-news-notify-source/source.zip
```

パイプラインが自動起動し、`ai-news-notify` アプリスタックがデプロイされる。

### 以降のデプロイ

コードを変更したら手順 4 のアップロードのみで自動デプロイされる。

## 手動実行

デプロイ後すぐ動作確認したい場合は Lambda を直接呼び出す。

```bash
aws lambda invoke \
  --function-name ai-news-notify-crawler \
  --region ap-northeast-1 \
  response.json && cat response.json
```

## クロール対象

| ソース | 取得方法 |
|---|---|
| [Anthropic](https://www.anthropic.com/news) | RSS (`/rss.xml`) → HTML フォールバック |
| [OpenAI](https://openai.com/blog) | RSS (`/blog/rss.xml`) |
| [Google Gemini](https://gemini.google/jp/release-notes/?hl=ja) | HTML パース |

新着記事の URL を DynamoDB に記録し、30日以内に送信済みの記事は除外する。

## スタック構成

| スタック名 | テンプレート | 用途 |
|---|---|---|
| `ai-news-notify-pipeline` | `pipeline.yaml` | CI/CD インフラ（初回のみデプロイ） |
| `ai-news-notify` | `template.yaml` | アプリ本体（パイプラインが自動管理） |

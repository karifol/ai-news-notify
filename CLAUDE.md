# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

Crawls Anthropic, OpenAI, and Google Gemini news pages daily, translates new articles to Japanese using Gemini-2.5-flash, and sends an HTML email digest via Amazon SES. Articles are deduplicated using DynamoDB (30-day TTL).

## Deployment workflow

Two CloudFormation stacks, deployed in order:

**1. Pipeline stack (one-time setup):**
```bash
aws cloudformation deploy \
  --template-file pipeline.yaml \
  --stack-name ai-news-notify-pipeline \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    FromEmail=sender@example.com \
    ToEmail=recipient@example.com
```

**2. Trigger the pipeline by uploading source:**
```bash
zip -r source.zip . -x "*.git*" "*.zip"
aws s3 cp source.zip s3://<AccountId>-ai-news-notify-source/source.zip
```

The pipeline (CodeBuild → CloudFormation changeset) then deploys `template.yaml` as the `ai-news-notify` app stack automatically.

**Required SSM parameter** (must exist before pipeline runs):
```bash
aws ssm put-parameter \
  --name /ai-news-notify/gemini-api-key \
  --value "YOUR_KEY" \
  --type SecureString
```

**SES sender address** must be verified in `ap-northeast-1` before emails can be sent.

## Architecture

```
pipeline.yaml   → CI/CD infrastructure (CodePipeline + CodeBuild + IAM)
template.yaml   → Application infrastructure (Lambda + DynamoDB + EventBridge)
buildspec.yaml  → CodeBuild: sam build → sam package → packaged.yaml artifact
```

Lambda runs on a schedule (`cron(0 22 * * ? *)` = 07:00 JST) with a 300s timeout.

All Python dependencies (`requests`, `beautifulsoup4`, `google-genai`) are in a Lambda Layer defined in `layers/dependencies/requirements.txt`, not bundled with the function code.

## Lambda code structure (`src/crawler/`)

- **`app.py`** — entrypoint; orchestrates crawl → deduplicate → translate → notify
- **`crawlers.py`** — `BaseCrawler` + three subclasses (`AnthropicCrawler`, `OpenAICrawler`, `GeminiCrawler`); each crawler tries `__NEXT_DATA__` JSON first (Next.js sites), then falls back to HTML parsing
- **`translator.py`** — `Translator` wraps `google.genai.Client`; sends structured prompt and parses `タイトル:` / `概要:` lines from response; falls back to original text on any error
- **`notifier.py`** — `Notifier` sends HTML + plain-text multipart email via `boto3` SES client

## Adding a new news source

1. Add a subclass of `BaseCrawler` in `crawlers.py` with `source_name`, `base_url`, `news_url`, and a `fetch()` method returning `list[Article]`
2. Instantiate it in the `crawlers` list in `app.py`

## Environment variables (set by SAM from template.yaml)

| Variable | Source |
|---|---|
| `SEEN_ARTICLES_TABLE` | DynamoDB table name (CloudFormation ref) |
| `FROM_EMAIL` | CloudFormation parameter |
| `TO_EMAIL` | CloudFormation parameter |
| `GEMINI_API_KEY` | SSM SecureString `/ai-news-notify/gemini-api-key` |

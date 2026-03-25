# Meet Japan Workflow

`Meet Japan` is a small automation workflow for generating and publishing short-form travel content about Japan.

This public version focuses on the reusable code and templates behind the workflow:

- short video generation with the OpenAI Videos API
- prompt-packet based generation jobs
- YouTube upload orchestration
- competitor research snapshots
- travel news collection
- manifest tracking for generated assets

## Why this repo exists

I wanted a lightweight workflow that could connect:

1. idea planning
2. AI-assisted video generation
3. publishing operations
4. simple research loops

The goal was not to build a polished product, but to learn how AI-assisted content workflows behave in practice.

## Included in this public repo

- `programs/tools/generate_openai_generic_short.py`
  Generates a vertical short video with the OpenAI Videos API and writes a manifest.
- `programs/tools/run_generation_job.py`
  Launches a generation job from a prompt packet.
- `programs/tools/run_youtube_upload.py`
  Example uploader wrapper for YouTube publishing.
- `programs/tools/fetch_travel_news.py`
  Pulls official travel news and combines it with a local research snapshot.
- `programs/tools/research_competitors.py`
  Builds a simple competitor snapshot from public YouTube feeds.
- `planning/*.sample.*`
  Sample planning files used to manage ideas and scheduling.
- `examples/comments/inbox_comments.sample.json`
  Example structure for comment inbox handling.

## Not included

This repo intentionally excludes:

- API keys and secrets
- OAuth credentials
- generated videos and media outputs
- private logs
- unpublished production files

## Setup

1. Create a virtual environment.
2. Install dependencies:

```bash
pip install requests beautifulsoup4
```

3. Copy `.env.example` to `.env` and fill in the required values.

## Example commands

Draft review only:

```bash
python programs/tools/generate_openai_generic_short.py
```

Generate a video:

```bash
python programs/tools/generate_openai_generic_short.py --generate
```

Build a competitor snapshot:

```bash
python programs/tools/research_competitors.py
```

Fetch travel news:

```bash
python programs/tools/fetch_travel_news.py
```

## Notes

- Paths were converted to repository-relative paths for public release.
- The YouTube upload wrapper assumes you provide your own uploader script and OAuth setup.
- Sample files are included where the original workflow used private or generated data.

<p align="center">
  <a href="https://github.com/setsu2420/aidd-intern/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/badge/License-Apache_2.0-blue.svg"></a>
  <a href="https://smolagents-aidd-intern.hf.space/"><img alt="Website" src="https://img.shields.io/website/https/smolagents-aidd-intern.hf.space.svg?down_color=red&down_message=offline&up_message=online"></a>
</p>

<p align="center">
  <a href="README.md">English</a> · <a href="README.zh-CN.md">简体中文</a> · <strong>日本語</strong>
</p>

# AIDD-Intern

AIDD-Intern は、AI drug discovery の調査、binder 設計、protein-design
ワークフローのための非同期エージェント実行基盤です。LLM 呼び出し、コンテキスト
管理、ツールルーティング、MCP、セッショントレース、Web バックエンド、AIDD
ドメインツールを分離しているため、ノート PC では出典付き調査を行い、重い
protein-design 処理は外部計算資源へ委譲できます。

AIDD-Intern は CLI や FastAPI プロセス内で LLM 重みを読み込みません。また
BindCraft、BoltzGen、PXDesign、Chai-1、Protenix などの重い科学計算スタックも
Web バックエンドへ直接 import しません。モデルはリモート LLM API または
OpenAI-compatible なローカル推論サーバーで動かし、重い設計ツールは MCP、
サブプロセス、コンテナ、クラスタ、Hugging Face Jobs 経由で接続します。

## 言語

- English: [README.md](README.md)
- 简体中文: [README.zh-CN.md](README.zh-CN.md)
- 日本語: [README.ja.md](README.ja.md)

## 主な機能

- 出典付き調査: `research`、`web_search`、`literature_lookup`、
  `hf_papers`、Hugging Face docs、GitHub ツール、`aidd_bio` を内蔵。
- Google Search 対応: `GOOGLE_SEARCH_API_KEY` と
  `GOOGLE_SEARCH_ENGINE_ID` がある場合、Google Custom Search JSON API を使用。
- モデル切り替え: `--model`、`configs/models.json`、対話中の `/model`
  コマンドで切り替え可能。
- 可変コンテキスト長: リモート OpenAI-compatible provider は固定 65k に縛られず、
  ローカル未知モデルのみ保守的な既定値を使います。
- AIDD binder ワークフロー: `binder_design` は通常の内蔵ツールとして利用できます。
- Protein design 拡張: PXDesign、BoltzGen、BindCraft、Chai-1、Protenix、
  Foldseek などのツールも通常の内蔵ツールとして登録されます。重いローカル
  MCP launcher は明示的なセットアップと opt-in が必要です。
- CLI と Web UI: Python CLI、FastAPI backend、React frontend、Node.js harness
  を含みます。
- セッショントレース: Claude Code JSONL 互換形式で保存し、Hugging Face の
  private dataset にアップロードできます。

## クイックスタート

### 必要環境

- Python 3.11+
- `uv`
- Git
- frontend または Node CLI harness を触る場合のみ Node.js 22+
- PXDesign、BindCraft などをローカル実行する場合のみ Conda/Mamba と GPU

### Python runtime のインストール

```bash
git clone https://github.com/setsu2420/aidd-intern.git
cd aidd-intern
uv sync --extra dev
uv tool install -e .
```

初回セットアップでは上の HTTPS URL を使ってください。SSH 形式の
`git@github.com:setsu2420/aidd-intern.git` は、GitHub SSH key が設定済みで、
そのアカウントにリポジトリ権限がある場合だけ動きます。`uv sync` と
`uv tool install -e .` は `aidd-intern` ディレクトリ内で実行してください。
どちらもその場所の `pyproject.toml` を読みます。

起動:

```bash
aidd-intern
```

GPU なしで調査だけ行う場合:

```bash
aidd-intern --model openrouter/openai/gpt-5.2 \
  "Research recent protein binder design tools. Prefer Google Search and cite sources."
```

## モデル設定と切り替え

共有モデルカタログは [configs/models.json](configs/models.json) です。CLI と Web UI
の既定モデル、候補、alias、provider、tier を管理します。

```bash
AIDD_INTERN_DEFAULT_MODEL_ID=siliconflow/deepseek-ai/DeepSeek-V4-Flash
AIDD_INTERN_MODELS_CONFIG=configs/models.json
```

起動時に指定:

```bash
aidd-intern --model openai/gpt-5.5 "your prompt"
aidd-intern --model anthropic/claude-opus-4-6 "your prompt"
aidd-intern --model openrouter/openai/gpt-5.2 "your prompt"
aidd-intern --model siliconflow/deepseek-ai/DeepSeek-V4-Flash "your prompt"
```

対話モードのコマンド:

```text
/model list
/model status
/model 2
/model flash
/model openrouter/openai/gpt-5.2
/model ollama/llama3.1:8b
/model --global siliconflow/deepseek-ai/DeepSeek-V4-Flash
```

`/model <id|alias|number>` は現在のセッションだけを変更します。
`/model --global <id|alias|number>` は `configs/models.json` の `default` も更新します。

## API キーと検索

`.env` または shell export で設定します。`.env`、token、重み、checkpoint、
database、生成構造、trace は GitHub にコミットしないでください。

```bash
OPENAI_API_KEY=<your-openai-api-key>
ANTHROPIC_API_KEY=<your-anthropic-api-key>
OPENROUTER_API_KEY=<your-openrouter-api-key>
SILICONFLOW_API_KEY=<your-siliconflow-api-key>

GOOGLE_SEARCH_API_KEY=<google-custom-search-json-api-key>
GOOGLE_SEARCH_ENGINE_ID=<programmable-search-engine-id>
GOOGLE_API_KEY=<optional-google-api-key-alias>
GOOGLE_CSE_ID=<optional-google-cse-id-alias>

HF_TOKEN=<your-hugging-face-token>
GITHUB_TOKEN=<github-personal-access-token>
```

`web_search` は Google credentials がそろっている場合 Google Custom Search JSON
API を使い、`recent_days` は `dateRestrict=dN`、`sort_by_date=true` は
`sort=date` を送ります。credentials がない開発環境では HTML fallback を使います。

## CLI

```bash
aidd-intern
aidd-intern "Research current AlphaFold-style complex validation methods and cite sources."
aidd-intern "research-only task"
aidd-intern "plan a binder campaign"
aidd-intern "run protein design tools"
aidd-intern --sandbox-tools "test this script in an HF Space sandbox"
```

## Web App

一括起動:

```bash
./scripts/dev.sh
```

既定 URL:

- Frontend: `http://localhost:5173/`
- Backend health: `curl -g http://[::1]:7860/api`
- Frontend proxy health: `curl http://localhost:5173/api`

個別起動:

```bash
cd backend
uv run python -m uvicorn main:app --host ::1 --port 7860
```

```bash
cd frontend
npm ci
npm run dev
```

## Tools と MCP

既定設定:

- CLI: [configs/cli_agent_config.json](configs/cli_agent_config.json)
- Web: [configs/frontend_agent_config.json](configs/frontend_agent_config.json)

MCP は cold start を軽くするため遅延接続します。

- Hugging Face MCP は `https://hf.co/mcp` を使い、`HF_TOKEN` がない場合はスキップ。
- ProteinMCP は `AIDD_INTERN_ENABLE_PROTEINMCP=1` の場合のみ接続。
- OpenAPI/catalog のリモート取得は起動時ではなくツール呼び出し時に行います。

Binder と protein-design の機能は通常の内蔵ツールです。`binder_design`、
`run_pxdesign`、`run_boltzgen`、`run_bindcraft`、
`protein_design_ace_playbook` は別の selector なしで利用できます。

ProteinMCP のインストール:

```bash
scripts/setup-proteinmcp-local.sh all
scripts/setup-proteinmcp-local.sh bindcraft_mcp
scripts/setup-proteinmcp-local.sh boltzgen_mcp
scripts/setup-proteinmcp-local.sh pxdesign_mcp
```

## コンテキスト戦略

- 既知のリモートモデルは provider/catalog の情報を使います。
- 未知のローカルモデルは保守的に 65,536 token を使います。
- リモート OpenAI-compatible モデルはローカル 65k 方針に固定されません。
- context window に近づく前に compaction を行います。

上書き例:

```bash
AIDD_INTERN_FORCE_MODEL_MAX_TOKENS=1000000
AIDD_INTERN_LOCAL_MODEL_MAX_TOKENS=131072
SILICONFLOW_MODEL_MAX_TOKENS=1000000
OPENROUTER_MODEL_MAX_TOKENS=1048576
```

## 起動性能

CLI は banner/config の軽い段階と runtime の重い段階を分離しています。内蔵ツールは
schema だけを登録し、実装 handler は呼び出し時に import します。通常のローカル
起動では `whoosh` や `nbconvert` を cold-start path に載せません。

import profiling:

```bash
PYTHONPROFILEIMPORTTIME=1 uv run python -X importtime -m agent.main \
  --model siliconflow/deepseek-ai/DeepSeek-V4-Flash </dev/null
```

回帰テスト:

```bash
uv run pytest tests/unit/test_mcp_startup.py -q
```

## 開発とテスト

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

frontend:

```bash
cd frontend
npm run lint
npm run build
```

Node CLI harness:

```bash
npm run build
npm run lint
npm test
npm pack --dry-run
```

## セッショントレース

CLI session は Claude Code JSONL 互換形式で保存し、Hugging Face private dataset
へアップロードできます。

```text
/share-traces
/share-traces public
/share-traces private
```

既定 target:

```text
{your-hf-username}/aidd-intern-sessions
```

## Citation

```bibtex
@Misc{aidd-intern,
  title =        {AIDD-Intern: an agent runtime for source-backed AI drug discovery research and binder workflows},
  author =       {Aksel Joonas Reedi, Henri Bonamy, Yoan Di Cosmo, Leandro von Werra, Lewis Tunstall},
  howpublished = {\url{https://github.com/setsu2420/aidd-intern}},
  year =         {2026}
}
```

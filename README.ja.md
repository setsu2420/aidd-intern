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
- AIDD preparation stage: `aidd_prepare` は文献メタデータ収集、RCSB PDB
  ダウンロード、構造 crop、接触ベースの hotspot residue 候補抽出を行います。
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
cp .env.example .env
```

初回セットアップでは上の HTTPS URL を使ってください。SSH 形式の
`git@github.com:setsu2420/aidd-intern.git` は、GitHub SSH key が設定済みで、
そのアカウントにリポジトリ権限がある場合だけ動きます。`uv sync` と
`uv tool install -e .` は `aidd-intern` ディレクトリ内で実行してください。
どちらもその場所の `pyproject.toml` を読みます。

`git clone` が `GnuTLS recv error (-110)` などの GitHub HTTPS transport error
で失敗する場合は、Git HTTP/1.1 を強制して再試行してください:

```bash
git -c http.version=HTTP/1.1 clone --depth 1 \
  https://github.com/setsu2420/aidd-intern.git
```

GitHub source archive fallback 付きの一括 bootstrap が必要な場合:

```bash
curl -fsSL https://raw.githubusercontent.com/setsu2420/aidd-intern/main/scripts/bootstrap-source.sh | bash
```

起動:

```bash
aidd-intern
```

最初の実 LLM 呼び出しの前に `.env` を編集し、選択したモデルに対応する API key
を少なくとも 1 つ設定してください。たとえば `openrouter/openai/gpt-5.2` には
`OPENROUTER_API_KEY`、`openai/gpt-5.5` には `OPENAI_API_KEY`、
`anthropic/claude-opus-4-6` には `ANTHROPIC_API_KEY`、
`siliconflow/deepseek-ai/DeepSeek-V4-Flash` には `SILICONFLOW_API_KEY` が必要です。
ローカル vLLM を使わない場合は、`.env` の `AIDD_INTERN_DEFAULT_MODEL_ID` も
リモートモデルに変更してください。

チャットを開始せずにローカル環境だけ確認:

```bash
aidd-intern --doctor
```

GPU なしで調査だけ行う場合:

```bash
aidd-intern --model openrouter/openai/gpt-5.2 \
  "Research recent protein binder design tools. Prefer Google Search and cite sources."
```

## ローカル更新

published npm package を global install しているユーザーは、npm の global update
経路を使えます:

```bash
npm install -g aidd-intern@latest
```

Node CLI からもステップ付きで実行できます:

```bash
aidd-intern update
aidd-intern update --check
aidd-intern update --dry-run
```

`aidd-intern update` は npm harness package だけを更新します。source checkout は
編集せず、Python の `uv tool install -e .` runtime も更新しません。現在の
`aidd-intern` command が Python CLI を指している場合は、下の
`npm run update:local` source-checkout path を使ってください。

既存 source checkout を更新するには、リポジトリルートで実行します:

```bash
scripts/update-local.sh
npm run update:local
```

このスクリプトは各ステップを表示してから実行します:

1. `git pull --ff-only origin <current-branch>`
2. `uv sync --extra dev`
3. `uv tool install -e .`
4. 任意の `frontend/` 内 `npm ci`
5. `command -v aidd-intern`

frontend dependencies も更新する場合:

```bash
scripts/update-local.sh --with-frontend
npm run update:local:frontend
node src/cli.ts update --checkout --with-frontend
```

`git pull --ff-only` はローカルブランチが remote と分岐している場合に失敗し、
自動で merge commit を作りません。別の remote や branch から更新したい場合だけ
`AIDD_INTERN_UPDATE_REMOTE` または `AIDD_INTERN_UPDATE_BRANCH` を設定してください。

## ローカル診断

インストール後、`.env` 変更後、更新後に実行できます:

```bash
aidd-intern --doctor
```

doctor は read-only です。Python、`git`、`uv`、任意の `npm`、config 読み込み、
選択中モデルに必要な LLM API key、Google Search credentials、update helper、
任意の frontend dependencies、ProteinMCP opt-in を順番にチェックします。

Hermes Agent と同じ実用的な流れを参考にしています。まず install、次に provider を
1 つ設定し、doctor-style check を実行し、簡単な chat を確認してから重いツールを有効にします。

## AIDD 準備段階

binder generation の前に、次の 4 つの準備タスクをローカルで完了できます:

1. 文献調査: `literature_lookup` と `web_search` で paper、公式ページ、DOI、
   PMID、preprint ID、既知 binder、epitope、assay 制約を集めます。
2. PDB 取得: RCSB PDB から選択した実験構造をダウンロードします。
3. 構造 crop: downstream design tool に渡す target chain/domain/residue range
   だけを残します。
4. Hotspot residue 決定: target/partner chain の atom contacts から候補 residue
   を順位付けし、文献や mutagenesis 情報で確認します。

インストール後、Python CLI で準備フローを実行できます:

```bash
aidd-intern --prepare-aidd \
  --target-name "PD-L1" \
  --pdb-id 4ZQK \
  --target-chains A \
  --partner-chains B \
  --residue-ranges A:19-134 \
  --prep-project-dir runs/pd-l1-prep
```

出力:

- `aidd_preparation_manifest.json`
- `literature/literature_sources.md`
- `structures/raw/<PDB_ID>.pdb`
- `structures/cropped/<PDB_ID>_<chains>_crop.pdb`
- `analysis/hotspots.json`
- `aidd_preparation_summary.md`

`aidd_prepare` は agent の内蔵 tool としても利用でき、`create_project`、
`literature_research`、`download_pdb`、`crop_structure`、`identify_hotspots`、
`run_preparation` をサポートします。Hotspot は非水素 atom contact から得た準備用
候補であり、実験的 binding energy の証明ではありません。

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

テンプレートから始める場合:

```bash
cp .env.example .env
```

```bash
# LLM providers. 選択したモデルに対応する key を設定します。
OPENAI_API_KEY=<your-openai-api-key>
ANTHROPIC_API_KEY=<your-anthropic-api-key>
OPENROUTER_API_KEY=<your-openrouter-api-key>
SILICONFLOW_API_KEY=<your-siliconflow-api-key>

# 既定モデル。コマンドごとに --model でも上書きできます。
AIDD_INTERN_DEFAULT_MODEL_ID=openrouter/openai/gpt-5.2
AIDD_INTERN_MODELS_CONFIG=configs/models.json

# Real Google Search. 両方が必要です。
GOOGLE_SEARCH_API_KEY=<google-custom-search-json-api-key>
GOOGLE_SEARCH_ENGINE_ID=<programmable-search-engine-id>

# Optional aliases.
GOOGLE_API_KEY=<google-custom-search-json-api-key>
GOOGLE_CSE_ID=<programmable-search-engine-id>

HF_TOKEN=<your-hugging-face-token>
GITHUB_TOKEN=<github-personal-access-token>

LOCAL_LLM_BASE_URL=http://localhost:8000
LOCAL_LLM_API_KEY=<optional-local-api-key>
AIDD_INTERN_ENABLE_PROTEINMCP=0
```

npm harness は provider-specific setup steps を表示できます。ファイルは変更しません:

```bash
aidd-intern configure-llm
aidd-intern configure-llm openrouter
aidd-intern configure-llm local
```

OpenClaw/Hermes Agent と同じ実用的な設定パターンを参考にしています。provider を
1 つ選び、model id を設定し、provider API key または local base URL を `.env`
に入れ、doctor/check command で確認してから full workflow に進みます。

`web_search` は Google credentials がそろっている場合 Google Custom Search JSON
API を使い、`recent_days` は `dateRestrict=dN`、`sort_by_date=true` は
`sort=date` を送ります。credentials がない開発環境では HTML fallback を使います。
Google の現在の文書では、Custom Search JSON API には Programmable Search
Engine ID と API key の両方が必要です。また Google は、Custom Search JSON API
利用者は 2027 年 1 月 1 日までに代替手段へ移行する必要があると発表しているため、
この依存関係は `.env` で明示的に管理してください。

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
- `AIDD_INTERN_DISABLE_UPDATE_CHECK=1` で起動時と `aidd-intern --doctor`
  の read-only version check を抑制します。

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

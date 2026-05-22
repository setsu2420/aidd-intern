<p align="center">
  <a href="https://github.com/setsu2420/aidd-intern/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/badge/License-Apache_2.0-blue.svg"></a>
  <a href="https://smolagents-aidd-intern.hf.space/"><img alt="Website" src="https://img.shields.io/website/https/smolagents-aidd-intern.hf.space.svg?down_color=red&down_message=offline&up_message=online"></a>
</p>

<p align="center">
  <a href="README.md">English</a> · <a href="README.zh-CN.md">简体中文</a> · <strong>日本語</strong>
</p>

# AIDD-Intern

AIDD-Intern は、AI 創薬（AI Drug Discovery, AIDD）の調査、binder 設計、および protein-design ワークフローのための非同期エージェント実行基盤です。LLM 呼び出し、コンテキスト管理、ツールルーティング、MCP 統合、セッショントレース、Web バックエンド、および AIDD 関連のドメインツールを解耦し、効率的でスケーラブルな開発を可能にします。

## 目次

- [主な機能](#主な機能)
- [クイックスタート](#クイックスタート)
- [ローカル更新](#ローカル更新)
- [ローカル診断](#ローカル診断)
- [AIDD 準備段階](#aidd-準備段階)
- [プロジェクト構成](#プロジェクト構成)

## 主な機能

- **文献調査とデータ探索**：内蔵された検索ツールを使用し、創薬の意思決定に必要な最新の文献、コードレポジトリ、およびモデル情報を収集します。
- **AIDD 準備タスク**：準備用プロジェクトの自動生成、PDB 構造データの取得、標的構造のクロップ、およびアミノ酸ホットスポット候補のランキングを実行します。
- **MCP 科学ツールの統合**：Hugging Face MCP やローカルの ProteinMCP（BindCraft, BoltzGen, PXDesign）の軽量なコールドスタートと呼び出しをサポートします。
- **適応型コンテキスト**：使用モデルの Token 制限値に基づき、実行時にコンテキストを自動圧縮し、長時間の実行タスクが中断するのを防ぎます。
- **デュアルエンジンログ**：PyO3 + Maturin に基づく高性能なログ書き込み加速モジュールを搭載。ローカルに Rust コンパイル環境がない場合は、自動的かつ透過的にネイティブ Python 書き込みエンジンにフォールバックします。

## クイックスタート

### 必要環境

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (高速 Python パッケージマネージャー)
- Git (ソースコード管理用)

### インストールと設定

ターミナルで以下のコマンドを実行してインストールを行います：

```bash
git clone https://github.com/setsu2420/aidd-intern.git
cd aidd-intern
uv sync --extra dev
uv tool install -e .
```

> **注意**：必ず `cd aidd-intern` でディレクトリに移動してから `uv sync` および `uv tool install -e .` を実行してください。依存関係の解決とツールのインストールにそのディレクトリ下の `pyproject.toml` が必要となるためです。

ネットワークの理由により `git clone` 時に HTTPS 転送エラーが発生した場合は、HTTP/1.1 を強制してシャロークローンを実行してください：
```bash
git -c http.version=HTTP/1.1 clone --depth 1 https://github.com/setsu2420/aidd-intern.git
```
または、Git エラー時に自動的にアーカイブをダウンロードしてインストールを行う自動復旧スクリプトを使用できます：
```bash
curl -fsSL https://raw.githubusercontent.com/setsu2420/aidd-intern/main/scripts/bootstrap-source.sh | bash
```

インストール完了後、環境変数テンプレートから `.env` ファイルを作成します：
```bash
cp .env.example .env
```
`.env` ファイルを編集し、使用するモデルに対応する API Key（`SILICONFLOW_API_KEY` や `OPENROUTER_API_KEY` など）および `AIDD_INTERN_DEFAULT_MODEL_ID` を設定します。

## ローカル診断

インストールや設定変更、アップデートを行った後は、診断コマンドを実行して環境を検証することを推奨します：
```bash
aidd-intern --doctor
```
このコマンドは読み取り専用で実行され、Python、Git、uv、設定ファイル、LLM API 認証情報、および ProteinMCP の設定を検証します。

## ローカル更新

ローカルのソースコードを最新バージョンに更新するには、レポジトリのルートディレクトリで以下のスクリプトを実行します：
```bash
scripts/update-local.sh
```
このスクリプトは `git pull --ff-only origin <current-branch>`、`uv sync --extra dev`、および `uv tool install -e .` を安全に実行し、依存関係とコマンドツールを更新します。

## Rust 高速化（オプショナル）

AIDD-Intern には、JSON シリアライゼーション、機密情報のマスク処理、ANSI 文字列処理を最大 **3.2 倍**高速化するオプショナルな Rust ネイティブ拡張モジュール（`aidd_intern_core`）が含まれています。GIL-free の並行処理もサポートしています。

**Rust 拡張は完全にオプショナルです** — システムに Rust ツールチェーンがインストールされていない場合でも、プロジェクトは純粋な Python 実装を使用してゼロ設定で同一に動作します。

### 自動検出（推奨）

Rust が既にインストールされている場合は、以下を実行するだけです：
```bash
uv sync --extra dev
```
ビルドシステム（`setuptools-rust`）が自動的に検出してネイティブ拡張をコンパイルします。

### ワンクリックセットアップ（Rust 安装 + コンパイル）

Rust がまだインストールされていない場合は、セットアップスクリプトを実行します：
```bash
./scripts/setup-rust.sh
```
このスクリプトは `rustup` 経由で Rust ツールチェーンを自動安装し（存在しない場合）、リリース最適化版のネイティブ拡張をコンパイルします。

### 手動セットアップ

1. Rust をインストール：
   ```bash
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
   source $HOME/.cargo/env
   ```
2. プロジェクトを再ビルド：
   ```bash
   uv sync --extra dev
   ```

### 確認

```bash
python -c "from aidd_intern_core import json_dumps_sorted; print(json_dumps_sorted({'hello': 'world'}))"
```
エラーが発生しなければ、Rust 高速化が有効になっています。

## AIDD 準備段階

重い binder 科学計算生成タスクを実行する前に、以下の 4 つの準備タスクを完了させる必要があります：
1. **文献調査**：標的、既知の binder、結合部位（エピトープ）、および実験的制約メタデータを収集します。
2. **PDB 取得**：RCSB PDB データベースから指定の実験用三次元構造座標データを取得します。
3. **構造 crop**：後続の設計ツールで必要となる、特定の標的チェーンやドメイン残基の範囲を切り出します。
4. **Hotspot residue 決定**：標的チェーンとパートナーチェーンの非水素原子の接触に基づき、ホットスポット候補アミノ酸をランキングします。

以下のコマンドを実行することで、すべての準備タスクを一括実行できます：
```bash
aidd-intern --prepare-aidd \
  --target-name "PD-L1" \
  --pdb-id 4ZQK \
  --target-chains A \
  --partner-chains B \
  --residue-ranges A:19-134 \
  --prep-project-dir runs/pd-l1-prep
```
このワークフローは、指定された出力ディレクトリに以下の構造化された成果ファイルを生成します：
- `aidd_preparation_manifest.json` (プロジェクトメタデータ)
- `literature/literature_sources.md` (文献調査結果)
- `structures/raw/<PDB_ID>.pdb` (オリジナル構造)
- `structures/cropped/<PDB_ID>_<chains>_crop.pdb` (クロップ後の構造)
- `analysis/hotspots.json` (接触アミノ酸分析結果)
- `aidd_preparation_summary.md` (準備報告書)

> **安全上の注意**：`aidd_prepare` によるホットスポットの選定は準備段階の入力候補に過ぎず、実験的 binding energy を証明するものではありません。

## プロジェクト構成

- `agent/`：Agent 実行環境、コンテキスト管理、CLI、および内蔵ツール。
- `backend/`：FastAPI Web バックエンド、セッション管理および API ルーティング。
- `configs/`：共有モデルカタログおよび MCP 設定ファイル。
- `aidd_intern_core/`：Rust ネイティブ拡張の Python ラッパー（Rust が利用可能な場合自动コンパイル）。
- `src/`：Rust ネイティブ拡張のソースコード（`lib.rs`）。
- `scripts/`：ローカル開発起動スクリプト、科学計算ツール MCP インストールおよび一键設定ツール。
- `tests/`：pytest ユニットテストおよび統合テストスイート。

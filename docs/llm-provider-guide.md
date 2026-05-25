# LLM 多模型接入指南

AIDD-Intern 支持通过统一接口接入 **20+ 种 LLM 提供商**，采用 `prefix/model-name` 格式路由到对应 provider。

---

## 架构概览

```
用户输入: "deepseek/deepseek-chat"
         │
         ▼
┌─ model_switcher.py ─┐
│  解析 prefix → 路由  │
└────────┬────────────┘
         │
    ┌────┴────┐
    ▼         ▼
 直连模式   HF Router 模式
(openai/,   (huggingface/
 deepseek/,  无前缀模型)
 kimi/ ...)
    │
    ▼
┌─ openai_compatible_models.py ─┐
│  查找 base_url + api_key      │
└────────┬──────────────────────┘
         │
         ▼
┌─ llm_params.py ─┐
│  litellm.acompletion() │
└──────────────────┘
```

**核心机制**: 所有远程 provider 均通过 OpenAI-compatible wire protocol 调用，底层使用 [LiteLLM](https://docs.litellm.ai/) 统一适配。

---

## 支持的 Provider 列表

### 主流云端 Provider

| Provider | 前缀 | 默认 Base URL | API Key 环境变量 |
|----------|------|---------------|------------------|
| **OpenAI** | `openai/` | (LiteLLM 内置) | `OPENAI_API_KEY` |
| **Anthropic** | `anthropic/` | (LiteLLM 内置) | `ANTHROPIC_API_KEY` |
| **AWS Bedrock** | `bedrock/` | (LiteLLM 内置) | AWS 凭证 |
| **Google Gemini** | `gemini/` | `https://generativelanguage.googleapis.com/v1beta/openai` | `GEMINI_API_KEY` |
| **xAI (Grok)** | `xai/` | `https://api.x.ai/v1` | `XAI_API_KEY` |
| **DeepSeek** | `deepseek/` | `https://api.deepseek.com/v1` | `DEEPSEEK_API_KEY` |

### 国内 Provider

| Provider | 前缀 | 默认 Base URL | API Key 环境变量 |
|----------|------|---------------|------------------|
| **Kimi (月之暗面)** | `kimi/` | `https://api.moonshot.cn/v1` | `KIMI_API_KEY` |
| **MiniMax** | `minimax/` | `https://api.minimax.chat/v1` | `MINIMAX_API_KEY` |
| **DashScope (通义千问)** | `dashscope/` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `DASHSCOPE_API_KEY` |
| **腾讯混元** | `tencent/` | `https://api.lkeap.cloud.tencent.com/v1` | `TENCENT_API_KEY` |
| **小米 MiMo** | `xiaomi/` | `https://api.xiaomimimo.com/v1` | `XIAOMI_API_KEY` |

### 第三方 API 聚合平台

| Provider | 前缀 | 默认 Base URL | API Key 环境变量 |
|----------|------|---------------|------------------|
| **OpenRouter** | `openrouter/` | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` |
| **SiliconFlow** | `siliconflow/` | `https://api.siliconflow.cn/v1` | `SILICONFLOW_API_KEY` |
| **NovitaAI** | `novita/` | `https://api.novita.ai/v3/openai` | `NOVITA_API_KEY` |
| **NVIDIA NIM** | `nvidia/` | `https://integrate.api.nvidia.com/v1` | `NVIDIA_API_KEY` |
| **Arcee AI** | `arcee/` | `https://api.arcee.ai/v1` | `ARCEE_API_KEY` |

### 本地推理服务器

| Provider | 前缀 | 默认端口 | 说明 |
|----------|------|----------|------|
| **Ollama** | `ollama/` | 11434 | 本地模型管理 |
| **vLLM** | `vllm/` | 8000 | 高性能推理 |
| **LM Studio** | `lm_studio/` | 1234 | 桌面端推理 |
| **llama.cpp** | `llamacpp/` | 8080 | 轻量级推理 |

---

## 快速配置

### 1. 设置 API Key

将 `.env.example` 复制为 `.env`，填入需要的 key：

```bash
cp .env.example .env
```

```env
# 至少设置一个
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
DEEPSEEK_API_KEY=sk-...
KIMI_API_KEY=sk-...
# ... 其他 provider
```

### 2. 设置默认模型

```env
AIDD_INTERN_DEFAULT_MODEL_ID=deepseek/deepseek-chat
```

### 3. CLI 使用

```bash
# 使用默认模型
aidd-intern "设计一个 PD-L1 binder"

# 临时切换模型
aidd-intern --model kimi/moonshot-v1-128k "设计一个 PD-L1 binder"

# 交互模式中切换
> /model deepseek/deepseek-reasoner
```

---

## 模型 ID 格式

### 直连模式 (推荐)

使用 `provider/model-name` 格式直接连接 provider API：

```
deepseek/deepseek-chat
kimi/moonshot-v1-128k
gemini/gemini-2.5-pro
xai/grok-3
minimax/MiniMax-M1
tencent/hunyuan-turbo
xiaomi/MiMo-7B-RL
```

直连模式跳过 HuggingFace Router catalog 检查，延迟更低。

### HF Router 模式

无前缀的模型 ID 通过 HuggingFace Inference Router：

```
moonshotai/Kimi-K2.6
MiniMaxAI/MiniMax-M2.7
deepseek-ai/DeepSeek-V4-Pro:deepinfra
```

需要设置 `HF_TOKEN`。

### OpenRouter / SiliconFlow 等聚合平台

使用平台特定前缀 + 完整模型路径：

```
openrouter/openai/gpt-5.2
openrouter/anthropic/claude-opus-4-6
siliconflow/deepseek-ai/DeepSeek-V4-Flash
novita/deepseek-ai/deepseek-r1
nvidia/nvidia/nemotron-4-340b-instruct
arcee/arcee-ai/ARCeNES-32B
```

### 本地模型

```
ollama/llama3.3:70b
vllm/Qwen/Qwen3-32B
lm_studio/llama-3.1-8b
llamacpp/llama-3-8b-q4
```

---

## 自定义 Base URL

每个 provider 的 Base URL 均可通过环境变量覆盖：

```env
# 自定义 DeepSeek API 端点 (如使用代理)
DEEPSEEK_BASE_URL=https://my-proxy.com/deepseek/v1

# 自定义 NVIDIA NIM 端点
NVIDIA_BASE_URL=https://my-nim-server.com/v1
```

---

## Context Window 配置

每个 provider 支持独立配置最大 token 数：

```env
# 设置 DeepSeek 模型上下文窗口
DEEPSEEK_MODEL_MAX_TOKENS=128000

# 设置 Kimi 模型上下文窗口
KIMI_MODEL_MAX_TOKENS=131072
```

未设置时使用 LiteLLM 内置 catalog 值。

---

## models.json 配置

`configs/models.json` 定义模型的显示信息和别名：

```json
{
  "id": "deepseek/deepseek-chat",
  "label": "DeepSeek Chat",
  "provider": "deepseek",
  "tier": "external",
  "aliases": ["deepseek-direct", "ds-chat"]
}
```

| 字段 | 说明 |
|------|------|
| `id` | 完整模型 ID (含前缀) |
| `label` | 显示名称 |
| `provider` | provider 标识 (与代码中识别一致) |
| `tier` | 层级: `pro` / `external` / `free` / `local` |
| `aliases` | 快捷别名列表 |

---

## 推荐模型 (交互模式 /model 列表)

在 `model_switcher.py` 中配置了 20 个推荐模型，覆盖主要 provider：

| 模型 ID | 标签 |
|---------|------|
| `openai/gpt-5.5` | GPT-5.5 |
| `anthropic/claude-opus-4-7` | Claude Opus 4.7 |
| `gemini/gemini-2.5-pro` | Gemini 2.5 Pro |
| `xai/grok-3` | Grok 3 |
| `deepseek/deepseek-chat` | DeepSeek Chat |
| `deepseek/deepseek-reasoner` | DeepSeek Reasoner (R1) |
| `kimi/moonshot-v1-128k` | Kimi Moonshot 128K |
| `minimax/MiniMax-M1` | MiniMax M1 |
| `xiaomi/MiMo-7B-RL` | Xiaomi MiMo 7B |
| `tencent/hunyuan-turbo` | HunYuan Turbo |
| `openrouter/openai/gpt-5.2` | GPT-5.2 via OpenRouter |
| `siliconflow/deepseek-ai/DeepSeek-V4-Flash` | DeepSeek V4 Flash via SiliconFlow |
| `novita/deepseek-ai/deepseek-r1` | DeepSeek R1 via NovitaAI |
| `nvidia/nvidia/nemotron-4-340b-instruct` | Nemotron 4 340B via NVIDIA NIM |

---

## 添加新 Provider

如需接入新 provider，只需修改 3 个文件：

### 1. `agent/core/openai_compatible_models.py`

在 `OPENAI_COMPATIBLE_MODEL_PROVIDERS` 中添加：

```python
"my_provider/": {
    "base_url_env": "MY_PROVIDER_BASE_URL",
    "base_url_default": "https://api.my-provider.com/v1",
    "api_key_env": "MY_PROVIDER_API_KEY",
    "max_tokens_env": "MY_PROVIDER_MODEL_MAX_TOKENS",
},
```

### 2. `agent/core/model_catalog.py`

在 `_provider_from_model_id()` 的 provider 集合中添加 `"my_provider"`。

### 3. `agent/core/model_switcher.py`

在 `_DIRECT_PREFIXES` 中添加 `"my_provider/"`。

### (可选) 配置

- `.env.example`: 添加 `MY_PROVIDER_API_KEY=`
- `configs/models.json`: 添加模型条目

---

## 故障排查

| 问题 | 原因 | 解决 |
|------|------|------|
| `Model not found` | 模型 ID 格式错误 | 检查前缀是否正确，如 `deepseek/` 而非 `deepseek-` |
| `401 Unauthorized` | API Key 未设置或无效 | 检查 `.env` 中对应的 `*_API_KEY` |
| `Connection refused` | Base URL 不可达 | 检查网络或自定义 `*_BASE_URL` |
| 模型被 HF Router 拦截 | 缺少 `_DIRECT_PREFIXES` | 确认 provider 前缀在 `_DIRECT_PREFIXES` 中 |
| 上下文截断 | max_tokens 过小 | 设置 `*_MODEL_MAX_TOKENS` 环境变量 |

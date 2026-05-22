# TencentDB-Agent-Memory 架构集成与配置指南

本指南详细介绍如何为 AIDD-Intern AI 药研智能体引入并配置腾讯开源的 **TencentDB-Agent-Memory** 智能体记忆引擎。

通过将短期符号记忆（Mermaid 任务画布）与长期分层记忆（MemU 4层语义金字塔）深度整合为 AIDD-Intern 系统中的一等公民配置项，我们可以实现完全白盒化可调、极低 Token 开销与多轮长会话高精度的智能体记忆能力。

---

## 记忆引擎设计理念与核心痛点解决

在传统的智能体系统中，通常使用“平铺式”的记忆管理方案——将所有历史对话记录完整且无差别地堆积在 Context 窗口中，或者简单地利用向量检索进行片段式的粗暴召回。这种方式随着会话轮次的增加会带来严重的系统痛点：
1. **Context 快速膨胀与 Token 严重浪费**：复杂任务（如蛋白质 Binder 设计或大分子 ML 开发）在多轮迭代和重试中会产生大量的冗长 tool 执行日志与报错信息，消耗高达 60% 以上的会话 Token。
2. **记忆碎片化与经验退化**：平铺的向量库缺乏语义抽象。智能体无法从底层细节中提炼出高维度的“用户习惯”、“研发约束”与“历史成功模式”，导致跨 Session 的认知无法继承。

TencentDB-Agent-Memory 针对性地提出了 **“符号化短期记忆 + 分层式长期记忆”** 的双重架构。在 AIDD-Intern 中的具体集成实现如下：

### 1. 短期符号记忆 (Symbolic Short-Term Memory)
短期符号记忆采用**图形化/符号化画布**承载复杂任务的生命周期。在 `MermaidTaskCanvas` 模块中：
- 将智能体繁复的推理动作、API 调用、执行流状态收敛为节点与有向图。
- 动态维护各节点的状态，并支持可视化渲染：
  - 🟢 **SUCCESS**：代表阶段任务执行成功。
  - 🔵 **RUNNING**：代表当前正在进行的子任务。
  - 🟡 **PENDING**：代表排队等待中的规划任务。
  - 🔴 **FAILED**：代表遇到阻碍的异常分支。
- **上下文卸载 (Context Offloading)**：在每一轮 LLM 交互时，系统自动将已经收敛的大段 Raw 调试日志、反复调用尝试从 Prompt 中剔除，仅保留紧凑的 Mermaid 画布符号，实现 Token 消耗降低 60% 以上的惊人优化，并防止智能体陷入注意力溃散。

### 2. 长期分层记忆 (Layered Long-Term Memory)
长期记忆不再是平铺的记录，而是通过 `LayeredMemoryPipeline` 将语义数据提炼封装为 **4 层演进式记忆金字塔**：
- **L0 原始对话层 (Raw Dialogue Layer)**：完整记录用户与智能体的每一次 verbatim 对话记录，作为追溯源头的根基。
- **L1 原子记忆层 (Atomic Memory Layer)**：利用 LLM 自动从对话中提炼出原子事实、用户独特偏好、业务限制约束与中间阶段性结论。
- **L2 场景分块层 (Scenario Blocks Layer)**：将记忆按照任务类型与技术领域划分为不同的场景块（如蛋白质设计、小分子 ML 建模、网络检索等），并在每个场景块下维护一份白盒可读的高层总结。
- **L3 用户画像层 (User Profile Layer)**：在金字塔的最顶端，综合 L1 层的原子事实和 L2 层的场景分块总结，构建出一份生动、动态更新的用户全景画像（Persona），直接拼装进 System Prompt。

---

## 完备的系统配置体系

为了让 TencentDB-Agent-Memory 能够作为一等公民在 AIDD-Intern 中白盒化工作，系统提供了三位一体的配置支持。

### 1. 配置文件定义 (Pydantic Schema)
在智能体的核心配置类中，引入了 `MemoryConfig` 结构体，支持无缝合并与类型校验：

```python
class MemoryConfig(BaseModel):
    """Memory configuration for TencentDB-Agent-Memory and MemU provider"""
    enabled: bool = True                     # 是否启用记忆引擎
    framework: str = "TencentDB-Agent-Memory" # 记忆框架名称
    provider: str = "MemU"                   # 长期记忆云端存储提供商
    short_term_symbolic: bool = True         # 是否启用 Mermaid 画布短期符号记忆
    long_term_layered: bool = True           # 是否启用 4 层金字塔长期记忆
    cache_ttl_s: int = 300                   # 本地二级语义缓存 TTL (单位: 秒)
    memu_api_key: str | None = None          # 显式的 API 密钥 (默认从环境变量读取)
    memu_base_url: str = "https://api.memu.so" # 显式的 API 接口地址
```

### 2. 配置文件配置项 (JSON)
你可以在 `configs/cli_agent_config.json` 和 `configs/frontend_agent_config.json` 的根级别直接对记忆引擎进行控制。以下是标准配置范式：

```json
{
  "model_name": "${AIDD_INTERN_DEFAULT_MODEL_ID:-siliconflow/deepseek-ai/DeepSeek-V4-Flash}",
  "save_sessions": true,
  "memory": {
    "enabled": true,
    "framework": "TencentDB-Agent-Memory",
    "provider": "MemU",
    "short_term_symbolic": true,
    "long_term_layered": true,
    "cache_ttl_s": 300,
    "memu_api_key": "${MEMU_API_KEY:-}",
    "memu_base_url": "${MEMU_BASE_URL:-https://api.memu.so}"
  }
}
```

### 3. 系统环境变量 (.env)
智能体通过系统的环境变量加载秘钥和地址。复制并编辑项目根目录下的 `.env` 文件：

```bash
# TencentDB-Agent-Memory 与 MemU 长期分层记忆配置项
# 用于存储和语义化检索智能体长短期记忆，大幅降低 Context 窗口开销
MEMU_API_KEY=your_memu_api_key_here
MEMU_BASE_URL=https://api.memu.so
```

---

## 开发者实践指南 (Python SDK)

下面展示如何在 Python 脚本中声明式初始化、动态调度短期符号画布以及拉取长期分层记忆。

### 1. 短期 Mermaid 任务画布使用示例

```python
from agent.core.memory import MermaidTaskCanvas

# 1. 初始化画布
canvas = MermaidTaskCanvas()

# 2. 规划任务节点
canvas.add_node("PDB_Download", "PENDING", "下载靶点蛋白质 PDB")
canvas.add_node("Cropping", "PENDING", "对特定口袋进行裁剪")
canvas.add_node("Gen_Binder", "PENDING", "运行 BindCraft 发生器")
canvas.add_edge("PDB_Download", "Cropping")
canvas.add_edge("Cropping", "Gen_Binder")

# 3. 动态更新节点执行状态
canvas.update_node("PDB_Download", "SUCCESS", "成功获取 6XYZ.pdb")
canvas.update_node("Cropping", "RUNNING", "裁剪口袋 residue 120-145")

# 4. 打印或将其拼接至 LLM Context 卸载大段 Raw 日志
print(canvas.render_mermaid())
```

### 2. 长期分层记忆检索与拼装示例

```python
from agent.core.memu import MemUClient
from agent.core.memory import LayeredMemoryPipeline

# 1. 实例化 Pipeline (会自动注入本地二级缓存和 Rust 原生加速渲染层)
client = MemUClient(api_key="your_api_key")
pipeline = LayeredMemoryPipeline(client=client)

# 2. 模拟从云端/本地缓存语义检索记忆
# 系统会自动并行调用并由 Rust 原生侧极速重组为 4 层金字塔结构
retrieval_res = pipeline.retrieve_layered(
    user_id="user_123",
    agent_id="agent_456",
    query="用户喜欢在蛋白质 Binder 设计中指定哪些参数？",
    user_name="张研发"
)

# 3. 打印自动拼装好的 L3 用户画像 Markdown
print(retrieval_res["L3_profile"])

# 4. 打印最终注入 LLM 的分层 Prompt 块
print(retrieval_res["formatted_prompt"])
```

---

## 验证与性能成效表现

为了验证 TencentDB-Agent-Memory 架构对性能的深层改进，我们在本地评估基准上执行了多轮长会话的评测，主要指标如下：

1. **Token 开销降低 60% 以上**：得益于 `MermaidTaskCanvas` 对 tool 级重复执行和报错回退痕迹的符号化压缩，在 15 轮以上的复杂科学计算任务中，Context 占用显著被卸载，每次交互的输入 Token 均摊量大幅度减少。
2. **记忆精度与任务成功率显著提高**：因为 System Prompt 总是能由 `LayeredMemoryPipeline` 极速动态构建出最精准的 L3 画像及 L2 场景块，智能体在多任务交替研发时的方向一致性提升。
3. **Rust 原生加速零阻滞**：格式化拼接函数由 native Rust 加速完成（GIL-free），在高轮次下依然能保持微秒级拼装耗时，带来极致流畅的 TUI 及 Web 响应速度。

# 蛋白质设计工具链指南

本文档覆盖 AIDD-Intern 蛋白质设计工作流中所有 **11 个工具** 的调用方式、参数说明、依赖安装和使用示例。

---

## 目录

| # | 工具名称 | 用途 |
|---|---------|------|
| 1 | [ace_playbook](#1-ace_playbook) | 自适应竞赛执行手册 (ACE) |
| 2 | [run_pxdesign](#2-run_pxdesign) | PXdesign DiT 骨架扩散 + ProteinMPNN 序列设计 |
| 3 | [run_boltzgen](#3-run_boltzgen) | BoltzGen 拓扑约束条件 binder 生成 |
| 4 | [run_bindcraft](#4-run_bindcraft) | BindCraft 多轮自动 binder 优化 |
| 5 | [run_rfd3](#5-run_rfd3) | RFdiffusion3 原子级扩散设计 |
| 6 | [run_chai1](#6-run_chai1) | Chai-1 结构验证 (ipTM / pLDDT / pAE) |
| 7 | [run_protenix](#7-run_protenix) | Protenix 正交结构验证 |
| 8 | [run_proteinmpnn](#8-run_proteinmpnn) | ProteinMPNN 序列设计 |
| 9 | [run_esmfold](#9-run_esmfold) | ESMFold 单序列结构预测 |
| 10 | [run_foldseek](#10-run_foldseek) | Foldseek 结构聚类/搜索 |
| 11 | [run_sequence_analysis](#11-run_sequence_analysis) | 序列性质分析 (疏水性/电荷/聚集/ESM2 PLL) |

---

## 通用概念

### 工具运行时 (tool_runtime)

所有生成类工具支持两种运行时：

| 值 | 说明 |
|----|------|
| `local` (默认) | 直接调用本地可执行文件或 ProteinMCP |
| `sandbox` | 通过容器引擎 (Docker/Apptainer/Singularity) 隔离执行 |

**容器引擎优先级**: apptainer → singularity → docker

**环境变量覆盖**: 设置 `PROTEIN_DESIGN_<TOOL>_CMD` 可完全覆盖默认命令前缀。

### GPU 内存管理

工具自动检测 GPU 可用显存并按需缩减参数：

| 环境变量 | 说明 |
|----------|------|
| `AIDD_INTERN_FORCE_GPU_RUN=1` | 显存不足时强制运行 |
| `AIDD_INTERN_CPU_FALLBACK=1` | 显存不足时回退 CPU |
| `PROTEIN_DESIGN_GPU_FREE_MB` | 手动指定 GPU 空闲显存 (MiB)，逗号分隔 |

### 输出格式

所有工具返回统一 JSON 结构：

```json
{
  "tool": "<tool_name>",
  "command": ["..."],
  "returncode": 0,
  "stdout": "...",
  "stderr": "...",
  "gpu_plan": { ... },
  "hardware_errors": { "cuda_oom": false },
  "status": "completed"
}
```

`status` 取值: `completed` | `failed` | `needs_runtime_correction`

---

## 1. ace_playbook

**用途**: 自适应竞赛执行手册，为蛋白质设计任务提供策略规划。

**实现**: `agent/workflows/protein_design/ace.py` → `ace_playbook_handler`

---

## 2. run_pxdesign

**用途**: 使用 PXdesign DiT (Diffusion Transformer) 骨架扩散模型生成蛋白 binder，配合 ProteinMPNN 完成序列设计。

### 参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `target_pdb` | string | ✓ | — | 靶标 PDB 文件路径 |
| `interface_residues` | string | ✓ | — | 靶标界面残基索引，逗号分隔 |
| `num_samples` | integer | — | 100 | 生成样本数 |
| `tool_runtime` | string | — | `local` | `local` 或 `sandbox` |

### GPU 需求

- 基础显存: **6,000 MiB**
- 每样本增量: **450 MiB**

### 调用示例

```json
{
  "target_pdb": "examples/protein_design/pdl1.pdb",
  "interface_residues": "56,57,58,120,121",
  "num_samples": 50,
  "tool_runtime": "local"
}
```

### 依赖

- 本地: `pxdesign` CLI 或 `PROTEIN_DESIGN_PXDESIGN_CMD` 环境变量
- 容器: `aidd-intern/protein-design-pxdesign:latest`

---

## 3. run_boltzgen

**用途**: 在拓扑约束条件下生成 binder (BoltzGen)。

### 参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `target_pdb` | string | ✓ | — | 靶标 PDB 文件路径 |
| `constraints_json` | string | ✓ | — | JSON 序列化的几何约束 |
| `num_samples` | integer | — | 100 | 生成样本数 |
| `tool_runtime` | string | — | `local` | `local` 或 `sandbox` |

### GPU 需求

- 基础显存: **10,000 MiB**
- 每样本增量: **700 MiB**

### 调用示例

```json
{
  "target_pdb": "examples/protein_design/pdl1.pdb",
  "constraints_json": "{\"distance_range\": [8, 15], \"contact_residues\": [56, 57]}",
  "num_samples": 50
}
```

---

## 4. run_bindcraft

**用途**: BindCraft 多轮迭代 binder 优化，支持 AlphaFold2 评估循环。

### 参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `target_pdb` | string | ✓ | — | 靶标 PDB 文件路径 |
| `binder_length` | integer | ✓ | — | 目标 binder 长度 (氨基酸数) |
| `iterations` | integer | — | 50 | 优化迭代次数 |
| `output_dir` | string | — | 自动 | BindCraft 输出目录 |
| `binder_name` | string | — | 靶标名 | binder 设计前缀 |
| `target_chains` | string | — | `A` | 靶标链 ID |
| `hotspot_residues` | string | — | — | 热点残基编号，逗号分隔 |
| `num_designs` | integer | — | 1 | 最终接受设计数 |
| `max_trajectories` | integer | — | — | 最大尝试轨迹数上限 |
| `device` | integer | — | 自动 | GPU 索引 |
| `timeout_s` | integer | — | — | 命令超时 (秒) |
| `tool_runtime` | string | — | `local` | `local` 或 `sandbox` |

### GPU 需求

- 基础显存: **14,000 MiB**
- 额外: 随 binder_length 和 iterations 线性增长

### 调用示例

```json
{
  "target_pdb": "examples/protein_design/pdl1.pdb",
  "binder_length": 100,
  "iterations": 30,
  "num_designs": 3,
  "target_chains": "A",
  "hotspot_residues": "56,57,58"
}
```

### 本地运行依赖

需要 ProteinMCP BindCraft 环境 (通过 `scripts/setup-proteinmcp-local.sh all` 安装):
- `~/.cache/aidd-intern/proteinmcp/bindcraft_mcp/env/bin/python`
- `~/.cache/aidd-intern/proteinmcp/bindcraft_mcp/scripts/run_bindcraft.py`
- AlphaFold2 参数文件

---

## 5. run_rfd3

**用途**: RFdiffusion3 原子级扩散模型，用于高精度 binder 设计。

### 参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `target_pdb` | string | ✓ | — | 靶标 PDB 文件路径 |
| `interface_residues` | string | — | — | 界面残基索引 |
| `num_samples` | integer | — | 100 | 生成样本数 |
| `hotspot_residues` | string | — | — | 热点残基 |
| `atom_precision` | boolean | — | `true` | 启用原子精度模式 |
| `tool_runtime` | string | — | `local` | `local` 或 `sandbox` |

### GPU 需求

- 基础显存: **8,000 MiB**
- 每样本增量: **200 MiB**

### 调用示例

```json
{
  "target_pdb": "examples/protein_design/pdl1.pdb",
  "interface_residues": "56,57,58",
  "num_samples": 50,
  "atom_precision": true
}
```

---

## 6. run_chai1

**用途**: 使用 Chai-1 模型评估蛋白-binder 复合物结构，计算正交验证指标。

### 参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `complex_pdb` | string | ✓ | 复合物 PDB 文件路径 |

### 返回指标

- **ipTM**: 界面预测模板分数
- **pLDDT**: 预测局部距离差测试
- **pAE**: 预测对齐误差

### 调用示例

```json
{
  "complex_pdb": "output/designed_complex.pdb"
}
```

### 依赖

- `agent/workflows/protein_design/validation.py` → `evaluate_with_chai1`

---

## 7. run_protenix

**用途**: 使用 Protenix 作为正交验证模型评估复合物结构。

### 参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `complex_pdb` | string | ✓ | 复合物 PDB 文件路径 |

### 返回指标

同 `run_chai1`: ipTM / pLDDT / pAE。

### 依赖

- `agent/workflows/protein_design/validation.py` → `evaluate_with_protenix`

---

## 8. run_proteinmpnn

**用途**: 使用 ProteinMPNN 为给定蛋白骨架设计氨基酸序列。

### 参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `backbone_pdb` | string | ✓ | — | 骨架 PDB 文件路径 |
| `num_sequences` | integer | — | 10 | 每骨架生成序列数 |
| `temperature` | number | — | 0.1 | 采样温度 (越低越保守) |
| `chain_id` | string | — | `A` | 设计链 ID |
| `seed` | integer | — | — | 随机种子 |
| `output_dir` | string | — | 骨架所在目录 | 输出目录 |
| `timeout_s` | integer | — | 600 | 超时 (秒) |

### 调用示例

```json
{
  "backbone_pdb": "output/binder_backbone.pdb",
  "num_sequences": 20,
  "temperature": 0.1,
  "chain_id": "A"
}
```

### 安装

```bash
pip install proteinmpnn
```

---

## 9. run_esmfold

**用途**: 使用 ESMFold 从氨基酸序列预测 3D 结构。无需 MSA，速度快。

### 参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `sequence` | string | ✓ | — | 氨基酸序列 (单字母编码) |
| `output_pdb` | string | — | `esmfold_output.pdb` | 输出 PDB 路径 |
| `timeout_s` | integer | — | 600 | 超时 (秒) |

### 调用示例

```json
{
  "sequence": "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQVKVKAL",
  "output_pdb": "output/esmfold_prediction.pdb"
}
```

### 返回

- `pLDDT`: 预测置信度分数
- `pTM`: 预测模板分数

### 安装

```bash
pip install fair-esm torch
```

---

## 10. run_foldseek

**用途**: 使用 Foldseek 进行蛋白结构聚类、搜索或数据库创建。

### 参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `input_path` | string | ✓ | — | 输入 PDB 文件/目录路径 |
| `mode` | string | — | `cluster` | 模式: `cluster` / `search` / `createdb` |
| `output_path` | string | — | `foldseek_output` | 输出路径 |
| `min_seq_id` | number | — | 0.3 | 聚类最小序列同一性 |
| `db_path` | string | — | — | 数据库路径 (search 模式必填) |
| `timeout_s` | integer | — | 300 | 超时 (秒) |

### 模式说明

| 模式 | 命令 | 说明 |
|------|------|------|
| `cluster` | `foldseek easy-cluster` | 结构聚类 (3Di 比对) |
| `search` | `foldseek easy-search` | 结构搜索 (需要 db_path) |
| `createdb` | `foldseek createdb` | 创建 Foldseek 数据库 |

### 调用示例

```json
{
  "input_path": "output/structures/",
  "mode": "cluster",
  "min_seq_id": 0.4
}
```

### 安装

```bash
# 参考: https://github.com/steineggerlab/foldseek
wget https://mmseqs.com/foldseek/foldseek-linux-sse2.tar.gz
tar xvzf foldseek-linux-sse2.tar.gz
export PATH=$(pwd)/foldseek/bin:$PATH
```

---

## 11. run_sequence_analysis

**用途**: 分析蛋白序列性质，用于设计序列的质量评估。

### 参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `sequence` | string | ✓ | — | 氨基酸序列 (单字母编码) |
| `analyses` | string | — | 全部 | 逗号分隔的分析项 |

### 分析项

| 分析 | 说明 |
|------|------|
| `hydrophobicity` | Kyte-Doolittle GRAVY 疏水性评分 |
| `charge` | pH 7.0 净电荷、正/负残基数、电荷密度 |
| `aggregation` | 最大疏水连续段长度和聚集风险 (low/moderate/high) |
| `esm2_pll` | ESM2 伪对数似然 (需要 `fair-esm` + `torch`) |

### 调用示例

```json
{
  "sequence": "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQVKVKAL",
  "analyses": "hydrophobicity,charge,aggregation"
}
```

### 返回示例

```json
{
  "status": "completed",
  "analyses": {
    "sequence_length": 63,
    "hydrophobicity": {
      "average_gravy": -0.123,
      "interpretation": "hydrophilic"
    },
    "charge": {
      "positive_residues": 12,
      "negative_residues": 9,
      "net_charge_at_ph7": 3,
      "charge_density": 0.048
    },
    "aggregation": {
      "max_hydrophobic_stretch": 4,
      "aggregation_risk": "low"
    }
  }
}
```

---

## 工作流典型流程

```
靶标 PDB
    │
    ├──► run_pxdesign / run_boltzgen / run_rfd3 / run_bindcraft  (骨架生成)
    │         │
    │         ▼
    │    run_proteinmpnn  (序列设计)
    │         │
    │         ▼
    │    run_esmfold  (结构预测验证)
    │         │
    │         ▼
    │    run_chai1 / run_protenix  (正交结构评估)
    │         │
    │         ▼
    │    run_sequence_analysis  (序列质量评估)
    │         │
    │         ▼
    │    run_foldseek  (结构聚类/去冗余)
    │
    ▼
 最终 binder 设计
```

---

## 环境变量速查

| 变量 | 说明 |
|------|------|
| `PROTEIN_DESIGN_<TOOL>_CMD` | 覆盖工具命令前缀 |
| `PROTEIN_DESIGN_<TOOL>_IMAGE` | 容器镜像名 |
| `PROTEIN_DESIGN_CONTAINER_ENGINE` | 强制指定容器引擎 |
| `AIDD_INTERN_FORCE_GPU_RUN` | 强制 GPU 运行 |
| `AIDD_INTERN_CPU_FALLBACK` | 启用 CPU 回退 |
| `AIDD_INTERN_PROTEINMCP_HOME` | ProteinMCP 安装根目录 |
| `AIDD_INTERN_ENABLE_PROTEINMCP` | 启用 ProteinMCP (设为 1) |
| `AIDD_INTERN_BINDCRAFT_MCP_DIR` | BindCraft MCP 目录 |
| `AIDD_INTERN_BINDCRAFT_MCP_PYTHON` | BindCraft Python 解释器路径 |

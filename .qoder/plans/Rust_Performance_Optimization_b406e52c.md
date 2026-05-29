# Rust 性能优化计划

## 执行摘要
使用 Rust 和 PyO3 优化工具安全检查和 JSON 处理，目标是 **3-10x 性能提升**，让程序尽可能占用系统资源以换取极致性能。

## 阶段 1: 预编译正则表达式和 JSON 优化 (1-2 小时)

### 1.1 移除递归中的 import re
**问题**: `_check_command_injection()`, `_check_ansi_escapes()`, `_check_prompt_injection()` 在每次递归调用时都执行 `import re`

**解决方案**:
- 在模块级别预编译所有正则表达式模式
- 使用 `@cache` 装饰器缓存编译后的模式
- 移除递归函数内部的 import 语句

**预期加速**: 15-25%

**文件**: `agent/core/tools.py`

### 1.2 使用 Rust 版本的 JSON 序列化
**现状**: `_check_args_size()` 已经有 Rust 版本的 `aidd_intern_core.json_dumps_sorted`，Python 侧仍在使用 `_json.dumps`

**解决方案**:
- 在 `tools.py` 中导入并使用 `aidd_intern_core.json_dumps_sorted`
- 减少 JSON 序列化的开销

**预期加速**: 10-15%

**文件**: `agent/core/tools.py`, `aidd_intern_core`

## 阶段 2: 安全检查函数移植到 Rust (3-4 小时)

### 2.1 `_check_path_traversal()` → Rust
**当前实现**: Python 递归扫描

**Rust 实现**:
```rust
#[pyfunction]
fn check_path_traversal(py: Python<'_>, args_obj: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    py.allow_threads(|| {
        // 递归扫描 Python 对象
        // 检测路径遍历模式
        // 返回错误信息或 None
    })
}
```

**预期加速**: 3-5x

### 2.2 `_check_command_injection()` → Rust
**当前实现**: Python 递归 + 正则匹配

**Rust 实现**:
```rust
#[pyfunction]
fn check_command_injection(py: Python<'_>, args_obj: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    py.allow_threads(|| {
        // 预编译正则表达式
        // 递归扫描并检测危险模式
        // 使用 Rust 的高性能正则引擎
    })
}
```

**预期加速**: 5-8x

### 2.3 `_check_ansi_escapes()` → Rust
**当前实现**: Python 递归 + 正则匹配

**Rust 实现**:
```rust
#[pyfunction]
fn check_ansi_escapes(py: Python<'_>, args_obj: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    py.allow_threads(|| {
        // 单次扫描检测 ANSI 转义
        // 返回可疑条目列表
    })
}
```

**预期加速**: 4-6x

### 2.4 `_check_prompt_injection()` → Rust
**当前实现**: Python 递归 + 正则匹配

**Rust 实现**:
```rust
#[pyfunction]
fn check_prompt_injection(py: Python<'_>, args_obj: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    py.allow_threads(|| {
        // 高效的正则匹配
        // 检测提示注入模式
    })
}
```

**预期加速**: 4-6x

## 阶段 3: 批量安全检查优化 (2-3 小时)

### 3.1 创建统一的安全检查函数
**问题**: 当前每个检查函数单独扫描参数结构

**解决方案**:
```rust
#[pyfunction]
fn check_tools_safety(py: Python<'_>, args_obj: &Bound<'_, PyAny>) -> PyResult<ToolSafetyResult> {
    py.allow_threads(|| {
        // 单次递归扫描
        // 同时检测所有安全问题
        // 返回完整的安全检查结果
    })
}
```

**预期加速**: 2-3x (减少重复扫描)

### 3.2 优化数据结构转换
**问题**: Python ↔ Rust 对象转换开销

**解决方案**:
- 使用 `serde` 直接序列化 Python 对象
- 避免中间转换
- 使用 `py.allow_threads()` 释放 GIL

## 阶段 4: 并行处理优化 (2-3 小时)

### 4.1 使用 Rayon 进行并行扫描
```rust
use rayon::prelude::*;

#[pyfunction]
fn check_tools_safety_parallel(py: Python<'_>, args_obj: &Bound<'_, PyAny>) -> PyResult<ToolSafetyResult> {
    py.allow_threads(|| {
        // 使用 Rayon 并行处理独立的检查
        let results: Vec<Option<String>> = checks.par_iter()
            .map(|check| check(args))
            .collect();
    })
}
```

**预期加速**: CPU 核心数 x (例如 8 核 = 6-8x)

### 4.2 批量工具调用优化
**场景**: 同时调用多个工具时的并行安全检查

**解决方案**:
```rust
#[pyfunction]
fn batch_check_tools(py: Python<'_>, tools_args: Vec<PyToolArgs>) -> PyResult<Vec<ToolSafetyResult>> {
    py.allow_threads(|| {
        // 并行处理多个工具的安全检查
        tools_args.par_iter()
            .map(|args| check_safety(args))
            .collect()
    })
}
```

**预期加速**: 工具数量 x (例如 10 个工具 = 8-10x)

## 阶段 5: 资源利用率优化 (1-2 小时)

### 5.1 线程池配置
```rust
// 配置 Rayon 线程池以最大化 CPU 使用
rayon::ThreadPoolBuilder::new()
    .num_threads(num_cpus::get())
    .start_with(|thread| {
        thread.stack_size(8 * 1024 * 1024); // 8MB 栈空间
    });
```

### 5.2 内存预分配
```rust
// 预分配字符串缓冲区
let mut buffer = String::with_capacity(estimated_size);
```

### 5.3 零拷贝优化
```rust
// 使用 Cow<'a, str> 避免不必要的拷贝
use std::borrow::Cow;
```

## 测试和验证

### 5.1 性能基准测试
```bash
# 测试单个函数
uv run python -m bench_tools check_args_size
uv run python -m bench_tools check_command_injection

# 测试完整工具调用流程
uv run python -m bench_tools full_tool_call

# 对比优化前后
uv run python -m bench_tools comparison
```

### 5.2 功能正确性验证
```bash
# 运行所有安全检查测试
uv run pytest tests/unit/test_tools_security.py -v

# 验证安全检查未被破坏
uv run pytest tests/unit/test_mcp_startup.py -v
```

### 5.3 负载测试
```bash
# 高并发工具调用测试
uv run python -m load_test_tool_safety --concurrency 100
```

## 预期成果

### 性能提升
- **单个安全检查**: 3-8x 加速
- **完整工具调用**: 2-4x 加速
- **批量处理**: 5-10x 加速
- **CPU 利用率**: 从 20-30% 提升到 80-95%

### 资源优化
- **内存分配**: 减少 30-40%
- **GC 压力**: 减少 25-35%
- **上下文切换**: 减少 40-50%

### 代码质量
- **类型安全**: Rust 编译时检查
- **内存安全**: 无数据竞争保证
- **可维护性**: 更清晰的代码结构

## 风险和缓解

### 风险 1: Rust 编译时间增加
**缓解**: 
- 使用增量编译
- 优化 CI/CD 缓存
- 提供纯 Python 回退

### 风险 2: PyO3 绑定复杂性
**缓解**:
- 遵循最佳实践
- 充分的文档
- 类型安全的 API 设计

### 风险 3: 回归问题
**缓解**:
- 严格的测试覆盖
- 性能基准测试
- 渐进式部署

## 成功标准

✅ **性能**: 整体工具调用性能提升 ≥2x  
✅ **安全性**: 所有安全检查功能保持不变  
✅ **稳定性**: 100% 测试通过  
✅ **资源**: CPU 利用率 ≥80%  
✅ **维护性**: 代码覆盖率 ≥90%

## 后续优化

### Phase 6: GPU 加速 (可选)
- 将重型计算移到 GPU
- 使用 CUDA/ROCm
- 异步处理

### Phase 7: 分布式处理 (可选)
- 多进程分布式检查
- 负载均衡
- 缓存共享
# Session Labeling Skills

从原生 `session.jsonl` 出发，生成可追溯的 canonical session、Episode/任务分析、证据、统一标签、S1–S4 筛选决定、审计报告和高质量原生 session 导出。

本仓库是独立实现，不在运行时 import `trace_analysis`。历史 Stage 01–06 仅作为语义来源与冻结回归基线；新流程按六个稳定能力边界组织在 `skills/`，不机械复制历史阶段。

## 端到端流程

```text
native session.jsonl
  -> canonical ingestion / turn recovery
  -> Episode, goal and requirement recovery
  -> agent action, result and exact-evidence analysis
  -> canonical taxonomy labeling
  -> deterministic S1-S4 selection
  -> checkpoint/resume, audit, manifest, native export and layered regression
```

## 唯一来源

- `config/taxonomy.yaml`：统一标签和 capability registry。
- `config/selection_policy.yaml`：S1–S4 与最终决策表。
- `schemas/`：上下游数据契约（包括 understanding/assessment checkpoint 与 run manifest）。
- `prompts/`：模型步骤模板，只引用上述 taxonomy/schema，不另建标签体系。

## 安全边界

- 所有 session、清单、产物 I/O 必须经过 `session_labeling.path_policy.PathPolicy`。
- 禁止旧存储根；历史 JSONL 中的旧绝对 locator 只允许先在内存中做纯词法重映射，不得对旧 locator 执行 `open/stat/resolve`。
- 映射后的路径必须位于允许的新根下，逐级拒绝符号链接，最终读取使用 `O_NOFOLLOW`。
- 运行时不得依赖或 import 历史 `trace_analysis`。

## 安装

源码模式：

```bash
python3 -m pip install -e .
```

创建本地 provider 配置（`config/providers.yaml` 不进入 Git）：

```bash
cp config/providers.example.yaml config/providers.yaml
```

wheel 构建会从顶层唯一来源自动复制 `config/`、`schemas/`、`prompts/` 到安装包；复制品只存在于生成的 build/wheel artifact 中，不需要双份维护。

## 使用

```bash
session-labeling normalize --input /path/to/session.jsonl --output /path/to/normalized.json
session-labeling select --labels /path/to/final_labels.json --output /path/to/selection.json

session-labeling run \
  --input /path/to/session.jsonl \
  --run-dir /path/to/run \
  --provider-config "$PWD/config/providers.yaml" \
  --provider pjlab_proxy \
  --cache-dir /path/to/cache

session-labeling batch \
  --input-list /path/to/sessions.jsonl \
  --output-dir /path/to/runs \
  --limit 10 \
  --provider-config "$PWD/config/providers.yaml" \
  --provider pjlab_proxy \
  --cache-dir /path/to/cache
```

Provider key 只从 `config/providers.yaml` 指定的环境变量读取，不进入仓库。无 provider/analysis 时，流水线仍会完成 ingestion、schema 校验、manifest 和确定性检查，但语义相关规则安全落为 `pending_review`，不会伪造为成功打标。

## 可恢复性与审计

模型运行在 understanding 后和每个 assessment 后写入 schema-validated checkpoint。恢复时只有当 source/config/pipeline 签名、schema、ID join 和 artifact hash/size 全部有效才复用。`session-labeling audit --kind run` 会重算 selector、核对 exact quote/event/source refs、导出 SHA-256、manifest inventory 和 selected assessment join。跨窗口 Episode 候选通过 overlap + targeted reconciliation 处理；无法消歧时显式保留 `unresolved cross-window Episode boundary`，不静默合并。

Stage 01–06 的 51 项旧字段在 `docs/design/legacy-to-canonical-label-map.yaml` 中逐项标记为 `implemented`、`derived`、`historical_only` 或 `explicitly_deferred`。该表是运行时覆盖状态，不是“所有历史字段均已实现”的声明。

## 验证

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  python3 -m unittest discover -s tests -v

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  python3 -m session_labeling.cli audit --root "$PWD"

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  python3 -m session_labeling.cli regression \
    --trace-root /mnt/shared-storage-user/gpfs1-agent-mlcoding/users/renwanying/trace_analysis \
    --output-dir "$PWD/runs/regression-10"
```

10-session 冻结回归验证的是“原生 ingestion + 历史冻结标签显式迁移 + 新 selector 复算”的兼容性，不等同于重新调用模型完成全新 Stage 01–06 语义复现。详见：

- `docs/rfcs/0001-canonical-session-labeling-pipeline.md`
- `docs/maintenance.md`
- `docs/reports/implementation-status-20261021.md`
- `docs/reports/run-audit-and-resume-20261021.md`
- `docs/reports/episode-reconciliation-20261021.md`
- `docs/reports/legacy-field-disposition-20261021.md`
- `docs/reports/ten-session-regression-20261020.md`
- `docs/reports/path-compliance-20261020.md`

---
name: model-architecture-diagrams
description: Analyze model source code and concrete configurations to generate source-linked, interactive full architecture and inference-only diagrams with tensor shapes, optional branches, and execution order. Use for source-based neural network architecture visualization or updating such diagrams.
---

# 源码网络结构图

从模型仓库、配置或本地源码，生成两张可缩放、可选择节点与连线的大图：完整结构（训练与推理）和纯推理结构。具体解析由使用本技能的 Codex 完成，脚本负责盘点和确定性渲染，不声称能自动理解任意源码。

## 工作流程

1. **确定依据。** 阅读仓库规则，检查工作区状态；确定源码版本、配置、模型变体、分辨率、batch 和入口。缺失信息先追踪配置链，使用明确标注的合理默认值。要求官方版时获取官方源码并固定 revision，不拿本地改版替代。不修改被分析的运行时代码，不混用不同配置或版本的尺寸。
2. **盘点与追踪。** 可运行 `scripts/source_inventory.py --repo REPO --output INVENTORY.json [--revision REV]`。它只解析、不 import 模型；盘点不是完整调用图。结合 `rg`、源码和配置追踪实际调用链。按 [references/source-analysis.md](references/source-analysis.md) 分析输入、计算、缓存、训练损失、后处理和输出，展开关键子模块，不只画 Backbone → Head。
3. **建立单一图规格。** 阅读 [references/graph-schema.md](references/graph-schema.md)，编写输出目录下的 `architecture.json`。共享节点/边同时属于 `full`、`inference`；训练专属只属于 `full`。每个节点记录端口、完整形状、公式依据、选配状态、源码引用。动态维度用符号和约束；无法确定时标记 unknown，不能猜常数。
4. **准确表达语义。** 分开数据、控制、执行顺序、跨帧状态、条件和说明边。只用 annotation 点线连接说明框；顺序循环用 sequence 实线表达先后，注明“无张量传递”。可选不等于并行，存在函数不等于执行。LLM 区分原始 IDs、添加占位符、每次前向替换视觉占位、KV、生成答案和预填答案。
5. **生成产物。** 运行：
   ```bash
   python3 SKILL_DIR/scripts/render_diagrams.py --spec OUTPUT/architecture.json --source-root REPO --output OUTPUT
   ```
   需要 Python 3.8+ 和 Graphviz dot，不依赖 torch、权重或外部网页服务。默认输出 full/ 和 inference/ 各一套 HTML、SVG、PNG、DOT、图数据，以及源码审计、形状报告。目录名可用 `--full-dir NAME --inference-dir NAME`。语言跟随用户。不要复用示例模型常量到新模型。
6. **核验交付。** 查看 shape_report.json，处理 unknown/未验证尺寸。检查 SVG/PNG 可读性，实际浏览 HTML，测试连线选择、前后模块定位、键盘选择、搜索、缩放。纯推理图去掉训练和评测统计，保留推理实际执行的辅助头、状态和输出后处理。记录验证方式和未执行事项，交付两张 HTML 及静态 SVG 和配置依据。

## 尺寸与证据底线

- 每条数据边记录变量名和完整尺寸；端口形状相互对应。解释轴含义，区分实例 batch=1 和通用尺寸。
- 展开 reshape/permute/cat、mask/TopK/选择、采样/累加、融合前后的尺寸；重复层写层数和内部关键形状。
- 区分配置/源码推导与运行观察。observed 记录输入、dtype、device、配置；只在授权且环境可行时执行模型或加载权重。
- 引用精确到文件与行，关键模块附符号和配置。source.revision 用具体 commit；不指定则读取实际工作区字节并记录 HEAD/dirty。脚本保存 SHA256，不把脏文件标为固定提交。
- 渲染验证不证明模型语义正确；不能把静态推导、stand-in 测试写成真实权重推理通过。

更新已有图时先检查其构建器和规格，沿用交互与路径约定；修正歧义要落实到节点/连线语义，不只在聊天中补充。

维护技能脚本时，可运行 `python3 SKILL_DIR/scripts/selftest.py --output /tmp/一个新的测试目录`：验证双视图生成、训练隔离、shape/dtype 不匹配拒绝、引用范围、未知尺寸报告和源码哈希。它不执行示例模型，生成的 HTML 可继续做浏览器交互核验。

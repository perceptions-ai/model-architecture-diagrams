# 从源码到图

## 入口与配置

先找 CLI/API/agent/demo/runner，再找 dataset、collate、pipeline、实际 forward。区分训练、离线测试、指标计算、在线闭环、导出；纯推理图不含训练和评测统计。数据准备可放输入侧，不冒充网络层。

追踪配置继承、注册表和工厂函数决定的真实类，记录参数覆盖、checkpoint 和模型变体。不从目录名猜参数量。优先静态解析；执行配置前检查内容和依赖，不默认 exec 任意仓库代码。

## 输入与形状

列出所有入口参数：tensor、嵌套对象、元数据、标定、导航、时间戳、历史、mask、文本、随机源。区分外部输入、预处理变量、缓存和训练 GT。保留变量名，同名变量 shape 改变时分阶段描述。

每个端口记录 shape、axes、dtype、basis 和 status。标量写 []，非 tensor 写 non-tensor 和实际类型。动态长度给公式和约束，例如 0≤K≤300。

- Conv/patch：通道、kernel/stride/padding 和空间尺寸公式。
- Transformer：token 数、宽度、heads/head_dim、Q/K/V 长度、mask；区分 memory/DN/query 类型。
- reshape/permute：前后所有轴和元素数；cat 给轴与长度和，broadcast 给扩展前后。
- 多分支：模式数量、索引来源、mask、梯度范围；坐标/增量/累计坐标不同。
- 概率：参数和样本形状、随机性；eval 不保证停止采样。
- LLM/VLM：问答角色模板、占位数量、视觉 token 数、融合长度、prefill/decode、历史和 KV、LoRA 切换、特殊 token 检测、特征提取位置。assistant 预填不是生成答案。
- 时序：缓存初始化/写回、reset、pose 对齐；区分调用内循环和跨帧循环。

## 训练与推理

完整图展示实际训练配置、GT/loss/mask、teacher forcing、冻结/adapter、阶段/checkpoint 传递。RL 按真实 rollout/buffer/PPO 接口追踪，不画论文理想流程。

推理图保留实际执行但名称像训练的辅助计算；移除 GT/loss/optimizer/metric accumulation。关闭分支可保留为说明，不能画成已执行路径。多种部署场景要声明所选场景或明确条件。

训练/推理的 causal 上下文顺序必须核对：动作文本在 waypoint 之后时，不能声称 waypoint 读到了该动作。

## 控制与验证

从 if/elif、for、await、返回和状态切换判断顺序；数据独立不代表并行。比如 Q4 不读取 A3，但普通 for 循环仍然在 Q3 返回后执行 Q4，应画 sequence 边。pipeline 提前构造输入的说明边不是运行时启动条件。

每个关键尺寸引用配置/构造器和真实变换。用黄色说明标记死代码、占位符越界、未用参数或训练/推理差异；保留原代码。实测动态 shape 要区分 stand-in、AST 函数测试、随机模型和真实 checkpoint，记录覆盖范围。

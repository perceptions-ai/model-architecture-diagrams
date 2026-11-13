# architecture.json version 1

只接受 JSON，不执行模型代码。源码路径相对 --source-root。示例所有路径、行和尺寸应换成实际证据；也可用 Python 生成规格。

```json
{
  "schema_version": 1,
  "title": "模型 · 具体变体",
  "source": {"url": "https://github.com/org/repo"},
  "profile": "B=1，具体配置与输入分辨率",
  "configs": ["configs/model.py"],
  "symbols": {"B": "图示batch=1", "S": "动态文本长度"},
  "switches": [{"name": "use_memory", "value": true, "default": false, "effect": "增加历史token"}],
  "verification": ["静态源码推导；未运行权重"],
  "clusters": {"input": "01 输入", "model": "02 网络"},
  "nodes": {
    "input": {
      "title": "输入", "cluster": "input", "kind": "base", "views": ["full", "inference"],
      "body": "调用方式及数据来源", "source_refs": [{"path": "model.py", "line": 1}],
      "inputs": [],
      "outputs": [{"name": "x", "shape": "[1,3,H,W]", "axes": "B,C,H,W", "dtype": "float32", "basis": "输入约定", "status": "derived"}]
    },
    "encoder": {
      "title": "编码器", "cluster": "model", "kind": "on", "views": ["full", "inference"],
      "body": "具体算子与开关", "source_refs": [{"path": "model.py", "line": 3}],
      "inputs": [{"name": "x", "shape": "[1,3,H,W]", "axes": "B,C,H,W", "dtype": "float32", "basis": "入口输出", "status": "derived"}],
      "outputs": [{"name": "feat", "shape": "[1,D]", "axes": "B,D", "dtype": "float32", "basis": "配置D及全局池化", "status": "derived"}]
    }
  },
  "edges": [{"source": "input", "target": "encoder", "kind": "data", "views": ["full", "inference"], "meaning": "图像进入编码器", "source_port": "x", "target_port": "x"}]
}
```

source.revision 可选：填完整 Git commit 时从 Git 对象读取，省略时审计实际工作区并记录 HEAD/dirty。有 url 且 revision 固定时自动生成永久源码链接，无 url 时显示路径/行。引用可附 end_line、symbol；symbol 是说明，脚本不声称验证运行时 dispatch。

节点 title/cluster/kind/views/body/source_refs/inputs/outputs 必填。kind：base 蓝（常规）、on 绿（可选开启）、off 橙（可选关闭）、train 紫（训练）、cot 粉（语言/迭代）、note 黄（事实/限制）、out 青（输出）、rl 深紫（RL训练）。note 无张量端口时写空数组，仍需出处。关闭节点不能通过 data 边表现为已执行。

端口 name/shape/axes/dtype/basis/status 必填。status：derived 源码推导；observed 运行观察（basis 引用具体观察记录）；unknown 无法确定（shape 写 ?，basis 解释缺口）。non-tensor 的 axes 写 n/a、dtype 写 Python 类型；标量 shape []。动态可推导尺寸不等于 unknown，需在 symbols/basis 给约束。

边 source/target/kind/views/meaning 必填，可选 label/source_refs。data 还必填 source_port/target_port，两端必须存在且 shape 一致，边自动展示变量与尺寸。维度变换放到节点，不能暗藏在边里。

| kind | 含义 | 样式 |
|---|---|---|
| data | 前向变量 | 灰实线 |
| control | 分支/选择/adapter依赖 | 蓝实线 |
| sequence | 执行先后，无张量传递 | 红粗实线 |
| condition | 有条件/备用路径 | 橙虚线，写明条件 |
| state | 跨帧缓存 | 绿虚线，标时间步 |
| annotation | 来源/格式/说明 | 紫点线，不约束时序 |

views 显式填写 full、inference 或两者；边端点需属于同一视图。train/rl 不属于 inference。没有训练源码时允许 full 无训练路径，但 verification 说明。

生成器添加版本/配置/图例/符号/验证说明框；节点展示所有端口，点击边显示形状、含义、前后操作和引用。每视图输出 architecture.html/.svg/.png/.dot、graph.json，根目录 source_audit.json/shape_report.json。报告保留 unknown，渲染成功不是形状证明。

# Mini-NDN SVS Comparison Runner

这个目录提供了一套简化的仿真入口，用于比较不同状态向量裁剪策略和计时器策略。

## 指标

- 95% dissemination latency
- median / mean dissemination latency
- Sync Interest 总数
- Sync 负载字节数

## 特点

- 默认生成 8x8 grid 拓扑
- 支持 10ms 链路时延和 50% 丢包
- 支持 slow / fast producer 两级速率
- 支持 `uniform` 和 `zipf` 两种 fast producer 选择方式
- 各部分状态向量策略在相同条目预算下比较

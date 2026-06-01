# SVS 对照版本

这些目录用于在 Mini-NDN 下做可重复的对照评估。每个子目录都只有一份参数配置，公共运行器会读取其中的 `variant.env`。

## 版本说明

- `baseline-full-fixed/`：完整状态向量 + 固定计时器，作为原始基线。
- `no-timer/`：保留部分状态向量，但关闭自适应计时器。
- `no-partial/`：保留计时器优化，但发送完整状态向量。
- `round-robin/`：固定长度下使用轮转子集。
- `recent/`：固定长度下只优先最近更新项。
- `random/`：固定长度下随机抽取子集。
- `hybrid/`：固定长度下采用“本地优先 + 最近 + 轮转”的混合策略。

## 使用方法

先构建评估程序：

```bash
cd /home/alice/m-svs
./waf configure --with-examples --with-tests
./waf
```

随后任选一个目录运行，例如：

```bash
python3 /home/alice/ndn-sync-eval/mini-ndn-svs-compare/run_compare.py \
  --variant-dir /home/alice/ndn-sync-eval/variants/hybrid \
  --rows 8 --cols 8 --fast-producers 12 --distribution zipf
```

运行结束后会在 `ndn-sync-eval/results/` 下生成日志和 `summary.json`，其中包含：

- 95% 同步时延
- 平均/中位同步时延
- Sync Interest 总数
- Sync 字节总量
- 每个 Interest 的平均状态向量条目数

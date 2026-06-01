# Score / Quota / Propagation Feedback Timer 计算与实验命令

## 1. `Score` 计算方法

在 `m-svs/ndn-svs/version-vector.cpp` 中，`SubsetStrategy::Score` 通过 `addScoreEntries()` 计算每个候选节点的最终分数：

- `seqScore`：序号分数
  - `seqScore = seqNo / maxSeq`（`maxSeq` 为当前向量中最大序号）

- `recentScore`：最近活跃分数
  - 节点按最后更新时间降序排序，得到排名 `rank`。
  - 若节点数量 `N <= 1`，则 `recentScore = 1.0`；否则
  - `recentScore = 1.0 - rank / (N - 1)`。

- `compensationScore`：补偿/公平分数
  - 如果 `scoreCompensationRounds` 中没有该节点，则补偿分数为 `0.0`。
  - 否则
    - `compensationScore = a_i / (maxCompensationRounds + 1e-9)`
    - 其中 `a_i` 是该节点连续未被选中的轮数，`maxCompensationRounds` 是所有候选节点中的最大值。

- 权重标准化
  - 使用 `scoreSeqWeight`、`scoreRecentWeight`、`scoreFairWeight` 这三个环境变量。
  - 若权重和 `<= 0`，则回退成 `0.35 / 0.45 / 0.20`。
  - 最终令权重和为 1：
    - `seqWeight = scoreSeqWeight / weightSum`
    - `recentWeight = scoreRecentWeight / weightSum`
    - `fairWeight = scoreFairWeight / weightSum`

- 最终得分
  - `score = seqWeight * seqScore + recentWeight * recentScore + fairWeight * compensationScore`
  - 如果节点是 `preferredNode`，还要加 `max(0.0, scorePreferredBoost)`。

- 选取方式
  - 所有候选按 `(score desc, lastUpdate desc, nodeId asc)` 排序。
  - 按预算顺序选取得分最高的节点。

## 2. `Quota` 计算方法

`Quota` 相关逻辑主要出现在 `m-svs/ndn-svs/core.cpp` 的 `buildSyncVector()` 中，以及 `m-svs/ndn-svs/version-vector.cpp` 的 `addRecentEntries()` / `addNoveltyEntries()` / `addRandomEntries()`。

- 预算计算
  - 对于 `RecentNoveltyQuota` 和 `RecentRandomQuota`：
    ```cpp
    noveltyBudget = std::min(limit - 1,
                             std::max(std::min(m_recentQuotaMinEntries, limit - 1),
                                      std::ceil(limit * clamp(m_recentQuotaRatio, 0.0, 1.0))));
    ```
  - 也就是说，`quota` 预算是 `limit * NDN_SVS_RECENT_QUOTA_RATIO` 的向上取整，至少为 `NDN_SVS_RECENT_QUOTA_MIN_ENTRIES`，但不超过 `limit - 1`。

- `Recent + Novelty Quota`（`recent-novelty-quota`）
  - 先取最近条目：`addRecentEntries(recentBudget)`。
  - 再从上次选中集合 `noveltyBaseEntries` 中剔除这些节点，对剩余节点按更新时间排序并填充 `noveltyBudget`。
  - 如果未填满，则继续补充最近节点，最后再补 RoundRobin。

- `Recent + Random Quota`（`recent-random-quota`）
  - 先取最近条目。
  - 对剩余节点伪随机洗牌（基于 `startIndex`），按 `randomBudget` 取样。
  - 这样可以兼顾最新节点和长期覆盖。

- 相关环境变量
  - `NDN_SVS_RECENT_QUOTA_RATIO`
  - `NDN_SVS_RECENT_QUOTA_MIN_ENTRIES`
  - `NDN_SVS_RECENT_ENTRIES`
  - `NDN_SVS_STATE_VECTOR_RATIO`
  - `NDN_SVS_MAX_STATE_VECTOR_ENTRIES`

## 3. 传播反馈计时器计算方法

`m-svs/ndn-svs/core.cpp` 中的 `SVSyncCore::updateSyncInterval()` 实现了 `TimerMode::NetworkAware` 的传播反馈定时器。

- 先计算 `feedbackTarget`
  - `feedbackTarget = clamp(round(3.0 * max(40, m_feedbackDelayMs)
                                  + 2.2 * max(15, m_feedbackJitterMs)
                                  + 320.0
                                  + 220.0 * m_linkLossRate),
                            floorMs,
                            m_maxPeriodicSyncTime)`
  - 其中：
    - `m_feedbackDelayMs`、`m_feedbackJitterMs` 在构造时由网络直径与丢包率计算得到；
    - `floorMs` 是最小周期，受 `NDN_SVS_MIN_PERIODIC_SYNC_TIME_MS`、`totalEntries`、策略类型影响；
    - `m_maxPeriodicSyncTime` 默认 `30s`。

- 事件驱动 `alpha`
  - 默认 `alpha = 0.06`。
  - 如果 `NDN_SVS_NETWORK_AWARE_EVENT_ALPHA=1`，则根据信号类型调整：
    - `RepairNeeded`：`0.16`
    - `LocalUpdate`：`0.10`
    - `RemoteUpdate`：`0.07`
    - `Idle`：`0.04`

- 更新周期
  - `next = clamp(round((1 - alpha) * current + alpha * feedbackTarget), floorMs, m_maxPeriodicSyncTime)`。
  - `m_periodicSyncTime` 被设为 `next`。

- 延迟采样
  - `sampleSyncDelay()` 会基于 `m_periodicSyncTime` 加抖动：
    - 基本区间 `[base * (1 - jitter), base * (1 + jitter)]`
    - 若 `TimerMode::NetworkAware`，还会加上额外扩展 `extraSpread`：
      `0.05 * lossRate + 0.08 * feedbackPressure(delay, jitter)`。
  - 最终从 `[low, high]` 中均匀抽样。

## 4. 0.3 比例下的实验命令

下面的命令会在 `grid` 和 `hierarchical` 两个拓扑上比较以下策略：

- `score-paper-updated`（Score / 补偿版）
- `recent-random-quota-fixed`（Quota / Recent + Random Quota）
- `random`（随机）
- `recent-fixed`（最近优先）
- `randrec-paper`（RandRec）

### Grid 拓扑

```bash
cd /home/alice/ndn-sync-eval/mini-ndn-svs-compare
sudo python3 run_partial_strategy_compare.py \
  --topology grid \
  --variants score-paper-updated recent-random-quota-fixed random recent-fixed randrec-paper \
  --ratio 0.3 \
  --max-entries 32 \
  --rows 8 \
  --cols 8 \
  --duration-s 10 \
  --slow-ms 1000 \
  --fast-ms 100 \
  --distribution zipf \
  --seed 7 \
  --output-dir /home/alice/ndn-sync-eval/results/paper-zh-score-quota-0.3-grid
```

### Hierarchical 拓扑

```bash
cd /home/alice/ndn-sync-eval/mini-ndn-svs-compare
sudo python3 run_partial_strategy_compare.py \
  --topology hierarchical \
  --variants score-paper-updated recent-random-quota-fixed random recent-fixed randrec-paper \
  --ratio 0.3 \
  --max-entries 32 \
  --rows 8 \
  --cols 8 \
  --duration-s 10 \
  --slow-ms 1000 \
  --fast-ms 100 \
  --distribution zipf \
  --seed 7 \
  --output-dir /home/alice/ndn-sync-eval/results/paper-zh-score-quota-0.3-hierarchical
```

> 这两条命令使用了 `NDN_SVS_STATE_VECTOR_RATIO=0.3`，并将预算上限固定在 `32` 条状态向量条目。

## 5. 计时器 vs 基线 对比命令

下面这条命令在 `grid` 和 `hierarchical` 两个拓扑上对比：

- `baseline-full-fixed`：完整状态向量 + 固定计时器
- `no-partial`：完整状态向量 + 传播反馈计时器

```bash
cd /home/alice/ndn-sync-eval/mini-ndn-svs-compare
sudo python3 run_feedback_timer_matrix.py \
  --variants baseline-full-fixed no-partial \
  --topologies grid hierarchical \
  --fast-producers 0 4 8 12 16 24 32 38 \
  --rows 8 \
  --cols 8 \
  --duration-s 10 \
  --slow-ms 1000 \
  --fast-ms 100 \
  --distribution zipf \
  --seed 7 \
  --output-dir /home/alice/ndn-sync-eval/results/paper-zh-timer-vs-baseline
```

如果要比较“传播反馈计时器 + 无事件驱动 alpha”版本，可以把 `--variants` 改成：

```bash
sudo python3 run_feedback_timer_matrix.py \
  --variants baseline-full-fixed no-partial-no-event \
  --topologies grid hierarchical \
  ...
```

## 6. 文件说明

本文件已保存为：

- `/home/alice/ndn-sync-eval/mini-ndn-svs-compare/EXPERIMENT_SCORE_QUOTA_TIMER.md`

你可以直接打开这个文件查看完整公式和命令。
<div align="center">

# paper-impact

**AI 会议里哪些论文真正有影响：NeurIPS 与 ICML 历年发表的每一篇论文，连同它的被引数和领域归一化影响力。** 论文清单来自各会议自己的论文集，
数字来自 [OpenAlex](https://openalex.org)（开放数据，CC0）。公开 JSON 加静态网站，每月重建。

<a href="https://github.com/zch6a/paper-impact/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/zch6a/paper-impact/actions/workflows/ci.yml/badge.svg"></a>
<img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-blue">
<img alt="No dependencies" src="https://img.shields.io/badge/dependencies-none-2ea44f">
<a href="LICENSE"><img alt="MIT license" src="https://img.shields.io/badge/license-MIT-blue"></a>

[English](README.md) · **简体中文**

</div>

---

会议论文的被引数很分散：同一篇论文的预印本和论文集版本是两条记录；会议的归属登记得不一致（OpenAlex 里名为
“International Conference on Learning Representations”的 source 总共只有 602 篇）；原始被引数又偏向老论文和大领域。
paper-impact 从各会议论文集列出的论文出发，在 OpenAlex 里逐篇找到它们，把 OpenAlex 的领域归一化指标和原始被引数放在一起，并说明找到了多少。

ICML 2017 的实际构建结果（论文集共 434 篇）：

| | |
|---|---|
| 在 OpenAlex 里找到 | 418 篇（96%），共 39 次请求（页面 1 次、精确标题搜索 22 次、对未命中的宽松重试 16 次） |
| 被引最多 | Model-Agnostic Meta-Learning（9,057）、Wasserstein GAN（6,442）、Neural Message Passing for Quantum Chemistry（5,745） |
| 有 FWCI 和百分位的 | 418 篇中的 135 篇（OpenAlex 只给部分记录计算，预印本记录没有） |

## 网站

选会议和年份（或全部年份），按被引数、领域归一化百分位、FWCI 或近两年被引排序，搜索标题。每个会议年份都链接到它的论文集，并说明找到了多少篇；
没找到的论文照样列出，只是没有数字。数据公开：`data/index.json` 和每个会议年份一个文件。

## 自己构建

```bash
uvx --from git+https://github.com/zch6a/paper-impact paper-impact build venues.json -o site/ --years 2015-2024
```

[venues.json](venues.json) 按论文集页面列出 NeurIPS 2012–2024 和 ICML 2013–2025；每个页面都写明它必须包含的文字（会议名、年份），
卷号写错时会直接报错，而不是悄悄混进另一个会议。

- **匹配**：标题在 OpenAlex 里每次约 20 个一起搜索，只接受规范化后完全相同、年份相差不超过一年的记录；没命中的再宽松地试一次
  （85% 的词相同、长度相近），在数据里标为 `close`。预印本和论文集版本两条记录时，显示被引更多的那条，另一条记在 `also` 里（不相加：OpenAlex 是分开计数的）。
- **费用**：每次搜索花 OpenAlex 额度 0.001 美元，一个 1000 篇的会议年份约 0.05 美元。不设 `OPENALEX_API_KEY` 时每天 0.10 美元额度，
  同一 IP 下所有人共享；免费 key 每天 1 美元。重建时复用 `site/` 里已有的数据：只搜索还没找到的论文，其余按 ID 刷新（每次请求 100 篇，0.0001 美元）。
- **每月构建**（[site.yml](.github/workflows/site.yml)）：构建任务用只读权限运行，数据存在 Actions 缓存里；部署任务只负责发布到 Pages。
  在仓库里加一个 `OPENALEX_API_KEY` secret，首次全量构建可以从几周缩短到几天。

## 这些数字是什么

| | |
|---|---|
| 被引 | OpenAlex 对匹配到的那条记录的计数 |
| FWCI | 领域加权引用影响力：1.0 是同领域、同类型、同年份作品的世界平均 |
| 百分位 | OpenAlex 的 `citation_normalized_percentile`，以及前 1% / 前 10% 标记 |
| 近两年 | 最近两个完整年份的被引数，取自 OpenAlex 的逐年计数 |

## 局限

- 只有 OpenAlex 里有的：ICML 2017 约 4% 的论文按标题找不到；被引分散在多条记录上的论文只显示其中一条的计数。
- 会议论文里只有少数有 FWCI 和百分位（预印本记录常常没有）；按它们排序时只排有数字的，其余放在后面，页面上会写明有多少篇。
- 会议论文集上线之后才收录：NeurIPS 2025 目前只上线了 Creative AI 分区，暂不收录。

## 同一套工具

[paper-proof](https://github.com/zch6a/paper-proof) 检查论文的参考文献与数字；[submit-check](https://github.com/zch6a/submit-check) 按会议规则检查论文；
[arxiv-diff](https://github.com/zch6a/arxiv-diff) 显示版本之间改了什么；[exp-tables](https://github.com/zch6a/exp-tables) 把实验结果变成只在有依据时才加粗的表格；
[scholar-cards](https://github.com/zch6a/scholar-cards) 把学者的数字放到个人主页上。

## 许可证

代码为 MIT。数据来自 OpenAlex（CC0）和各会议论文集的列表（标题与链接）。

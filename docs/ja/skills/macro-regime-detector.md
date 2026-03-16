---
layout: default
title: "Macro Regime Detector"
grand_parent: 日本語
parent: スキルガイド
nav_order: 29
lang_peer: /en/skills/macro-regime-detector/
permalink: /ja/skills/macro-regime-detector/
---

# Macro Regime Detector
{: .no_toc }

クロスアセット比率分析を用いて、構造的なマクロレジーム転換（1〜2年の期間）を検出します。RSP/SPY集中度、イールドカーブ、信用環境、サイズファクター、株式-債券関係、セクターローテーションを分析し、Concentration、Broadening、Contraction、Inflationary、Transitionalの各状態間のレジームシフトを特定します。マクロレジーム、市場レジーム変化、構造的ローテーション、長期的な市場ポジショニングについて聞かれた際に実行します。
{: .fs-6 .fw-300 }

<span class="badge badge-free">API不要</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/macro-regime-detector.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/macro-regime-detector){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

クロスアセット比率分析を用いて構造的なマクロレジーム転換を検出するスキルです。

---

## 2. 使用タイミング

- ユーザーが現在のマクロレジームやレジーム転換について質問した場合
- ユーザーが構造的な市場ローテーション（集中 vs 分散）を理解したい場合
- ユーザーがイールドカーブ、信用環境、クロスアセットシグナルに基づく長期ポジショニングについて質問した場合
- ユーザーがRSP/SPY比率、IWM/SPY、HYG/LQDなどのクロスアセット比率に言及した場合
- ユーザーがレジーム変化が進行中かどうかを評価したい場合

---

## 3. 前提条件

- **FMP APIキー**（必須）: 環境変数 `FMP_API_KEY` を設定するか `--api-key` を渡す
- 無料枠（250コール/日）で十分（スクリプトは約10コールを使用）

---

## 4. クイックスタート

```bash
python3 skills/macro-regime-detector/scripts/macro_regime_detector.py
```

---

## 5. ワークフロー

1. 方法論のコンテキストとしてリファレンスドキュメントを読み込む:
   - `references/regime_detection_methodology.md`
   - `references/indicator_interpretation_guide.md`

2. メイン分析スクリプトを実行:
   ```bash
   python3 skills/macro-regime-detector/scripts/macro_regime_detector.py
   ```
   9つのETF + 国債金利の600日分のデータを取得します（合計10 APIコール）。

3. 生成されたMarkdownレポートを読み、ユーザーに結果を提示。

4. ユーザーが歴史的な類似事例について質問した場合、`references/historical_regimes.md` を使用して追加コンテキストを提供。

---

## 6. リソース

**リファレンス:**

- `skills/macro-regime-detector/references/historical_regimes.md`
- `skills/macro-regime-detector/references/indicator_interpretation_guide.md`
- `skills/macro-regime-detector/references/regime_detection_methodology.md`

**スクリプト:**

- `skills/macro-regime-detector/scripts/fmp_client.py`
- `skills/macro-regime-detector/scripts/macro_regime_detector.py`
- `skills/macro-regime-detector/scripts/report_generator.py`
- `skills/macro-regime-detector/scripts/scorer.py`

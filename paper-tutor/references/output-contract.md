# Paper-Tutor Output Contract

## Contents

1. [Output boundary](#output-boundary)
2. [Full-document schema selection](#full-document-schema-selection)
3. [General full-document contract](#general-full-document-contract)
4. [Explanation recipes](#explanation-recipes)
5. [Evidence appendix](#evidence-appendix)

## Output boundary

Produce a focused answer for a focused request. Produce exactly one `paper-tutor.md` for a full-paper request. When the request is a complete-paper reading session, additionally follow [reading-completion.md](reading-completion.md) to produce the compressed `reading-note.md` and reconstructed `method.svg`; these are projections of the one deep analysis, not another full analysis. Apply paper identity, mode, verification, claim labels, source priority, conflict handling, and the caption-only `overview` safety rule from [integration-and-evidence.md](integration-and-evidence.md); do not duplicate or weaken them here.

Use transparent `Not present in the available source.` or `Not verifiable from the available evidence.` text whenever required material is absent. Never fill a section with plausible but invented material. Keep simple or obvious sections concise and explain complex core concepts in detail.

## Full-document schema selection

Choose one primary schema before drafting:

| Observable paper type | Required schema |
| --- | --- |
| The benchmark, evaluation suite, task collection, or test environment is a primary contribution | Read and apply [benchmark-paper.md](benchmark-paper.md). Its Benchmark Card, task-level Input/Output map, one-sentence formula, and Claim → Evidence Appendix form the full `paper-tutor.md`. |
| The paper primarily contributes a model, method, system, theory, or empirical finding and only uses existing benchmarks for evaluation | Use the General full-document contract below. |

When the paper co-contributes a method and a new benchmark, choose the primary structure by the paper's main argument. If the method and benchmark are equally central, retain the Benchmark Card's 16 fields as an index and add a compact method module covering the method's inputs, training objective, mechanism, and supporting evidence. Keep both contributions traceable without duplicating the full analysis in a second outline.

## General full-document contract

For a non-Benchmark paper, write one `paper-tutor.md` with this reader-first order. Put one compact source/CKPT/depth line near the title and the full mode block plus depth line at the end so status is visible without burying the first-screen mainline:

1. **30 秒导读**：问题、缺口、核心做法、主要发现、结论边界、3–5 个阅读问题和必要前置知识。
2. **问题与 Insight**：把背景、旧方法的具体不足、作者的关键改变连接起来；作者陈述与 Tutor Explanation/Analysis 分开。
3. **方法与必要知识**：给出真实的输入→处理步骤→输出流程，再按需要展开模块、公式和前置概念。每一步至少说明作用、输入、输出、必要性。
4. **关键图表与实验**：只深入支撑主结论或关键边界的图表、实验和消融；说明问题、比较、指标、设置、结果、能证明和不能证明什么。
5. **贡献、局限与研究视角**：作者贡献、明确局限、读者分析、替代设计、可复现性/泛化/成本等按深度选择展开。
6. **重新串联与记忆点**：用 `Background → Gap → Insight → Method → Evidence → Contribution` 复述全文，给 5–10 个高密度要点和 2–3 个可自检问题。
7. **Claim → Evidence Appendix**：使用本文末尾的精确表头。

这是覆盖契约，不要求每篇论文机械打印相同标题或重复同一段摘要。简单内容保持短，真正阻碍理解的内容增加白话、最小例子和本文中的具体位置。若有有效的 Scholar-Slides reading view，复用其主线、机制步骤、决定性证据和论证链；不要建立第二套互相竞争的论文分析。

不要把作者未报告的内容写成缺失事实；使用 `Not reported by the authors.` 或 `Not verifiable from available evidence.` 区分已确认没有与当前证据不足。

## Explanation recipes

Use these ordered recipes as internal coverage checks whenever their content type
is requested. Render the supported reasoning in natural Chinese prose or a compact
table; do not mechanically print every English slot. When evidence cannot support
one item, state `Not verifiable from available evidence` in that item rather than
filling it with a plausible inference. A separately labeled Tutor Explanation or
Tutor Analysis may clarify a Paper Fact but never replace it.

| Content type | Required explanation sequence |
| --- | --- |
| Formula | original → symbols → mathematical meaning → intuition → necessity → role |
| Figure/Table | question → reading order → encodings/parts → intended observation → paper connection → limits |
| Experiment | research question → dataset → baseline rationale → metric → setup → expected evidence → result → can/cannot prove |
| Ablation | removed component → change → supported design choice → alternative explanation |
| Module | purpose → necessity → input → output → implementation → design rationale → relationship to neighbors |

When matching evidence contains an original formula, label the equation as a Paper
Fact and explain symbols, mathematical meaning, intuition, necessity, and role in
that order when those details matter. Keep unsupported definitions and roles at
the required unavailable value. The same principle applies to modules, figures,
experiments, and ablations: cover the reasoning without bloating the document with
empty template fields.

Do not copy a figure or table caption in place of explanation. The caption-only `overview` safety rule remains governed by [integration-and-evidence.md](integration-and-evidence.md).

## Evidence appendix

Use exactly this header and separator row:

| Claim | Source | Page | Section | Figure/Table | Evidence ID |
| --- | --- | --- | --- | --- | --- |

Keep body citations lightweight while making supporting appendix rows traceable. Retain available page, section, and figure/table locations; state when a location is unavailable. Preserve upstream Evidence IDs without renaming, regenerating, or merging them.

In Standalone Mode, label every appendix evidence entry `Standalone evidence` and `Not CKPT-1 verified` in the appropriate Source and/or verification text, while preserving required mode disclosure from [integration-and-evidence.md](integration-and-evidence.md).

## Formula presentation projection

When a validated downstream Paper Learning Map provides a derived
`formula-index.json`, Paper-Tutor may emit both the portable `paper-tutor-deep-v2.md`
and a same-source `paper-tutor-deep-v2.html`. Markdown remains the canonical textual
artifact and keeps raw LaTeX. HTML and the Learning Map drawer are presentation
projections of structured source data; they must never be generated by parsing
`paper-tutor.md` or by writing formula explanations into the factual graph.

Keep the provenance boundary explicit: `paper_formula` is a Scholar-Slides-backed
Paper Fact with evidence refs, while `tutor_derivation` and `tutor_example` are
Tutor-layer explanations. KaTeX must be project-local and offline; use
`htmlAndMathml`, conservative `trust=false`/`throwOnError` settings, preserve a raw
TeX fallback on parse failure, and do not add a CDN fallback.

# Benchmark Paper Contract

Use this contract when a benchmark, evaluation suite, task collection, or test environment is a primary contribution of the paper. A paper that only reports results on an existing benchmark uses the general full-document contract instead.

## Output order

For a full Benchmark-paper tutorial, write one `paper-tutor.md` in this order:

1. a short reader-first introduction: 30-second mainline, paper type, three key questions, and the argument chain;
2. `# Benchmark 梳理卡` with the 16-row table below;
3. `## Task → Input / Output Map`;
4. `## Benchmark 一句公式`;
5. grouped deep explanations: why this benchmark measures what it measures, how a task is completed and scored, what the experiments reveal, and how far the conclusion can go;
6. `## Claim → Evidence Appendix` using the exact schema in [output-contract.md](output-contract.md).

The Benchmark Card is the primary index, not the entire teaching document. Keep every field
once, in the fixed order, and put lightweight citations in the answers. Move long explanations,
worked metric examples, and cross-task reasoning into the grouped prose so the table remains
scannable. Preserve upstream Evidence IDs.

## Required Benchmark Card

Use these field names and questions exactly:

| 问题你必须回答 | 回答 |
| --- | --- |
| **Motivation** | 现有 benchmark 有什么问题？ |
| **Capability** | 它到底想测模型什么能力？ |
| **Task** | 设计了哪些任务？ |
| **Input / Output** | 每个任务输入输出是什么？ |
| **Dataset** | 数据哪里来的？规模多大？真实还是 synthetic？ |
| **Environment** | 模型运行在什么环境？有哪些工具？ |
| **Models** | 测了哪些模型？ |
| **Agent** | 是否用了 Agent？比较了什么 Agent？ |
| **Baseline** | baseline 是谁？ |
| **Metric** | 怎么判定任务成功？ |
| **Result** | 谁最好？最大的规律是什么？ |
| **Scaling** | 数据/任务复杂度增加后性能如何变化？ |
| **Failure** | 模型主要失败在哪里？ |
| **Validity** | Benchmark 是否公平、真实、存在污染？ |
| **Conclusion** | Benchmark 最终证明了什么？ |
| **Research Gap** | 暴露了哪些值得继续研究的问题？ |

Replace the second column with evidence-backed answers; do not leave the questions as answers. Each row must satisfy the following semantic contract:

| Field | Required answer content |
| --- | --- |
| Motivation | Name the concrete failure of prior benchmarks: missing capability coverage, unrealistic setting, weak task difficulty, saturated scores, poor reproducibility, contamination risk, or another author-supported limitation. |
| Capability | State the evaluation construct: the precise ability the benchmark operationalizes. Separate the authors' intended capability from Tutor Analysis about what the tasks actually measure. |
| Task | Enumerate every material task family and map each family to the intended capability. Do not substitute dataset names for tasks. |
| Input / Output | Summarize each task's observation/input and expected response, action, artifact, trajectory, or final state. The task-level map below is mandatory when more than one task exists. |
| Dataset | Give provenance, collection or generation procedure, scale, splits, annotation/quality control, and real/synthetic/mixed composition when reported. |
| Environment | Describe the runtime or interaction world, observation/action space, tools/APIs, sandbox, resource or step limits, retrieval/access constraints, and feedback when they affect evaluation. |
| Models | List evaluated model families and exact versions/checkpoints when reported; preserve closed/open and modality distinctions that affect comparison. |
| Agent | State whether evaluation is direct model inference or agentic. If agentic, compare scaffolds, planning/tool/memory loops, prompts, budgets, and controlled differences supported by evidence. |
| Baseline | Identify the primary no-new-mechanism comparator and other decision-relevant baselines, including human, oracle, random, retrieval, or non-agent baselines when reported. |
| Metric | Define success, partial credit, aggregation, judge or human evaluation, pass@k/trials, variance, and cost/latency metrics when reported. A metric name alone is insufficient. |
| Result | Name the best system only within its exact task, metric, and setting; then state the largest cross-model or cross-task pattern and important regressions, ties, or instability. |
| Scaling | Report the measured relationship between performance and data size, task difficulty, horizon, tool count, context length, or another complexity axis. Distinguish tested scaling from extrapolation. |
| Failure | Give the evidence-backed error taxonomy and where failures concentrate. Separate author-reported failures, directly observed results, and Tutor Analysis. |
| Validity | Assess internal fairness, external realism, and contamination/leakage separately, including prompt/tool/budget parity, annotation or judge reliability, representativeness, and train/test overlap evidence. |
| Conclusion | State the narrowest claim supported by the benchmark results under the tested conditions; do not turn benchmark performance into a general claim about intelligence or real-world competence. |
| Research Gap | Convert uncovered capability gaps, validity threats, scaling breakdowns, missing environments, or failure clusters into concrete research questions. Label these as Tutor Analysis unless the authors explicitly state them. |

If the full paper establishes that an item was not evaluated or not used, write a direct answer such as `Not evaluated by the authors.` or `No Agent; direct model inference only.` If the available evidence is merely insufficient, write `Not verifiable from available evidence`. Absence established from the full paper and missing evidence are different states.

## Task → Input / Output Map

Render one row per material task or task family. This table is required even when the Benchmark Card already summarizes the tasks.

| Task | Capability | Input / Observation | Output / Action | Success criterion |
| --- | --- | --- | --- | --- |
| ... | ... | ... | ... | ... |

Use the paper's task granularity. If instances within one task have materially different interfaces, split them into separate rows. For interactive tasks, include observations, allowed actions/tools, termination condition, and final deliverable. For static tasks, identify the supplied context and expected output form.

## Grouped deep explanations

Use these four sections after the compact card and task map:

1. **为什么这样测**：connect Motivation, Capability, and Task; explain what changed from prior benchmarks.
2. **一道任务怎样完成并评分**：connect Dataset, Input/Output, Environment, Agent, Baseline, and Metric; give one clearly labeled teaching example when it helps.
3. **实验真正发现了什么**：connect Models, Result, Scaling, and Failure; interpret decisive numbers with their exact setting.
4. **结论能走多远**：connect Validity, Conclusion, and Research Gap; separate fairness, realism, contamination, judge reliability, author claims, and Tutor Analysis.

Do not repeat the entire 16-row card in these sections. A table cell can point to a deep
section; a deep section can point back to a card field. Keep hypothetical calculations
explicitly labeled as teaching examples and never mix them with reported results.

## Benchmark 一句公式

Complete every blank in this exact sentence pattern with high-density phrases grounded in the card:

> **作者认为现有 Benchmark 无法评估 ______，因此构建了包含 ______ 数据和 ______ 任务的新 Benchmark，使用 ______ 指标评估 ______ 模型/Agent，最终发现当前模型主要在 ______ 上存在明显不足。**

Use `Not verifiable from available evidence` only for a blank that genuinely cannot be resolved. The sentence compresses the Benchmark Card; it must not introduce a new claim, stronger conclusion, or unsupported causal explanation.

## Evidence and reasoning rules

- Apply the Paper Fact, Tutor Explanation, Tutor Analysis, Unsupported, source-priority, and conflict rules from [integration-and-evidence.md](integration-and-evidence.md).
- Cite dataset sizes, task counts, model versions, agent settings, metrics, best results, scaling trends, failures, and validity claims when evidence locations exist.
- A global “best model” is valid only if the benchmark defines and reports a global aggregation. Otherwise name per-task or per-metric winners.
- `Scaling` requires an observed complexity axis and results at multiple levels. A larger model outperforming a smaller model is model scaling, not task/data-complexity scaling, unless the paper frames and measures it that way.
- `Validity` must distinguish paper-reported checks from Tutor Analysis. Lack of disclosed contamination analysis is not proof of contamination.
- `Conclusion` answers what this evaluation establishes; `Research Gap` answers what should be investigated next. Do not merge them.

# 09 Codex workflow 交接包

## 目标与边界

- 目标：按 [case_matrix.csv](case_matrix.csv) 生产 8 个正式主案，并以参考门和网格门约束发布。
- 允许：本需求目录、`local_runtime/tcad_projects/igbt_mosfet_seb_paper_20260714/`、VM 同名命名空间、指定脚本的最小兼容扩展。
- 禁止：70 µm 旧 deck、Rc=1e11 BV、2500 V A01 充当正式结果、裸跑并发 SDevice、覆盖 attempt、修改历史 LET 四点语义、Git commit/push。

## 探索阶段

本轮主代理侦察范围必须覆盖：技能与 AGENTS、git 脏改动、451.15 µm SDE、attempt04 HeavyIon、热稳态 Save/Load 先例、runner/core policy/merge schema、SSH/Sentaurus/license。收到这些证据后才可冻结实现计划。本任务指定唯一实现 worker，因此不再派遣可写 worker；若执行器允许只读探索，可按“输入谱系、runner 兼容、SVisual字段”三个互斥角度并行，并须全部返回后修订计划。

## 执行顺序

1. 建文档、矩阵和项目骨架；
2. 最小扩展 runner/merge，新增 prepare/extract/render/summarize；
3. 生成并审计两种 mesh；
4. 串行建立 8 个热稳态 restart；
5. 运行共享 IGBT 参考瞬态并执行精确 2.1 ns/字段/电荷门；
6. 参考门 PASS 后才运行其余主案；否则 fail closed；
7. 运行两个局部加密验证案并执行预注册网格门；
8. 提取、统一色标渲染、汇总、小型发布、验证与交接。

## Harness / 预算 / checkpoint

- SDevice harness：仅 `scripts/run_igbt_seb_case.ps1 -Threads 1`；自动租约；最多 4 个独立叶子；
- SDE、SVisual 后处理可直接 SSH 串行执行；
- 每条依赖链完成后保存 manifest/hash；参考门为昂贵瞬态预算 checkpoint；
- 失败使用新 attempt；网格/参数变化使用新 variant；
- 长任务管理到 exit code、稳定运行或有证据失败，不以“已启动”闭环。

## 完成条件

以 [08-测试用例](08-测试用例.md) 为准。若参考门失败，保留完整证据、将余下主案标 `NOT_RUN_REFERENCE_GATE` 并发布 fail-closed 报告即视为按计划完成，而不是实施遗漏。
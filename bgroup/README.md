# 组 B · 第一轮（单种子冒烟）

这一轮只跑 **一次**（seed=1），目的是把「队列 → 版图产物 → runs.csv → 网格密度」这条链走通，
不是拿结论。论文里的 η 数组来自第二阶段 153 组。

## 本轮矩阵

| 项 | 值 |
|---|---|
| 设计 | EPFL `adder128`（module `top`，128 位行波进位加法器） |
| PDK | sky130hd（ORFS 自带） |
| 库 | `basic` / `full` / `full-lite`（白名单裁 `.lib`+`.lef`，原地替换） |
| 种子 | 1（单次，不重复） |
| 固定量 | `CORE_UTILIZATION=0.50`、`PLACE_DENSITY=0.65`、虚拟时钟 100 ns |
| 网格 | 2.5 / 5 / 10 μm 三档（5 μm 进主表） |

## 每跑一次产出

```
out/
  results/sky130hd/adder128/base/6_final.def     版图（算面积、算密度）
  reports/.../synth_stat.txt                     逻辑面积（.lib 标称面积之和）
  logs/.../6_report.json                         核心区面积、利用率、WNS/TNS、DRV
  logs/.../5_2_route.json                        线长、DRC 违例
  trimmed/trim_report.json                       裁库清单 + 单元数对账
  density.json                                   2.5/5/10 μm 网格引脚密度
  odb_truth.json                                 OpenROAD 自己的 per-pin bbox（对账用）
  orient_check.json                              八朝向坐标变换误差
  runs.csv                                       一行一 run（15 字段）
```

## 三查

1. 单元数：`.lib` cell 数 == `.lef` MACRO 数（`trim_report.json.check_count_ok`）
2. 可读：`yosys read_liberty` 通过；LEF 由 flow 的 `read_lef` 隐式验证
3. 对得上：DEF `COMPONENTS` 去掉 fill/tap 后 == 网表单元数；ROWS 重算核心区面积 == report（±0.5%）

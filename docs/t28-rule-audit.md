# T28 IO 环规则与验收审计

设计建议核对依据为 TSMC N28 General I/O Library Application Note v1.4、第 18 章检查清单和本站安装的 OA 库。下表的章节号指应用笔记。工艺和封装发布版变化时，应重新核对适用条件。

## 规则在哪一步检查

| 项目 | 已执行的检查 | 仍需的证据 |
|---|---|---|
| 数字与模拟供电（8.6、9.5–9.7、10.6） | enrichment 按域和已规划绑线位置计数。普通模拟总线供电使用 3A/3AC 系列。专用 1A/1AC 必须指明宏和封装脚，正电源按封装脚检查数量，并检查宏的专用地配对。 | 版图与最终封装键合图一致。旧输入缺少域电压时，报告列出待填字段。 |
| 角、隔离和 POC（3.4、6.2–6.3、9.8） | 以插完 filler 后的实际物理顺序检查角两侧绑线地、隔离单元数量和类型、两侧 filler 类型及邻近电源或地。生成原理图端口与版图 POC 标签。 | 纯电源数字域的 POC 接地需有真实金属连接。 |
| VSS 全局总线与域内电阻（8.4、10.4、23y.3） | 记录每个 PDB3AC 到合格绑线地的最短环路距离，并记录各域不同器件组合中路径最长的一对。提供经校准的单位长度电阻时，报告超限估算。 | 用提取结果核对表 8.1/10.1 的适用组合、例外与电阻上限。23y.3 要求低于 1 Ω。 |
| SSO（7.1.5、7.3、清单 19–20） | 按域对双向 IO 的驱动因子求和，向上取整后检查两种绑线供电数量。缺少负载、封装电感或驱动数据时列为待核实。 | 库版本、驱动配置、封装与负载对应的 databook 数据。 |
| 芯片级 ESD、上电与焊盘（3、8–11、16、清单 38） | skill 列出了 clamp 连接与栅向、20 pF 去耦、二次保护、信号摆幅、上电顺序和模拟 CUP master 的检查项。 | 顶层实物与波形证据。本次 OA 查询只见到 PAD60GU/NU；模拟单元的配对资格需由该焊盘库 release note 确认。 |
| Calibre 验收 | 每次运行保存顶层单元、deck 包装文件哈希、所引用的规则路径、排除项和实际结果。默认 LVS 只虚连列出的电源/地，分别记录比较结果与 ERC 数量；可提供自定义 deck。 | cell DRC 有独立的排除清单。整片须使用目标芯片顶层、对应签核 deck，并复核工艺 deck 内部设置。 |

## DRC 与 ERC 的历史设置和规则依据

默认 [cell DRC wrapper](../skills/t28-ioring-generator/calibre/T28/_drc_rule_T28_cell_#L2657) 恢复为仓库基线 `a6b8437`，`DRC UNSELECT CHECK` 共列出 81 项。`result.json` 的 `wrapper_unselected_checks` 保存这份显式排除清单。实际运行项目还取决于 `DRC SELECT CHECK` 和底层 deck 的开关。`--chip-deck` 替换引用的规则文件，去掉这段显式排除，并沿用 wrapper 的选择清单。项目可以用 `--deck` 提供自己的完整 wrapper。

| 原仓库排除项 | 数量 | 适用范围或依据 |
|---|---:|---|
| `OD.S.14`、`OD.DN.3/.4/.5`、`PO.A.3` 至 `.6`、`PO.DN.3/.3.1/.4/.4.1/.11/.13`、`M1` 至 `M9` 及跨层 `Mx.DN` | 57 | OD 最大间距、PO 面积及多层密度，沿用 cell 级排除。DRM 2.3 §6.8 讨论 IP 和整片的填充及密度检查。 |
| `PO.DN.16`、`PO.R.28` | 2 | DRM 2.3 pp. 52、191–193 按 `MATCHING`、`ANARRAY_H`、`ANARRAY_M` 标记定义检查区域。含匹配标记的电路按整片 deck 检查。 |
| `IND.R.5`、`IND.DN.2:M1` 至 `:M7`、`IND.DN.7`、`AP.W.5`、`AP.S.6/.7`、`HVD_N.S.15`、`HVD_P.S.15` | 14 | 沿用 cell 级排除。DRM 2.3 pp. 231、234、357–358、429–430 分别给出 HV 多指栅间距、电感、AP 的几何条件。 |
| `SRAM.WARN.1/.2` | 2 | DRM 2.3 p. 371 按整片 SRAM 总面积提示冗余及 ECC。 |
| `IO_CONNECT_CORE_NET_VOLTAGE_IS_CORE:WARNING1`、`DIODMY_L:WARNING` | 2 | 已安装 DRC deck 把前者定义为提示。后者仅在设计无低漏电关注二极管时可忽略。 |
| `ESD.18g/.19g` | 2 | `tphn28hpcpgv18` release note 170A、170C §5a 明确列为 IO 库可豁免项。 |
| `ESD.40g/.40.1g` | 2 | DRM 2.3 §9.2.9.4 的 power clamp 指南，沿用 cell 级排除。170A／170C §5a 的 IO 库豁免清单未列这两项。 |

170C §5a 还明确列出 `ESD.37g`。原 wrapper 把它放在 `DRC SELECT CHECK` 中，实际适用由底层 deck 决定。DRM 2.3 §9.2.9.5 另有针对双二极管 ESD 方案的有条件豁免，条件涉及满足相应指南和已有硅验证依据。

原 [LVS wrapper](../skills/t28-ioring-generator/calibre/T28/_calibre_T28.lvs_#L30) 用 `LVS EXECUTE ERC YES`，仓库这一层没有 `ERC UNSELECT CHECK`。安装的 LVS deck 按开关选择 well、gate、source/drain 和 floating-well 等检查。本流程记录 Calibre 原始 ERC 数以及各规则计数。170A 和 170C release note §5b 的豁免作用于指定库 master 中的标记。

| ERC 规则 | Release note 所列 master |
|---|---|
| `mnpg` | `PCLAMP_G`，以及 `PCLAMPC`、`PVDD1AC`、`PVDD1ANA`、`PVDD1A`、`PVDD1DGZ`、`PVDD2ANA`、`PVDD2DGZ`、`PVDD2POC`、`PVDD3AC`、`PVDD3A` 的 `_H_G`／`_V_G` 版本。 |
| `floating.nxwell_float`、`npvss49` | `PVSS1AC`、`PVSS1ANA`、`PVSS1A`、`PVSS1DGZ`、`PVSS2AC`、`PVSS2ANA`、`PVSS2A`、`PVSS3AC`、`PVSS3A` 的 `_H_G`／`_V_G` 版本。 |

选用豁免时记录规则名、结果标记所属的库实例、库版本和 deck 版本。170C §5 引用 DRC C1 v1.7b 和 LVS C1 v1.0_3o，本站 deck 版本不同，跨版本适用性按项目采用的签核依据核对。`floating.psub` 未列入这两份 release note 的 ERC 豁免清单。

恢复 wrapper 后，3×3 混合单环、6×6 数字单环和 8×8 混合双环的 cell DRC 复跑各执行 2645 项检查，结果均为 0。上次样例的原始 ERC 结果库显示，8×8 的 40 条 `mnpg` 全部属于 `PVDD3AC_H_G`，对应 §5b 的规则和 master。6×6 的 2 条 `floating.psub` 都在环顶层。原始 ERC 数量分别保留为 40 和 2。

## 9×9 SAR ADC 回放

分别对旧的已保存 cell 和从早期 9×9 输入生成的 QA cell 运行 Calibre。早期输入与项目归档的八个数字输出 master 不同。下表是单元级观测；两者的 ERC 数量差不能单独归因于某一项版图修改。

| 观测 | 旧环 | 重新生成 |
|---|---:|---:|
| 两处域边界的 PRCUTA_G 总数 | 4 | 2 |
| cell DRC 结果数 | 0 | 0 |
| LVS 比较 | INCORRECT | INCORRECT |
| floating.psub | 4 | 0 |
| floating.nxwell_float | 6 | 4 |
| mnpg / npvss49 | 280 / 12 | 280 / 12 |
| ERC 总数 | 302 | 296 |

该次回放使用当时排除 79 项的 cell DRC wrapper。只提取环子单元时，VREFN 和 VREFP 各自的两段连接会被分开。项目在芯片顶层从四个焊盘分别走 M8，在 ADC core 内通过 VIA8 和 M9 分别汇合。这个 cell 结果不能作为整片参考网开路的依据。历史 issue 中的 ERC 334 使用另一套规则设置。

### 带实际布线的 r8 对照

将项目归档运行 `20261122_131553` 的焊盘名称、位置和 master 与 `Layout/design/io_ring.json` 的 36 个位置逐项对齐。D0–D7 均为 PRUW08SDGZ，SAMPLE 为 PDDW16SDGZ。用当前生成器重建环并从独立 OA 库 stream out，在 r8 整片 GDS 的副本中替换环，保留顶层和 core 的原有布线。使用 r8 的整片源网表、HCELL 和只虚连电源的 LVS deck。该试验用来检查新环对已有布线的兼容性。

| 观察 | 已布线 r8 原版 | 新环装入同一布线 |
|---|---|---|
| 整片 LVS | CORRECT | INCORRECT |
| 芯片端口 | 31/31 | 31/31，包括 VREFP、VREFN |
| 比较后的网络数（版图/原理图） | 1536/1536 | 1540/1536 |
| AVSS_CORE 顶层标签悬空 | 无 | (140, 650.1)、(620, 650.1) µm |
| ERC | 296 | 296 |

整片比较没有 VREF 差异。当时的 bab79c8 版本将靠角的地焊盘向角移动 20 µm；原顶层保留了旧标签和接入位置。差异报告列出四条版图多出的网、四处地焊盘附近的 rm1w/rm2w 以及并联合并后的宽度差异。迁移这个版本时，需要将已批准的焊盘坐标与生成结果对齐，并核对实际金属接入后重新提取。原项目的 OA 视图没有被修改。

当前自动摆放沿用原仓库的 20 µm 角间距和内排焊盘落点，数字 IO 版图使用原仓库的连线函数。供电、角邻接或隔离建议记录在报告中。用户可在 confirmed config 中直接指定摆放。上表为当时版本的诊断对照。

## Agent 如何交接结果

1. 在确定焊盘顺序、域、器件和键合意图后运行 `prepare_ring.py`。读取打印的 `run.json`，可定位输入副本、文件哈希、失败阶段及待验证项目。供电数量不足会列为建议，3×3 输入仍继续生成。
2. 对指定库、单元和视图执行生成脚本。DRC、LVS 和 ERC 使用本次运行保存的原始报告。报告要同时说明验收范围、退出状态和未通过的规则。
3. 仿真沿用符号导出产生的 run directory。testbench 检查引脚分类后再修改视图。Spectre 初始化脚本写入本次独立的远端目录，上传失败在该步返回。直接 Spectre 仿真和 Maestro 设置同步分别记录。
4. 只有对应证据齐备，才能交付芯片级结论。这个回放覆盖真实的 OA 生成、cell DRC/LVS/ERC 及 Spectre 环境脚本上传回读。整片 DRC、PEX 和完整功能仿真仍需针对具体设计执行。

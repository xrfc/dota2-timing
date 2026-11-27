# 7.42原始树事件、索引与视距来源补证

本轮按[用户授权](decisions/2026-11-27-tree-probe.md)，复用已有精确7.42/build6993录像，首先检查含齐天大圣的9103395615。旧捕获已取得分观察者树状态位；本轮补的是原始事件、索引字段和世界实体schema，并继续核对视距及昼夜来源的编码证据。

## 分层与来源边界

- `sources.map_tree_probe`只接已准备好的录像路径和明确的match/build，保留原始消息、字段元数据、树位变化及完成包序号；不读数据配置、不依赖data或workflow。
- `data.map_tree_probe_io`验证登记来源、真实比赛身份、非留出约束、版本、依赖与精确输入清单。共享层不导入B线捕获器。
- `scripts/capture_tree_probe.py`协调旧锚点、私有解析器副本、解压摘要前后校验及原子无覆盖发布。旧生产者和旧产物原字节保留。

新回执固定原始录像、旧锚点、全部解析器源码/资源与新生产者，读取时逐项核对。工程捕获含全知原始数据，`action_review_allowed=false`、`training_allowed=false`，不直接进入当时可知特征。

只接受登记的八场旧visibility回执，真实manifest身份与留出检查在捕获正文之前执行；新回执的输入清单必须与依赖闭包完全相等。大捕获经公共`source_io`限量读取，专用上限256MiB，写出端也按同一上限拒绝发布；公共64MiB默认值保持。

## 运行

显式spec使用`map-tree-probe-spec/1`，仅含`schema`、`exact_patch`与`anchor`；anchor为已登记的旧visibility捕获及回执的绝对路径/SHA256。命令必须在新进程运行，输出目录必须不存在：

```bash
PYTHONPATH=src .venv/bin/python scripts/capture_tree_probe.py \
  --spec reports/patch742-tree-probe-20261127/probe-9103395615-spec.json \
  --output reports/patch742-tree-probe-20261127/probe-new/9103395615
```

“完成包序号”指当前固定Gem解析器的packet-end回调次序，并非原始文件命令号或包内消息顺序。Gem内部可能重排消息；事件交付包与事件本身时间分别保留，不能当作严格的原始网络到达顺序。

首次赛末包记录ordinal，后续同tick包也排除。未完成包中的事件单列且禁止消费。`entity_changes`按`(entity_index, entity_serial)`首次保留完整`fields_raw`，之后只写变化键，显式null仍是未知；`previous_packet_ordinal`链接前一条。坐标和其他行字段是该条快照，不沿用上一条。树原字同样以初始完整值和后续变化记录保存。非空存储容器另按索引差分：`storage_rows_encoding=full`保留初始行，`delta`以`changed_rows`替换整行、以`removed_storage_indices`移除存储槽，并通过`base_field_packet_ordinal`连接该字段上次实际输出。空差分不等于空容器，元数据仍完整；整数长度/null/unknown整字段替换会重置容器基值。

齐天大圣栖树索引赋值瞬间的位置不能直接认证为树坐标，因此另保留本体原始栖树索引非哨兵值期间每个distinct replay tick的位置。这是原始索引关联轨迹，不等于已判定落树或整场移动轨迹。

非空向量不能仅按`entity.get(path)`读取整数长度：固定Gem的`FieldState`会用子节点替换父级长度，后续长度更新也不覆盖已有子树。内部list初始容量8并倍增，缩短到0仍可能留下旧槽，容量不等于协议长度。探针对这类容器保留`observed_storage_rows`及原存储索引，明确`logical_length_known=false`、`stored_slots_may_be_stale=true`；不能把这些槽直接算作当前有效viewer。精确当前成员需要另行保留低层长度写入和生命周期证据。

## 原始事件和视距核查

独立扫描直接读取原始包消息，不调用新捕获器或重建实体。八场共493510条S2战斗日志：赛末tick前489012、同tick236、之后4262；均为direct消息，bulk为0。`TREE_CUT`（type35）在全部消息中均为0；不能据此推断没有砍树行为，也未覆盖S1旧事件通道。解析入口保留direct原字节、bulk嵌套消息含未知字段的重序列化字节、字段presence和名称表状态，正路径由合成协议测试覆盖。

八场原始SendTables的2050个字段和3345个serializer声明一致。按vision/sight/fow/day/night及radius/range等字段名检索，没有找到明确的current/effective视距字段；这个结论不排除未识别名称或其他协议通道。已新增`m_fRevealRadius`、临时viewer、FOW blocker及嵌套`HeroID_t`原值捕获；基础昼夜范围或reveal半径不能直接当当前有效视距。

此前`HeroID_t`只看到二倍数值关系，本轮取得固定版本的独立实现和正负值测试依据：[Gem类型表](https://github.com/whanyu1212/gem-dota/blob/8aec34336f204b36367d9627ee02cf34f4de53d6/src/gem/schema/field_decoder/type_resolver.py#L123)、[Manta解码与测试](https://github.com/dotabuff/manta/blob/d4e46471014a651801c045c001816168a93e4e5e/field_decoder_test.go#L46)明确使用signed zigzag，当前compat走unsigned默认路径。build6993原始头部没有signed-enum扩展标志，因此这是有源依据的解码解释，不能写成录像头自身已声明签名。旧parser和旧字段值未改。

未来正式修正需独立登记生产者迁移，并核验旧`draft.py`中的`hero_id // 2`补偿，避免二次折半。来源ID解码不自动证明旗标生效、施法实体或有效视距；旧八场3404帧“来源非零但临时旗标全false”的现象仍需保留。

## 验收口径

树事件值、齐天大圣树字段、观察者树位与坐标对应分别检查；即使数值一致，也不把数组顺序或某一位平面的名称当成引擎规范。昼夜来源的编码修正与有效视距也分别检查：一个来源ID被正确解码，并不证明旗标当前生效、当前修饰器范围或完整坐标FOW。

正式知识仍7.41f，7.42完整行动复盘与训练入口继续关闭。

## 最终实测与复现结果

当前验收输出为`reports/patch742-tree-probe-20261127/probe-final-r3/9103395615/`，此前尝试仅保留为覆盖缺口或超限的审计记录，不作为当前生产者的已验产物。

- 240项生产输入固定，44150个完成包、84534条实体字段变化、3727条树原字变化、451个已遇到class schema；无未完成包记录。实际读取到150个不同的非哨兵栖树索引。
- 87段存活本体稳定XY（至少3个不同tick、至少0.5游戏秒）支持86个索引的局部空间关联：先按原英雄XY选唯一最近树，再检验英雄XY按`64*round(v/64)`取整后等于原地图点，且原始索引等于该点在原地图数组的0-based行号。87段全部相符，1-based假设为0；原始浮点XY精确相等为0，偏差约0.97–33.15，最近与次近树距离差至少71.92。阈值和取整是工程检验选择，不是已证原生规则；其余2308棵树未测，不推广为全图索引或位平面语义。
- 10名英雄的原始`HeroID_t`按上游signed zigzag解释后，与旧捕获真实实体名称及固定英雄名册的ID多重集合一致；未使用旧draft的折半名称补偿。只验证这场的观察存储集合，不证明当前成员、玩家槽位对应或所有补丁。
- 10个临时viewer实体的原始网格、半径、类型、valid和obstructed字段已保留；83个实体涉及非空存储证据，不能视为83个当前视野源。44类实体的`m_fRevealRadius`观察值均为0，仍未补成有效视距。4条其他未知容器来自`CDOTA_NPC_BaseBlocker.m_vecAbilities`的缺失长度，保留null，不当空数组；本次未观察到model4槽为非FieldState标量的分支。
- 字段和容器差分可无损重建。20条容器full、24482条delta实际传输29128次存储行替换；同内容按字段冗余展开的字节计量参照为1076153388字节，新文件94253072字节（约89.89MiB），减少91.24%。参照是同信息的展开计量表示，不是第二份可直接消费的协议工件，也未拿字段集不同的旧版本计算压缩率。
- 本次解析约397.7秒，整个命令约7分15秒，峰值505156KiB（约493MiB）。这是完整诊断捕获的实测成本，尚未做大规模解析吞吐验收。

独立重建核对旧捕获32340次树状态观察和26460个昼夜字段，全部一致；2940帧唯一匹配，tick0空帧仍有10个可能包，不强定包边界。组合核验337个输入无漂移；视距审计另核309文件、167个JSON指针、23处源码行与7份上游Git blob。

100项新增专项和35项相关回归通过。最终串行全量命令为`scripts/check.py --scope all`，前后包含未忽略未跟踪源码的指纹及结果以`reports/patch742-tree-probe-20261127/full-check.json`为准。

可分发的[验收摘要](acceptance/tree-probe-20261127.json)固定回执、统计和边界；本地[原始捕获回执](../reports/patch742-tree-probe-20261127/probe-final-r3/9103395615/receipt.json)、[组合独立核验](../reports/patch742-tree-probe-20261127/independent-final-r3-check.json)、[局部树映射](../reports/patch742-tree-probe-20261127/tree-probe-independent-r3.json)和[视距来源审计](../reports/patch742-tree-probe-20261127/vision-source-final-r3-audit.json)不随Git分发。

## 自检发现与后续出口

首轮完整捕获发现文件超过通用读取默认上限，已增加专用有界读取及发布端上限，并采用字段差分减少重复内容。随后独立视距复核发现非空`FieldState`被误作无效长度；保留该版为反例。补全原子值后整容器重复使输出超过256MiB，发布端正确拒绝；后续改为逐存储索引无损差分并流式有界写出，新输出单独发布。来源摘要和旧树/规则快照对账可以通过，仍不代表新增字段已充分采集，因此原字段覆盖审查与来源验收分开执行。

全库验收还发现CLI测试夹具依赖“此前未导入Gem”的执行顺序；已让夹具隔离并恢复原模块缓存，增加预加载回归。生产入口仍要求新进程，捕获生产者和已验原始产物无需因此重建；首轮失败日志保留，修复后重新串行全量验收。

下一步是取得完整原生树ID空间表、验证临时viewer的单位/类型/观察队伍与生命周期，并补低层向量长度更新观测；HeroID_t修正走新生产者与明确迁移，不能覆盖旧回执。已有栖树局部关联不外推剩余树，也不为两个位平面赋予“存活/砍倒”语义；有效英雄视距、具体视野来源归因和完整FOW继续保持未知。

# 7.42机制待决清单（2026-11-27）

这是可逐项回复的审阅稿，**不新增用户决定；“继续开发”不等于批准以下建议**。依据[U179及后续决定](decisions/2026-11-19-patch-7.42.md)，工程核验、双AI一致与旧版用户批准均不能代替本次语义裁定。可只答有把握的编号，其余保留未知。

当前3292行候选事实＝2489行候选可用＋700行明确排除＋103行未准入；103＝**25行既有待决＋69行证据不足＋9行字段例外**。25行不等于25个问题；103也不包括全部全局规则和未写入事实表的新提案。详见[候选资产说明](patch-review-assets.md)。本页不切换正式7.41f入口，不授权训练。

## 来源、定义和已决边界

- 定义依据[词表v15](../knowledge/mechanics/vocabulary-v15.json)，规则依据[规则v14候选](../knowledge/mechanics/reviews/rules-v14-draft-001.json)。表中“接受/拒绝”只针对明确的机制、对象与条件。
- `P[n]`定位[盲审原文包packet.json](../knowledge/mechanics/reviews/blind-742-001/packet.json)第n项（从0开始），包含`text_741f`、`text_742`、`changed_fields`和`patch_notes_742`；例如`P[13]/text_742/desc_loc`是剑刃风暴新说明。
- `H数字`定位原始文件`knowledge/hero-capabilities/snapshots/2026-11-19/sources/hero-数字-english.json`，在`/result/data/heroes/0/abilities`按表中能力名定位；旧版同路径日期改为`2026-11-06`。每组同时给出H、能力名及P定位，便于核对原文及差异。
- `c###`是[claim-key.json](../knowledge/mechanics/reviews/blind-742-001/claim-key.json)中的真实`claim_id`，不是已批准的事实`review_id`。对照[盲审答案](../knowledge/mechanics/reviews/blind-742-001/answers.json)、[旧行复核](../knowledge/mechanics/reviews/recheck-742-001/claude-review.json)和[新能力审阅](../knowledge/mechanics/reviews/new-abilities-742-001/results/batch-001.json)。
- `Notes`指[官方7.42说明原始文件](../knowledge/mechanics/reviews/patch-update-2026-11-19/notes/datafeed-7.42-english.json)。下方给出JSON指针；短摘录均可回查。

**不再询问U181–188已决事项**：R09魔抗说明已经落实；U182证据优先级及沙王震中A杖范围伤害、戴泽编织魔晶治疗、死亡先知巫术精研加速、帕格纳生命汲取持续施法按原决定；U183巨魔改状态抗性；U184命石文字退休；U187吸魂巫术是伤害和治疗、不是吸血；U188变形A杖不是范围伤害、噬咬魔晶有自身位移。U185盲审授权不是批准117条提案，U186视野工程授权不是游戏语义批准。米波掘地改A杖条件已落实双AI纠错，不冒充用户决定。

## G：全局规则

| 编号／当前定义 | 当前来源差异 | A：建议与具体影响 | B：替代选择 |
|---|---|---|---|
| **G1 束缚**：R18将束缚与缠绕/捆缚一起阻止受`ROOT_DISABLES`限制的位移；`leash`旧定义含不能闪烁/传送。 | `Notes /general_notes/0/generic/33/note`：“Leashes that do not expressly pierce debuff immunity … will no longer prevent movement-based abilities”。 | 仅收窄R18的束缚分支及词表：明确无视减益免疫的束缚才有这一阻止位移关系；缠绕/捆缚不改。逐技能核来源属性，不能用目标当前是否免疫替代。 | 暂停该束缚分支准入，待逐技能核实；不继续沿用过时的一般关系。 |
| **G2 隐身符伪装**：R06真视/显隐克制隐身；真视定义为看见隐身单位。 | `Notes /general_notes/2/generic/17/note`：“True Sight protection as long as you're not near enemy heroes or buildings”；激活后2秒启用。 | 给**真视分支**加条件例外：伪装已启用且未靠近敌方英雄/建筑。不编造距离阈值，不扩大成所有`reveal`无效。 | 此场景暂输出未知，其他R06关系独立审阅。 |
| **G3 幻象物品效能**：R20是范围伤害等对幻象的关系；尚无效能属性。 | `Notes /general_notes/0/generic/46–49、53/note`：幻象默认20%，可触发多数攻击特效；`/general_notes/2/generic/19/note`幻象神符为40%。 | 在`illusions`和R20加来源/例外备注，不凭效能变化重判克制关系，不把20%写成所有幻象固定值。 | 新建效能属性及来源级例外，需独立设计数值范围；不是加一个布尔标签。 |
| **G4 格子血量算不算减伤**：`damage_block`含吸收、比例减伤、延迟结算，尚未明确排除格子血量。 | `Notes /general_notes/0/generic/24–28/note`统一pip health；`P[4]`骷髅弓手：“Creeps and illusions deal 25% damage to them”。 | 排除格子血量的统一换算，维持克林克兹旧拒绝，并拒绝同类新提案。弓手规则不能记为英雄本体保命。 | 将其记为指定单位对指定攻击者的条件减伤；须明确受益者，扩大词表范围后统一审查同类记录。 |

G4对应既有待决`cfae8cc03fcac5a12dba`（`clinkz_wind_walk/damage_block`，基础reject），以及新提案`c042`灵能陷阱、`c043`蝗虫群、`c051`群蛇守卫、`c074`超新星、`c076`墨客幻影、`c077`追踪导弹。**同一分类问题只答一次。**

## A：25行既有待决的映射

下表24行，加G4的一行，合计25行（15个旧accept、10个旧reject）。升级条件按实际字段保留：先知范围伤害虽`context=base`仍需魔晶；拉席克三条base记录仍需A杖。

| 编号／原review_id与状态 | 来源差异、现有定义 | A：建议、改动及影响 | B：替代选择 |
|---|---|---|---|
| **A1 剑刃风暴**：`f326696738e9506b9b76`，基础强驱散accept（旧U75）。 | H8 `juggernaut_blade_fury`，`P[13]`：“Applies a basic dispel at the start and end”。强/弱驱散是不同词条。 | 强驱散改拒绝，新增弱驱散`c038`，注明开始/结束时；改变驱散关系和保命类型。 | 强驱散暂未知、补实测；弱驱散可单独接受。 |
| **A2 吸魂巫术**：`991b88a4bed0081d0cb1`，魔晶恐惧accept。 | H43 `death_prophet_spirit_siphon`，`P[7]`：魔晶恐惧文字/字段移除，A杖改减攻速。 | 拒绝旧魔晶恐惧；不改U187伤害/治疗结论。 | 该恐惧记录暂未知，补实测。 |
| **A3 钻地**：`132216459076ba9f1462`，需A杖回蓝accept（旧U52）。 | H88 `nyx_assassin_burrow`，`P[21]`改为“Scarab Metabolism is always active at … strength”。**U50已规定回蓝倍率算回蓝，条件为“倍率，效果取决于已有回蓝”。** | 按U50条件保留回蓝，注明来源是甲虫代谢倍率、钻地/A杖条件；代谢记录直接恢复，派生去重。纠正影响表早先“不是直接回蓝就删”的推断。 | 钻地只记增强关系、回蓝只记代谢；这需明确收窄U50在组合技能中的范围，不是机械删除。 |
| **A4 狂热者**：`audit:chen_zealot:displace_other:base`，基础位移他人accept。 | H66 `chen_zealot`，`P[3]`现为受控单位属性/移速及指定狂热者；旧传送字段删除，传送迁到神圣劝化。 | 拒绝狂热者位移，保留实际提供传送技能的独立事实，避免重复来源。 | 暂未知，补归属实测。 |
| **A5 驱使恶灵**：`audit:death_prophet_exorcism:healing:scepter`、`audit:death_prophet_exorcism:lifesteal:scepter`，两条A杖accept。 | H43 `death_prophet_exorcism`，`P[6]`：A杖删除；基础仍有“at the end … healed in proportion to the damage dealt”。 | 拒绝这两条升级标签；**基础结束治疗保留**，不能把删升级写成整个技能无治疗。 | 两条升级暂未知，基础治疗不受影响。 |
| **A6 青森诅咒**：`121fb347dd76a7845730`范围伤害（需魔晶）、`audit:furion_curse_of_the_forest:grant_vision:shard`，两条accept。 | H53 `furion_curse_of_the_forest`，`P[9]`改为先知/树人攻击分别施加减速与持续伤害；旧魔晶效果消失。U72不把多个单位分别攻击当范围伤害。 | 拒绝两条旧升级记录，当前攻击特效按N6另审。 | 两条暂未知、补实测；不推断额外视野。 |
| **A7 虚无主义**：`09192929b9ff1be1c99d`虚无、`e08e2b451fe9773cfd64`加速、`2d59c5a069b17fad1602`减魔抗、`5fa7df90ed38e15060e2`减速，均accept且需A杖。 | H52 `leshrac_greater_lightning_storm`，`P[15]`改为“an aura that disarms and constantly dispels … Basic Dispel”。 | 拒绝四条旧效果；新光环/弱驱散按N3单审。 | 四个ID可分别暂未知；不从驱散推断虚无/减速。 |
| **A8 生命汲取**：`959b59da03f5fcc0e46f`，A杖法强accept。 | H45 `pugna_life_drain`，`P[22]`：旧A杖删除，新A杖在遗忘学者。 | 拒绝旧A杖法强；U182已定的持续施法不改。 | 此升级暂未知，不重问持续施法。 |
| **A9 高射火炮**：`3ac2f189ccf9f8b69402`，基础攻击特效reject。 | H72 `gyrocopter_flak_cannon`，`P[11]`：“additional attacks can proc attack modifiers … except for Lifesteal and Critical Strike”。现定义是攻击附加效果。 | 维持拒绝：允许另一来源特效触发，不等于自带特效。可保留传播条件。 | 将“承载其他来源特效”也纳入词条，需区分自带/传播并重审计数范围。 |
| **A10 幽魂子弹**：`audit:muerta_spectral_slug:displace_other:shard`，魔晶位移他人accept。 | H138 `muerta_spectral_slug`，`P[19]`两版基础原文均有“knocking them back”，当前无魔晶前提。 | 保留位移，将条件改为基础；不新增一次重复击退。 | 先补升级条件实测，整行暂未知。 |
| **A11 部分破坏**：`a2ab422aa2bd8ff700c2`戴泽编织、`982d94c571914df47a7b`风行顺风，均旧U47reject。 | H50 `dazzle_innate_weave`与H21 `windrunner_tailwind`的`notes_loc`明确仅阻止新层数、不影响既有层数收益；脚本`IsBreakable=1`。词表允许“技能的一部分”被破坏。 | 两行改条件accept，**仅阻止叠新层，既有收益保留**；派生关系携带局部范围。 | 两项分别暂未知；若只认完全失效，须明确改变现词表。 |
| **A12a–f 旧U47六条拒绝**：精确ID见下表。 | 当前脚本唯一顶层`IsBreakable=1`，但字段不证明所有子效果全部失效。 | 建议先补具体作用范围，再逐项裁定；也可明确选择条件accept，只承认可破坏标记，并阻断依赖完整作用范围的克制结论。 | 旧reject保留历史，7.42继续unknown；不能写成已证明不可破坏。 |
| **A13 天隼冲击**：`audit:kez_falcon_rush:terrain_walk:base`，基础accept。 | H145 `kez_falcon_rush`，`P[14]`只有rush、`phased collision`与减速抗性。**U96已将跳跃/冲刺纳入terrain_walk**，但无单位碰撞不证明可越悬崖。 | 先补新版地形实测；符合U96的可过地形冲刺则条件保留，不凭碰撞文字批准。 | 若希望所有定向冲刺都算，需明确修改地形要求；不能让用户猜缺失事实。 |

A12脚本位于`knowledge/game-files/snapshots/2026-11-19/sources/scripts/npc/heroes/`，核能力定义顶层键，不借用同名数值块/命石块。

| 编号 | subject／review_id | 当前脚本与待核范围 |
|---|---|---|
| A12a | `centaur_horsepower`／`e8a993868f697cea1824` | `npc_dota_hero_centaur.txt`，H96：力量带来的移速。 |
| A12b | `keeper_of_the_light_bright_speed`／`f89a92aface0738ce292` | `npc_dota_hero_keeper_of_the_light.txt`，H90：智力移速及移动视野路径是否同受影响。 |
| A12c | `morphling_ebb_and_flow`／`d57452d5f3dc954eb4bc` | `npc_dota_hero_morphling.txt`，H10：力量/敏捷两组射程、减速抗性、移速。 |
| A12d | `terrorblade_dark_unity`／`95b085c137a279f9648c` | `npc_dota_hero_terrorblade.txt`，H109：邻近幻象加成范围。 |
| A12e | `tusk_bitter_chill`／`8c4650d7a1be53be72d6` | `npc_dota_hero_tusk.txt`，H100：被动减攻速光环。 |
| A12f | `wisp_equilibrium`／`26c05d2566461e5cf1e1` | `npc_dota_hero_wisp.txt`，H91：高血量增伤与低血量恢复/治疗增幅。 |

## N：新提案，按能力和条件分别答

这些有当前文字/AI支持，尚不等于用户批准。A1弱驱散、G4格子血量、U188噬咬位移不重复列。基础/升级条件及施效者必须随结果保留；受控单位效果不能写成英雄本体效果。

| 编号／claim_id | 来源、短摘录与现定义 | A：建议与影响；B：替代 |
|---|---|---|
| **N1** 沙王穿刺`c037` | H16，`P[27]/text_742/scepter_loc`：“create Stinger attack areas along the path”；范围伤害是一次施放/攻击可伤多个单位。 | A接受A杖范围伤害，注明沿途延迟Stinger攻击区；B只记升级关系，不另计范围标签。英雄统计不重复。 |
| **N2** 陈狂热者`c040` | H66，`P[3]`：“move speed to non-hero units under Chen's control”。 | A接受基础加速，受益者限受控非英雄单位，不计陈本体逃生；B仅挂受控单位效果，需要统一能力归属口径。 |
| **N3** 拉席克虚无主义`c044,c045` | H52，`P[15]`明确aura、Basic Dispel。 | A接受光环/弱驱散，分别写对附近敌方与自身的作用，核能力获取条件；B逐标签暂未知，不沿用旧效果。 |
| **N4** 赤红甲`c041` | `P[28]/text_742/desc_loc`：“Buckler Aura … armor to allied player units”。 | A接受物品护甲光环；B只记现有护甲字段，不纳入光环分类。 |
| **N5** 动能力场`c050` | H87，`P[33]/text_742/shard_loc`：“Electromagnetic Repulsion … reduced knockback”。 | A接受魔晶位移他人，限触碰力场触发；B等关联能力补证，不凭名称推断范围伤害。 |
| **N6** 青森诅咒`c058` | H53，`P[9]`攻击施加减速/持续伤害，符合攻击附加效果。 | A接受基础攻击特效，保留先知/树人归属和独立层数；B只记具体效果，暂不提升分类。 |
| **N7** 迷雾缠绕`c052,c053,c054` | H102，`P[35]`盟友加速、敌人减速；A杖“affects all units in a … radius”。 | A分别接受基础加速/减速、A杖范围伤害；B逐claim选择，未选继续未知，不混淆友敌效果。 |
| **N8** 死亡先知`c066,c067,c068` | H43，`P[39]`腐朽魔晶充能/减速；`P[7]`吸魂巫术A杖“steals … attack speed”。 | A接受前者魔晶充能/减速及后者A杖减攻速；B逐claim暂未知。U187不变。 |
| **N9** 遗忘学者`c075` | H45，`P[42]/text_742/scepter_loc`：“consuming an Oblivion Savant charge”。 | A接受A杖充能，注明该能力支持额外施法；B只记额外施法关系。不推断各技能有独立额外充能。 |
| **N10** 兽王雷肤兽`c080,c081,c082` | H38，`P[45]`：“calls forth an Ancient Thunderhide”，其Slam伤害/减速附近敌人；U72不把多召唤物各自攻击当范围伤害。 | A接受A杖召唤及**召唤物Slam**的减速/范围伤害；B只把召唤挂英雄，其余挂召唤物能力并保留可达关系。 |
| **N11** 混沌骑士末日冲锋`c083,c084,c085` | H81，`P[46]`持续移动积累速度，有大招幻象才能“charge over terrain”。 | A接受加速、条件自身位移/无视地形，保留移动蓄速及幻象存活条件；B逐标签暂未知。 |
| **N12a** 同技能`c086`；**N12b** `c087` | `P[46]/text_742/notes_loc`激活召集幻象；`desc_loc`：“Chaos Knight and the illusions will attack units they charge over”。 | A：a记位移他人、对象限自身幻象；b记条件范围伤害，依据**英雄本人的沿途攻击**，不是多幻象攻击。B：a只记召回关系；b先实测本人一次冲锋多目标。两项单答，不能自动证明克制幻象的整对关系。 |
| **N13** 戴泽穿越虚界`c088` | H50，`P[47]`：“pulls his body … to his spirit”，仅投影期间、返回结束投影。 | A接受魔晶自身位移，保留投影/身体受限条件；B只记返回关系。不因此生成对敌控制标签。 |
| **N14** 狼人群猎`c089–c093` | H77，`P[48]`攻击标记、增伤、按攻击伤害治疗；“revealed through fog of war and invisibility”。 | A分别接受攻击特效、吸血、治疗、显隐、视野，限标记目标/攻击者；B逐标签决定。吸血/治疗计数去重。 |
| **N15a** 米波`c060–c062,c094–c096` | H82，`P[38]/text_742/shard_loc`与`P[49]`：投掷携带单位、落点范围伤害与减速。 | A接受魔晶位移他人/范围伤害/减速，规范来源放实际投掷子能力、父能力记授予；B两处都记录但标同事件/别名并去重。一次投掷不能算两份。 |
| **N15b** 米波分摊`c063,c097` | 同上：“If the carried target is a Meepo, it shares damage with the carrier”。只在举起期间，比例未写；减伤定义尚未明确是否包含转移给队友。 | A不直接记damage_block，另存条件伤害共享；B将本体转移承伤纳入条件减伤，必须记另一承担者。两claim只答一次，不推断总承伤降低、比例或死亡风险降低。 |
| **N16** 甲虫代谢`c099–c101` | H88，`P[50]`不受伤一段时间后加速，并按最大生命/法力恢复。 | A接受基础加速/治疗/回蓝，保留生效条件，与A3钻地倍率去重；B逐标签决定。这里有实际恢复，不只是治疗增强。 |
| **N17** 不朽尸王噬咬`c102–c107` | H85，`P[51]`按伤害治疗；英雄被沉默/减速，小兵变可控僵尸；“Bite cannot miss”。 | A分别接受魔晶吸血/治疗、沉默/减速、召唤、必中，保留英雄/小兵目标分支与“仅此噬咬必中”；B逐claim裁定。自身位移c108不重问。 |
| **N18** 友军时光倒流`c109–c111` | H63，`P[52]`回到5秒前位置；Strong Dispel；“Disjoints projectiles”。 | A接受A杖位移他人/强驱散/躲避弹道；B逐标签暂未知。不顺带新增未提案的治疗/回蓝分类。 |
| **N19** 幽冥守卫`c114` | H45，`P[54]`对每个施法敌方英雄分别开火。范围伤害定义是“一次施放或一次攻击能对多个敌方单位造成伤害”，此处有放置生命周期与每次触发两种计数单位。 | A暂不准入通用范围伤害，先明确计数单位；若按每次触发只有一个目标则建议拒绝。B按一次放置生命周期接受条件范围伤害，限定多个敌方英雄分别施法；不能据此推断对幻象/小兵范围伤害。 |

## E：工程补证，不让用户猜事实或机械批准

2026-11-27更新：[14条工程附件](patch742-engineering-evidence-followup.md)已完成条件/关联/目标文本核验。11条支持明确条件或原文，3条行为仍未知；旧admission的69+9+25计数未被自动改写。下表记录证据缺口及后续消费，而不是全部尚未提取。

| 编号 | 缺口与下一步 | 不应怎么处理 |
|---|---|---|
| **E1 69行** | 29行无复核lane：28行脚本改变，1行熊缠绕缺完整双语/当前注册表证据；39行`keep_two_ai/unclear`；1行谜团魔晶召唤未落实“敌方英雄”条件。谜团已生成敌方英雄/每次眩晕/魔晶/不分裂的条件提案，待新候选生产者消费并重建；其余逐行补字段/原文/行为证据。 | 不批量问“69行是否通过”。完整源同一性已经证明的行已承接，不把旧user basis改称7.42用户批准。 |
| **E2 9行** | 持续施法：米波忽悠、陨星锤；单体指向：死亡契约target_team=0，以及吞噬、感染、变形、幻影突袭、衰老、噬魂的CUSTOM目标。7条单体指向已补双语目标文本与行为字段，待显式准入重建；2条引导已有文字，仍缺中断行为证据。 | CHANNELLED位或CUSTOM不自动等于U51词表含义，也不需用户重批机械值。 |
| **E3 关联能力** | `c046–c048`已固定3秒Open Wounds及关联减速/吸血/治疗文本；`c073`已证明关联电磁排斥，但触墙调用的范围继承仍未知。这4行旧候选已是two_ai_overlay可用，仍非用户批准；新证据附件不冒充已重新准入。 | 保留盲审unclear历史与后续候选状态；不从关联名称推断触发范围，也不把同一回血事件计成两次。 |
| **E4 视野/地形** | `c098`米波投掷只有`vision_radius=300`，需受益者、位置、时长；A13需7.42冲刺越崖/树木实测。 | 字段非零不是完整视野证据，无单位碰撞不是越地形证据；用户可提供观察，定义选择不能填补事实。 |
| **E5 破坏范围** | A11已有新/旧层数说明，可条件裁定；A12六条补子效果范围。 | 不重问已机械核验的全部65行；IsBreakable不覆盖旧U47冲突、不证明整体失效。 |
| **E6 已排除/空白** | `c112,c113`扫射及`c115–c117`幽冥守卫的命石提案按U184排除；`c059`携带时自身缴械不记对敌控制；`chaos_knight_armageddon_end`缺说明继续未知。 | 不把退休命石或空技能当已通过，也不把103行当成所有新提案。新提案仍需逐项核注册表、升级条件及是否已落实。 |

## 如何回复与落实

可按编号少量回复，例如：`G1=A；A1=A；A3=A（条件保留倍率）；N12a=B；N12b=先实测；N17仅接受c103/c104/c105，其他暂缓`。同组标签可拆答，不设“全部批准”捷径。

收到明确决定后，才关联对应review_id/claim_id，新增用户决定记录，更新候选事实/规则并重建派生和专项回归。未回复项继续pending，工程补证独立推进。营地类型、战略区域、路径/视野另按地图证据评审，不由本页代替，也不用旧7.41f区域填新版未知。

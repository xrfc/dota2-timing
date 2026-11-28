# 用Workshop Tools导出7.42地图数据（用户自己操作）

2026-11-27：本地已收到2026-11-23导出，目录`data/workshop-map-742-build26825343`，client 6989、Steam build 26825343；不需要重复导出。五文件校验和新旧对比见[7.42绑定](patch-asset-binding.md)。以下操作步骤保留给后续版本使用，上游最新版本的旧查询仅代表当时结果。

上游`leamare/dota-map-coordinates`最新仍是7.41（2026-11-20查）。它的数据是在Dota 2的Workshop Tools里跑一个自定义游戏导出的，用户可以自己在7.42上跑一遍。按工作区规则，助手不操作用户的Dota 2客户端，所以本页的步骤都由用户来做；导出的文件交给助手后，后面的处理不用联网。

上游README写得很简（[README](https://github.com/leamare/dota-map-coordinates#readme)），下面的步骤按README和它的脚本整理，**助手没有亲自跑过**，第一次做可能会遇到README没写到的问题，遇到了把报错发给助手。

## 我们要哪些文件

| 文件 | 内容 | 我们用来做什么 |
|---|---|---|
| `gridnavdata.json` | 每个64×64格子是否可走（只列不可走的） | 区域、可走路径、视野模拟 |
| `elevationdata.json` | 每格高度层 | 高低地、视野遮挡 |
| `mapdata.json` | 建筑、树、商店、野点、神符等实体的坐标 | 塔、树、地标 |
| `worlddata.json` | 地图边界 | 坐标换算 |
| `lanedata.json`（可选） | 兵线路径 | 区域草稿里的兵线分段 |

## 准备（只做一次）

1. Windows上的Steam，Dota 2已更新到7.42。
2. 在Steam库里右键Dota 2 → 属性 → DLC，勾选**Dota 2 Workshop Tools**（免费），等它下载完。
3. 下载上游仓库：<https://github.com/leamare/dota-map-coordinates>（绿色Code按钮 → Download ZIP），解压到一个文件夹，下面叫“仓库目录”。
4. 上游的`.bat`脚本把Dota 2写死在`C:\Program Files (x86)\Steam\steamapps\common\dota 2 beta\`。如果你的Dota 2装在别处，先用记事本把`copymap.bat`、`copydata.bat`、`textvmap.bat`里的这段路径改成你的实际路径。

## 导出

1. 在仓库目录双击运行`copymap.bat`：把当前（7.42）地图文件复制进自定义游戏，并在Dota 2目录下建几个空的输出文件。
2. 把仓库目录里的`content`和`game`两个文件夹复制到`<Dota 2目录>\`下（和已有的`content`、`game`合并；只会新增`dota_addons\dota-map-coordinates`）。
3. Steam库里右键Dota 2 → **Launch Dota 2 - Tools**。在弹出的列表里选`dota-map-coordinates`，启动。
4. 打开控制台，输入`dota_launch_custom_game dota-map-coordinates dota`，等游戏加载；随便选个英雄进入游戏。
5. 把控制台（VConsole）切到VScript输出，等加载完成，导出数据会打印出来。README的做法是把VConsole的输出保存成仓库目录里的`data\map_data.log`。脚本也会尝试把结果直接写到`<Dota 2目录>\game\dota\`下的`mapdata.json`等四个文件；如果那几个文件里有内容，运行`copydata.bat`把它们复制到仓库的`data\`即可。
6. （可选，要兵线路径时）运行`textvmap.bat`，把地图转成文本`data\*.vmap.txt`。

## 交给助手

把仓库目录的`data\`文件夹整个打包发过来（至少要那四个json；有`map_data.log`和`*.vmap.txt`也一起）。助手这边：

- 用`process_console.py`把日志转成json（如果第5步只拿到日志），生成兵线路径；上游的`process_data.py`要Python 2.7，助手在本地处理，不用你装。
- 和7.41的数据比对：塔、野点、双生之门、河道格子哪里变了，出新旧对照图给你看（就是之前说的地图对照）。
- 存为新的地图参考版本，7.41版保留不动（U178的待办改为“用户导出”）。

## 注意

- Workshop Tools会占几个GB的硬盘。
- 导出的是地图的静态数据（地形、实体位置），不含任何账号信息，可以放进仓库（U146）。
- 如果之后上游自己出了7.42版本，以上游为准再对照一次。

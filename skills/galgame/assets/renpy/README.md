# galgame Ren'Py 框架

Ren'Py 只当渲染器。文本、选项、每个选项的反应由模型按批返回，引擎负责贴图、打字机、存读档、章节推进。框架里不含任何具体作品：角色、世界观、场景、立绘、开场全部是数据。

## 怎么跑

用 SDK：装 Ren'Py 8.5 以上，新建空项目，把 `game/` 覆盖进去，Launcher 里运行。

用绿色版：把 `game/` 和 `options.txt` 放到运行时旁边，运行时目录要有 `<名字>.exe` 和同名的 `<名字>.py`。

不填密钥时走离线 mock，界面、选项、存档照常验证。填 key 不用改文件：游戏内点「MODEL」，或在主菜单「设置」里改模型项，填地址、模型名和 Key，保存后会同时写进运行时和 `options.txt`，下一批生效。填了密钥但没放图，背景是深色占位块，立绘透明，剧情不受影响。

## 配置

`options.txt` 是设置文件，只放设置，不放提示词。分了十四类：作品与角色、世界观与注入、对话模型、备用模型、多智能体、内容来源、生图、上下文、场景与镜头、节奏、选择密度、章节、显示、调试。每行都有注释，所有开关都用 0/1 数值。

场景和立绘不再写在 options 里：场景扫 `picture/scene/` 的文件名（必须是 `<time>_<place>.jpg`，时间只用 day / dusk / night），立绘以人物卡「## 立绘」为准（id 必须是数字），时间词可用 `game/time_words.json` 覆盖。`GALGAME_SCENE_LOCK=1`（默认）时模型在三种时间里选，一批最多换一次，且要满足最短停留；目标组合没有图就保持当前场景。

优先级：环境变量 > `options.txt` > `key.txt`（只覆盖非空项）> 代码默认值。

最常改的四行：

```
GALGAME_GENRE=校园恋爱          # 提示里的题材措辞
GALGAME_HEROINE=                # 留空则取 persona/ 里 lead: true 的那张
GALGAME_HEROINE_AUTO=1          # 留空时按初始好感度选女主角
GALGAME_PLAYER_SPRITE=0         # 是否显示「我」的立绘
GALGAME_ENDLESS=1               # 无限故事，没有结局
```

## 目录

```
options.txt                 配置
README.md                   这份文件
game/
├── ai.rpy                  模型调用、预取、剧情树、重注入、子智能体、日记、harness、生图
├── script.rpy              图片注册、渲染循环、存读档界面、动态舞台
├── seikai.md               世界观（复制 seikai.example.md 再改）
├── persona/<id>.md       人物卡，一张一个角色，下划线开头的文件忽略；me.md 是玩家角色
├── director.md             父合成规则（子智能体模式，可改）
├── agent.md                子角色规则，一份注入所有子请求（可改）
├── picture/scene/          背景，文件名 = <time>_<place>.jpg
├── picture/standing/<id>/<立绘id>.webp   立绘，目录是角色 id，文件名是立绘数字 id
├── picture/ui/             界面装饰：choice.png / dialogue.png / title.png，可选
├── bgm/<数字>.mp3          BGM，文件名只用数字 id
├── bgm/bgm.md              BGM 用法，随世界观交给主模型
├── voice/                  运行期生成的语音，按角色 id 分子目录
├── voice_example/          声生声用的参考音频，按角色名字命名
├── voice_ids.json          复刻音色缓存
├── opening.json            开场前几拍，可选
└── mock.json               离线样例剧情，可选
savedata/
├── slot_<n>.json / .png    存档与截图
├── history.json            每一拍的记录
├── chapters.json           章节大纲
├── diary/<角色>.json        子智能体日记（events + impressions）
└── harness/                和 harness 交换请求的文件队列
```

## 每拍长什么样

模型返回的 beats 里，`character` 是说话人或「旁白」，`standing` 是这一刻的立绘 id。旁白写 `character: "旁白"`、`standing: null`，代表所有人的动作和「我」的心理，不显示名字框。

多人同镜：`character: "绫&沈岚"`，`standings: {"绫":1,"沈岚":2}`，最多三人；全员同时说话写 `character: "全员"`，立绘取 `picture/standing/all/<数字>.webp`。同一件事、同一场景里服装必须固定，换装要由剧情交代。引擎自己用 `time + place` 组装背景，不让模型直接指定。

立绘 id 以人物卡「## 立绘」的键值块为准，**立绘 id 必须是数字**，每个差分四行：

```markdown
### 立绘 1

id：1
动作：站着，双手在身前交叠
表情：眼睑下垂
什么时候用：默认；防备时
```

图片放 `picture/standing/aya/1.webp`：目录是角色 id，文件名是立绘数字 id。写几节就能用几个差分。

## 起一个新作品

1. 复制整个目录，改 `GALGAME_SAVE_DIR`，免得和别的作品串档
2. 按 `references/seikai.md` 写 `game/seikai.md`，主要场所要和 `picture/scene/` 的文件名对上
3. 按 `references/persona.md` 写人物卡，存成 `persona/<id>.md`，女主角那张写 `lead: true`
4. 放背景图，文件名用 `day_` / `dusk_` / `night_` 加地点；中文时间词要改就写 `game/time_words.json`
5. 复制 `opening.example.json` 为 `opening.json`，写开场两拍，第一屏就靠它
6. 出图：自己画好的立绘用 `python ../../scripts/import_standing.py --game-dir . --role <id> --dir <图片目录>` 导入；其余用 `python ../../scripts/gen_art.py --game-dir . --dry-run` 看提示词，再去掉 `--dry-run` 生成
7. 离线跑一遍确认界面，再填密钥接模型

## 注入与重注入

每批请求的 system prompt 是：世界观 → 女主角人物卡 → 格式与规则。

- 平时注入世界观摘要，每 `GALGAME_REINJECT_EVERY` 拍（默认 40）完整重注入一次
- 切换模型时强制重注入，计数归零
- 人物卡的「## 剧情设定」和世界观的「## 当前局势」由引擎定期回写摘要

## 三种内容来源

`GALGAME_USING_HARNESS` 和 `GALGAME_SUBAGENTS` 决定谁来写。子代理开关独立于来源。harness 子代理模式要求宿主支持 galgame Skill 说明的 story_chat 文件协议。

**单模型**：一次请求出整批，默认。

**subagents**：`GALGAME_SUBAGENTS=1`。每张非玩家 persona 卡一个子调用，各自只拿到世界观 + 自己的人物卡 + `game/agent.md` + 最近 `GALGAME_HISTORY_FEED` 拍的全局历史，只返回台词和顺序。主模型按 `game/director.md` 把台词接成拍、补旁白、重排顺序、写 choices；台词按原文逐字回填，漏掉的补在末尾。每个角色有 `savedata/diary/<角色>.json`，记 `events` 和 `impressions`，每 `GALGAME_DIARY_EVERY` 拍更新。重注入按全局历史拍数，每 `GALGAME_REINJECT_EVERY` 拍把各自的人设、世界观和规则文件升为全文。

**harness**：`GALGAME_USING_HARNESS=1` 且 `GALGAME_HOST=harness`。引擎把请求写成 `savedata/harness/request-<id>.json`，等 `response-<id>.json` 回来。独立模板默认关闭 harness；显式开启时需要宿主消费队列，连接超时会提示。

## 自愈模型

默认关闭。`GALGAME_DOCTOR=1` 打开，`GALGAME_DOCTOR_MODEL` 填模型名才真正启用。接口和 key 可以单独写 `GALGAME_DOCTOR_ENDPOINT` / `GALGAME_DOCTOR_KEY`，留空复用主模型或备用模型。

它在后台每 `GALGAME_DOCTOR_INTERVAL` 秒巡检一次，做三件事：主模型返回坏 JSON 时让自愈模型修格式；主模型连续失败时补 4 拍安全过渡；预取卡住超过 `GALGAME_DOCTOR_STALL` 秒时清掉旧请求并切到备用或自愈模型。每局最多调用 `GALGAME_DOCTOR_MAX` 次，防止无限重试。

关闭开关时，非 harness 模式不启用自愈模型；harness 模式把修复和安全剧情交给 harness 模型处理。开启且填了模型时，harness 下也直接用下面这组模型，不再走 harness 自愈。

`GALGAME_HARNESS_SELF_HEAL=0` 会让 `self_heal` 直接为 false，即使开关关着也不让 harness 修。

harness 请求里会带 `self_heal`、`doctor`、`doctor_mode` 和 `doctor_hint`：开关关着时 `self_heal` 为 true，由 harness 模型修；开关开着时交给 option 模型，同时告诉 harness `self_heal: false`。

harness 模式下引擎不再单独发 `doctor` 请求。正常的 batch 请求会带这几个字段；当 `doctor_mode` 是 `subagent` 时，harness 应在回包前派一个子代理校验 beats 和 choices，把坏 JSON 修好再返回，这样不会每错一次就多一个请求。harness 拒绝或修不好时，引擎仍按 `GALGAME_DOCTOR_MAX` 放弃，回退到本地 `error_batch`。

## 语音

`GALGAME_VOICE=1` 才启用。角色台词在预取时后台合成，存到 `voice/<角色id>/<数字>.wav`，显示到那一拍时播放；`GALGAME_VOICE_PLAYER=1` 才给「我」生成声音，旁白永远没有声音。

`GALGAME_VOICE_MODE` 两种：`tts` 文生声、`clone` 声生声（参考音频放 `voice_example/<角色名字>.wav`，找不到就用文生声）。

**OpenAI 兼容**：`GALGAME_VOICE_API=openai`，`GALGAME_VOICE_ENDPOINT` 填完整的 `/audio/speech` 地址；人物卡「## 声音」会作为 `instructions` 传过去。

**阿里云百炼**：`GALGAME_VOICE_API=dashscope`。

- 文生声：`GALGAME_VOICE_MODEL=qwen3-tts-flash`，`GALGAME_VOICE_ENDPOINT` 可留空（默认 `https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation`），音色用 `GALGAME_VOICE_NAME=Cherry`；人物卡 frontmatter 写 `voice_name: Serena` 可以单独换音色。「## 声音」的自由描述在百炼里不生效。
- 声生声：填 `GALGAME_VOICE_CLONE_WORKSPACE`（百炼控制台的业务空间 WorkspaceId）和 `GALGAME_VOICE_CLONE_MODEL`（默认 `qwen-audio-3.1-tts-plus`）。引擎先 `create_voice` 把本地参考音频转成 data URI 提交，轮询 `query_voice` 到 `OK`，再调 `SpeechSynthesizer` 合成；拿到的音色 id 缓存在 `game/voice_ids.json`，删掉这个文件可以重新复刻。

请求和返回都做了兼容：音频二进制、JSON 里的 `output.audio.url`、base64、`data:audio/...` 都能落盘。

## 设置界面

主菜单有「设置」，列出 options.txt 里的全部设置。开关直接点，文本和数字点开输入；改完点「保存到 options.txt」，重启后全部生效。模型项也在「设置」里；游戏内「MODEL」快捷页保留，保存时同样先解锁再写。

游戏启动时会占住 options.txt，外部程序可以读，但不能写。要改设置请用游戏里的界面；保存时会短暂解锁、写完马上重新锁上。锁不上时设置页会提示，仍会尝试保存。

## BGM

`game/bgm/` 放音频，文件名只用数字 id，支持 mp3、ogg、wav、m4a、opus，比如 `1.mp3`、`2.ogg`。`game/bgm/bgm.md` 写每个 id 什么时候用，这份说明会跟世界观一起交给主模型。开 subagents 时只给合成的主模型，角色子调用不看。

模型在每一拍的 `bgm` 字段里返回 id。引擎只在 id 变化时换，不会每拍重播；换得太勤会被 `GALGAME_BGM_MIN_STAY` 按住。`0` 表示停，`null` 或不写表示沿用上一拍。

没有音频文件时不会注入 BGM 规则，`bgm` 写 `null`。

## 生图开关

五个整数开关：`GALGAME_GEN_SCENE`、`GALGAME_GEN_STANDING`、`GALGAME_GEN_UI_CHOICE`、`GALGAME_GEN_UI_DIALOGUE`、`GALGAME_GEN_UI_TITLE`。

- `0` 只用 `picture/` 里已有的图，默认；`gen_art.py` 与 `import_standing.py` 也会跳过立绘，不生成、不抠图
- `1` 写进 harness 队列，由外层 agent 生成
- `2` 用 `GALGAME_IMAGE_*` 配的生图模型，后台生成、落盘、立即生效

Ren'Py 运行时没有 Pillow，模式 2 的立绘是白底的。要透明立绘用 `scripts/gen_art.py` 离线抠图。

## 章节文件

路径 `savedata/chapters.json`。模型生成后写进去，你也可以手改，重启或读档后生效。

```json
{
  "current": 2,
  "chapters": [
    {
      "no": 1,
      "title": "第一章 借笔",
      "begin": "开学第二天，转学生坐到靠窗的空位。",
      "develop": "借笔、上课、放学下雨借伞。",
      "end": "雨停之后她把伞还回来，两人从陌生变成能说上话。"
    },
    {
      "no": 2,
      "title": "第二章 雨",
      "begin": "连着下了三天雨，她开始每天带两把伞。",
      "develop": "一起走的那段路变长，她说了家里的事。",
      "end": "雨停的那天，她第一次主动等在门口。"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `current` | 整数 | 当前播到第几章，必须能在 `chapters` 里找到 |
| `chapters` | 数组 | 章节列表，读取时按 `no` 升序重排 |
| `no` | 整数 | 章节序号，从 1 开始，重复的会被丢掉 |
| `title` | 字符串 | 写成「第X章 一个具体意象」 |
| `begin` | 字符串 | 这一章的开头，30 到 60 字 |
| `develop` | 字符串 | 两三个具体事件，60 到 120 字 |
| `end` | 字符串 | 结尾，30 到 60 字，留一个能接下去的场面 |

文件必须是合法 JSON，中文直接写，引号用英文双引号。缺字段补默认值，格式不对的条目跳过，游戏照常运行。`current` 超过最后一章时会收回到最后一章。把 `current` 改成某章，读档后从那一章接着走。

一章写到 60% 时，引擎在后台生成下一章的大纲。快到章尾时，下一章内容和人设一起注入，然后接着生成下一批，所以故事只会一章接一章往下走，不会结束。

`GALGAME_ENABLE_CHAPTER=0` 时这个文件不生效，剧情不分章节，也没有结局。

## 验收

不要靠截图。开 `GALGAME_DEBUG=1`，看这几处：

- `ai_debug.log`：启动行打印选中的女主角、场景数、立绘、生图模式；每次请求打印耗时、拍数、选项数、是否重注入
- `savedata/history.json`：每一拍的 `turn`、`path`、`character`、`standing`、`is_speech`、`scene`
- `savedata/diary/`：子智能体模式下每个角色的日记
- `savedata/harness/`：harness 模式下请求和回包

无头跑用例：

```
renpy.exe <项目路径> test <用例名>
```

lint 会提示几条 `im.Composite` 过时和中文文件名不适用 zip，都不影响运行：前者是缺图占位图的实现，后者是本地路径；要打 zip 分发时把 `persona/`、`picture/standing/` 的目录名换成英文 id 即可，引擎两者都找。

## 许可

框架自己的代码（`ai.rpy`、`script.rpy`、`scripts/gen_art.py`、`import_standing.py` 和文档）走 Apache License 2.0，全文在根目录 `LICENSE`，署名在 `NOTICE`，第三方组件在 `THIRD_PARTY_NOTICES.md`。改了框架文件再分发，按 Apache 2.0 第 4(b) 条在文件里注明改动。

Ren'Py 引擎主要是 MIT，部分库是 LGPL。分发的游戏要带 `game/LICENSE.txt`，保留 renpy.org 的许可证链接，不能阻止用户替换引擎。剧本不必开源。建议在 README 或商店页写：

> This program contains free software licensed under a number of licenses, including the GNU Lesser General Public License. A complete list of software is available at http://www.renpy.org/doc/html/license.html.

字体是 Ren'Py SDK 自带的思源黑体 Lite（OFL 1.1），全文在 `game/fonts/LICENSE-OFL.txt`。`game/gui/` 是 Ren'Py 项目模板的默认界面贴图，按 Ren'Py 的许可证走，正式作品建议换成自己的。SDK 里 `the_question` 和 `tutorial` 的示例美术另有版权，不要搬进项目。

图像和语音由模型生成时，商用前确认生成服务的条款。角色和剧本必须原创。BGM 用 CC0 或已授权素材，并在 About 页注明来源。

## 存档与记录

所有存档、历史记录都在游戏目录的 `savedata/`，启动后自动创建，不在 `%APPDATA%`。剧情历史不按拍数裁剪，长局会持续增长；需要控制体积时请手动归档或清空 `savedata/`。

- `slot_1.json` ~ `slot_6.json` + 同名 `.png`：六个手动存档与截图
- `slot_quick.json` / `.png`：Q.SAVE
- `slot_auto.json` / `.png`：每次选完选项后的自动存档
- `history.json`：所有分支的拍，结构见下
- `chapters.json`：章节大纲与当前章
- `diary/<角色>.json`：子智能体日记
- `harness/`：harness 模式的请求与回包

`history.json` 顶层：

- `cursor`：已经播到第几拍（`turn` 值），读档从这里接
- `path`：当前分支路径，根是 `[]`，选第 1 项后是 `[0]`
- `chapter` / `chapter_start`：当前章节名和本章起始拍
- `records`：所有分支的拍，未选中的分支也在，用 `path` 区分

`records` 里每拍：

- `turn`：全局递增，不按分支重置
- `path`：这一拍属于哪条分支
- `character`：显示名；旁白是「旁白」，多人是 `A&B`，全员是「全员」
- `characters`：名字数组（开场记录里可能没有）
- `standings`：这一拍每个角色的立绘 id，如 `{"绫":1,"沈岚":2}`（开场记录里可能没有）
- `speaker`：旁白为空串，其余等于 `character`
- `is_speech`：true 才加「」
- `standing`：主立绘 id，旁白为 null；`mood` 是兼容字段，值相同
- `scene`：`time + place` 组装后的场景 id
- `affection` / `flags`：这一拍结算后的快照
- `choices` / `chosen`：只有带选项的拍才有；`chosen` 是选中下标，没选过就没有这个键

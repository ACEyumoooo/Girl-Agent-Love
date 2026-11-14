---
name: galgame
description: 日式恋爱视觉小说的 Ren'Py 实时生成框架。模型按批写对白与旁白、预取掩盖延迟、剧情树与按拍存读档、章节无限推进、多角色同镜、可攻略角色好感度、子智能体分工、harness 桥接与生图开关。当用户想做视觉小说、恋爱模拟、美少女游戏，或要把已有故事续写成 Ren'Py 游戏、设计角色卡与世界观时使用。
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
metadata:
  trigger: 做视觉小说、galgame、恋爱模拟；续写故事做成 Ren'Py 游戏
  version: 1.0-b
---

# Galgame Ren'Py 框架

Ren'Py 只当渲染器。文本、旁白、选项由模型按批生成，引擎负责贴图、打字机、存读档、章节和预取。技能包里不含任何具体作品，角色、世界观、场景、立绘都是数据。

## 目录

技能包内：

```
assets/renpy/
├── options.txt                 设置文件（只放设置，不放提示词）
├── README.md                   工程说明与验收
└── game/
    ├── ai.rpy                  生成、注入、预取、剧情树、章节、存档、子智能体、harness
    ├── script.rpy              渲染循环、舞台、存读档界面
    ├── screens.rpy / gui.rpy / fonts.rpy / options.rpy / guisupport.rpy
    ├── seikai.md               世界观（示例 seikai.example.md）
    ├── persona/<id>.md         人物卡，下划线开头的文件忽略；me.md 是玩家角色
    ├── director.md             父合成规则（子智能体模式）
    ├── agent.md                子角色规则，一份注入所有子请求
    ├── picture/scene/          背景，文件名 = 场景 id
    ├── picture/standing/<id>/  立绘，文件名 = 立绘数字 id
    ├── picture/ui/             选项框、对话栏、首页装饰，可选
    └── seikai.example.md / opening.example.json / mock.example.json / art_prompts.example.json
scripts/
├── gen_art.py                  批量生成背景与立绘
├── import_standing.py          导入用户自己提供的立绘
└── save.py                     对话模式存档脚本（不在本技能流程内）
```

所有路径都相对技能目录或你的项目目录，不依赖 `~/.dsh`。复制 `assets/renpy/` 到项目里就自带这套结构。

## 跑起来

装 Ren'Py 8.5 以上，新建空项目，把 `game/` 覆盖进去；或用绿色版（exe + 同名 .py + `renpy/` + `lib/` + `game/`）。

```
renpy.exe <项目路径> lint
renpy.exe <项目路径> test <用例>
```

不填 `GALGAME_KEY` 时走离线 mock，界面和存档照常能验。玩家可以在游戏内点「MODEL」，或在主菜单「设置」里填地址、模型名和 Key；保存会同时写进运行时和 `options.txt`。验收看 `ai_debug.log` 和 `savedata/history.json`，不要靠截图。

## 数据文件

**世界观** `game/seikai.md`：一句话、时代与地点、世界规则、主要场所、人物关系、禁忌与尺度、当前局势。主要场所要和 `picture/scene/` 里的文件名对得上。规范见 `references/seikai.md`。

**人物卡** `game/persona/<id>.md`：frontmatter 写 `id`、`name`、`aliases`、`lead`、`romance`、`affection`；正文写外貌、说话方式、雷区、立绘。规范见 `references/persona.md`。

**玩家卡** `game/persona/me.md`：写「我」的设定，模板 `_ME_TEMPLATE.md`。会单独注入，写旁白和「我」的台词时遵守；不参与女主角选择、攻略判定和子智能体名单。

**场景**：引擎启动时扫描 `picture/scene/` 的文件名（去扩展名）作为场景 id，必须长成 `<time>_<place>`。没有图时用内置 11 组校园组合兜底。

**立绘**：id 以人物卡「## 立绘」的键值块为准，图片在 `picture/standing/<角色id>/<数字>.webp`。没有人物卡时扫 standing 目录。

**时间词**：场景时间只有 day、dusk、night 三种，对应白天、黄昏、夜晚；中文词可在 `game/time_words.json` 里按 `{"day":["早上","清晨"]}` 覆盖。

## 每拍字典

模型只输出一个 JSON：

```json
{
  "plan": "这一段想写什么，40字以内",
  "chapter": "第一章 一个具体意象",
  "scene_plan": [{"at": 0, "time": "dusk", "place": "classroom"}],
  "beats": [
    {"character": "旁白", "standing": null, "is_speech": false,
     "text": "班主任领她进来，她走到靠窗那一列。", "time": "dusk", "place": "classroom"},
    {"character": "绫", "standing": 1, "is_speech": true,
     "text": "……借一下。", "time": "dusk", "place": "classroom", "shot": "medium"},
    {"character": "绫&沈岚", "standings": {"绫": 1, "沈岚": 2}, "is_speech": true,
     "text": "一起说。", "time": "dusk", "place": "classroom"},
    {"character": "全员", "is_speech": true,
     "text": "全班一起。", "time": "dusk", "place": "classroom"}
  ],
  "choices": [
    {"label": "借给她", "hint": "她会记住", "add": 1, "target": "绫", "react": "她点了一下头。"}
  ]
}
```

- **旁白**：`character` 写「旁白」，`standing` 为 null，不显示名字、不加引号、不换立绘。旁白代表所有人的动作和「我」的心理。
- **单人**：`character` 写人物卡的 `name`，`standing` 是整数。
- **多角色同镜**：`character` 写 `A&B`，`standings` 写 `{"A":1,"B":2}`，最多三人；显示名就是 `A&B`。
- **全员**：`character` 写「全员」，`standing` 写数字，立绘取 `picture/standing/all/<数字>.webp`；缺图时透明。
- **玩家台词**：`character` 写「我」，`is_speech: true`；玩家的动作和心理写进旁白。
- `is_speech` 为 true 时引擎自动加「」，正文里不要自带引号。
- `scene` 由引擎用 `time + place` 组装并校验，模型不用写。

## 注入与重注入

每批 system prompt 顺序：世界观 → 女主角人物卡 → 立绘与多人规则 → 生成格式。

- 平时注入世界观摘要，每 `GALGAME_REINJECT_EVERY` 拍完整重注入一次
- 切换模型时强制重注入，计数归零
- 人物卡「## 剧情设定」和世界观「## 当前局势」由引擎定期回写摘要

## 好感度与攻略

- 只有 `romance: true` 的角色才有好感度，默认女主角可攻略，其他角色默认不可攻略
- 初始好感度写在人物卡 frontmatter 的 `affection`，只对新档开局生效
- 注入时每个可攻略角色分开说「初始 / 当前 / 阶段 / 这一阶段的表现边界」；不可攻略角色明说没有好感度，不写恋爱线
- 好感度不在界面显示，只驱动她的态度和事件
- 选项的 `add` 默认加给女主角，写 `"target":"角色名"` 加给别人；对不可攻略角色会被忽略

## 自己新增角色

`GALGAME_AUTO_CHARACTER=1` 时模型可以在 batch 里带 `new_characters`：

- 正式角色：`id/name/aliases/one_line/appearance/speech/taboo/romance/standings`，引擎校验后写成 `persona/<id>.md` 并注册，下一批可出场
- 临时配角：`{"temporary":true,"name":"..."}`，不建卡、不做立绘，只当这一批的说话人
- 每批上限由 `GALGAME_AUTO_CHARACTER_MAX` 和 `GALGAME_TEMP_CAST_MAX` 控制

## 三种内容来源

是否使用子代理由 GALGAME_SUBAGENTS 决定；harness 与自备模型只决定传输方式。

- **单模型**（默认）：一次请求出整批。
- **subagents**：每张非玩家 persona 卡一个子调用，各自只拿世界观、自己的人物卡、`game/agent.md` 和最近 `GALGAME_HISTORY_FEED` 拍的全局历史，**只返回台词和顺序，不写旁白、不写动作**；父模型按 `game/director.md` 补旁白、重排拍序、写 choices。台词按子智能体原文逐字回填，漏掉的补在末尾。子模型用 `GALGAME_SUBAGENT_MODEL`（留空用 `GALGAME_MODEL`），不跟主模型的降级走。重注入按全局历史拍数，每 `GALGAME_REINJECT_EVERY` 拍把各自的人设、世界观、规则文件升为全文。
- **harness**：`GALGAME_USING_HARNESS=1` 且 `GALGAME_HOST=harness` 时通过 `savedata/harness/` 文件队列收发。开了它就不使用对话模型；直接启动默认使用本地演示；显式开启 harness 后需有宿主消费队列。

宿主处理 `kind="story_chat"` 时，按 `stage` 区分 `subagent` 和 `director`。逐条保留 `messages` 的角色和内容，按 `output_format` 生成（`json_object` 仍以 JSON 文本放入 `content`，`text` 放纯文本）。`role` 只标记本次子代理扮演的人物。写回 `response-<id>.json`，格式为 `{"id":"原请求ID","content":"模型返回的文本"}`。每个角色请求独立处理，导演只在框架收齐子代理结果后收到整合请求。非子代理模式仍使用现有 `kind="batch"` 与 `batch/result` 响应。

## 生图

五个开关分别控制：背景（`GEN_SCENE`）、立绘（`GEN_STANDING`）、选项框（`GEN_UI_CHOICE`）、对话栏（`GEN_UI_DIALOGUE`）、首页（`GEN_UI_TITLE`）。

- `0` 用 `picture/` 里已有的图；立绘设 0 时 `gen_art.py` 不排立绘、`import_standing.py` 不抠图
- `1` 交给 harness 生成
- `2` 用 `GALGAME_IMAGE_*` 配的生图模型，后台生成、落盘生效

运行时生成的立绘是白底的（Ren'Py 没有 Pillow），透明立绘用 `gen_art.py` 离线抠图。规范见 `references/art.md`。

## 自愈模型

默认关闭。`GALGAME_DOCTOR=1` 打开，`GALGAME_DOCTOR_MODEL` 填模型名才真正启用。接口和 key 可以单独写 `GALGAME_DOCTOR_ENDPOINT` / `GALGAME_DOCTOR_KEY`，留空复用主模型或备用模型。

它在后台每 `GALGAME_DOCTOR_INTERVAL` 秒巡检一次，做三件事：主模型返回坏 JSON 时让自愈模型修格式；主模型连续失败时补 4 拍安全过渡；预取卡住超过 `GALGAME_DOCTOR_STALL` 秒时清掉旧请求并切到备用或自愈模型。每局最多调用 `GALGAME_DOCTOR_MAX` 次，防止无限重试。

关闭开关时，非 harness 模式不启用自愈模型；harness 模式把修复和安全剧情交给 harness 模型处理。开启且填了模型时，harness 下也直接用下面这组模型，不再走 harness 自愈。

## 语音

`GALGAME_VOICE=1` 时，角色台词会先合成语音再播放：

- `GALGAME_VOICE_MODE=tts`：文生声，用人物卡「## 声音」的描述做音色提示
- `GALGAME_VOICE_MODE=clone`：声生声，用 `game/voice_example/<角色名字或id>.wav` 做参考；找不到参考音频时退回文生声
- `GALGAME_VOICE_PLAYER=0`（默认）时「我」不生成声音；设 1 才生成
- 旁白没有声音；临时配角必须有 `voice_prompt`，否则不生成
- 语音按 `voice/<角色id>/<数字>.wav` 存，数字 id 递增，删掉目录会重新生成
- `GALGAME_VOICE_API` 选协议：`openai` 走 OpenAI 兼容的 `/audio/speech`（描述放 `instructions`）；`dashscope` 走阿里云百炼；留空按端点自动识别

阿里云百炼的配法：

- 文生声：`GALGAME_VOICE_API=dashscope`、模型 `qwen3-tts-flash`，请求打到 `.../services/aigc/multimodal-generation/generation`；音色只能从固定列表选（`GALGAME_VOICE_NAME`，人物卡 frontmatter 的 `voice_name` 可逐个覆盖），自由描述不生效
- 声生声：先 `create_voice` 用参考音频建音色，轮询 `query_voice` 到 `OK`，再用 `SpeechSynthesizer` 合成；需要 `GALGAME_VOICE_CLONE_WORKSPACE`（业务空间 WorkspaceId），音色 id 缓存在 `game/voice_ids.json`
- 复刻接口只收公网 URL 或 `data:audio/wav;base64,...`，引擎会把 `voice_example/` 里的本地文件转成 data URI；输出统一存 wav
- 返回音频二进制、JSON 里的 `audio.url`、base64 或 data URI 都认

## BGM

`game/bgm/` 放音频，文件名只用数字 id，比如 `1.mp3`。`game/bgm/bgm.md` 写每个 id 的使用场合，这份说明随世界观交给主模型；subagents 模式下只给合成的主模型。

模型在每拍返回 `bgm` id。引擎只在 id 变化时换，不重播同一条；`GALGAME_BGM_MIN_STAY` 防止换得太勤。`0` 表示停，`null` 或不写表示沿用。

## 场景、服装与节奏

- 背景由 `时间 + 地点` 组装，只能从 `picture/scene/` 现有的场景里选；同一个地点要覆盖它会出现的时间
- 时间由正文时间词决定，方位词不算过渡；同一背景至少停留 `GALGAME_SCENE_MIN_STAY` 拍
- **场景锁定**（`GALGAME_SCENE_LOCK=1`，默认）：模型在 day / dusk / night 里选 time，引擎按选中的组合取图；一批最多换一次，且要满足 `GALGAME_SCENE_MIN_STAY`。目标组合没有图时保留当前场景
- **服装固定**：同一件事、同一场景里不要换衣服；换装必须由剧情明确交代。人物卡「立绘」每节的样貌要写清这套衣服是什么
- `GALGAME_ENDLESS=1`（默认）时故事没有结局，章节一直往后接；`0` 时允许模型给 `ending`，故事可以收束
- 一次提前决定 10–20 拍，选项时所有分支并发预取，用 `react` 掩盖延迟；关掉 rollback 和 autosave，存档写自定义 JSON，按 `path + turn` 精确到拍

## 起一个新作

1. 复制 `assets/renpy/` 到项目目录；自定义剧情存读档在 `savedata/`，要换位置用 `GALGAME_SAVEDIR` 环境变量（不是 `GALGAME_SAVE_DIR`）
2. 按 `references/seikai.md` 写 `game/seikai.md`，主要场所对上场景文件名
3. 按 `references/persona.md` 写人物卡，存成 `persona/<id>.md`，女主角写 `lead: true`、`romance: true`、`affection`
4. 出图：自己画好的立绘用 `python scripts/import_standing.py --game-dir <项目> --role <id> --dir <图片目录>`；其余用 `python scripts/gen_art.py --game-dir <项目>`
5. 复制 `opening.example.json` 为 `opening.json`，写开场两拍
6. 跑 lint 和离线 mock，确认界面；再填密钥接模型

如果用户拿来的是别人写的故事要续写，先通读原作，把时代、地点、人物、已发生的事写进 `seikai.md` 和人物卡，不要套用本技能里的原型或事件池。

## 许可

Ren'Py 是 MIT 加部分 LGPL，分发的游戏要带 `game/LICENSE.txt`，保留 renpy.org 的许可证链接，不能阻止用户替换引擎。剧本不必开源。

字体是 Ren'Py SDK 自带的思源黑体 Lite（OFL 1.1），不要换成 Windows 的微软雅黑、黑体、宋体。`game/gui/` 是项目模板的默认贴图，正式作品建议替换。SDK 里 `the_question` 和 `tutorial` 的示例美术另有版权。

图像由 AI 生成，商用前确认生成服务条款，角色与剧本必须原创。BGM 用 CC0 或已授权素材并注明来源。

## 资源

- `assets/renpy/` — 完整框架与 options 模板
- `assets/renpy/game/persona/_TEMPLATE.md` — 空白人物卡
- `references/persona.md` — 人物卡规范
- `references/seikai.md` — 世界观规范
- `references/art.md` — 背景与立绘规范
- `references/characters.md` — 角色写法参考（不写死剧情）
- `references/structure.md` — 节奏与分支参考（不写死剧情）
- `references/dialogue.md` — 文风规则
- `scripts/gen_art.py` / `scripts/import_standing.py` — 出图与导入

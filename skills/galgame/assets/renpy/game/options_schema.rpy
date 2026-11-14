# 由 options.txt 的注释与键生成；game/options_schema.rpy
init -10 python:
    OPTIONS_SCHEMA = [
        {"title": '一、作品与角色', "items": [
            {"key": 'GALGAME_GENRE', "default": '校园恋爱', "desc": '题材词，只影响提示里的措辞，比如「校园恋爱」「都市治愈」「奇幻冒险」', "kind": 'text', "restart": False},
            {"key": 'GALGAME_HEROINE', "default": '', "desc": '指定女主角：写人物卡的 id 或 name。留空且「自动选择女主角」开启时，自动选初始好感度最高的角色', "kind": 'text', "restart": True},
            {"key": 'GALGAME_HEROINE_AUTO', "default": '1', "desc": '开启后，上面「指定女主角」留空时自动选初始好感度最高的角色；关闭时只使用上面填写的角色。', "kind": 'switch', "restart": True},
            {"key": 'GALGAME_SAVE_DIR', "default": '', "desc": 'Ren\'Py 自带存档目录名（不是自定义剧情存读档的 savedata）。留空用 galgame-<女主角 id>', "kind": 'text', "restart": True},
            {"key": 'GALGAME_PLAYER_SPRITE', "default": '0', "desc": '开启后允许「我」显示立绘，需要在 persona 里写人设，并在立绘文件夹中放入图片；关闭时主角不出立绘。', "kind": 'switch', "restart": False},
        ]},
        {"title": '二、世界观与注入', "items": [
            {"key": 'GALGAME_REINJECT_EVERY', "default": '40', "desc": '每多少拍把世界观、人设、章节、日记摘要完整重注入一次，防止漂移。切换模型时会强制重注入一次，计数归零', "kind": 'int', "restart": False},
            {"key": 'GALGAME_DETAIL_INTERVAL', "default": '50', "desc": '每多少拍把新剧情里的长期设定合并写回人物卡的「## 剧情设定」一节', "kind": 'int', "restart": False},
            {"key": 'GALGAME_PERSONA_MAX', "default": '20', "desc": '人物卡里最多保留多少条长期设定', "kind": 'int', "restart": False},
            {"key": 'GALGAME_AUTO_CHARACTER', "default": '0', "desc": '开启后允许模型在剧情里自行新增角色；关闭时只使用现有角色卡。新增角色会按人物卡规则保存。', "kind": 'switch', "restart": False},
            {"key": 'GALGAME_AUTO_CHARACTER_MAX', "default": '1', "desc": '开启自动新增角色时，一次请求最多新增几个正式角色。', "kind": 'int', "restart": False},
            {"key": 'GALGAME_TEMP_CAST_MAX', "default": '2', "desc": '模型请求返回一次最多几个临时配角', "kind": 'int', "restart": False},
        ]},
        {"title": '三、对话模型（开启 harness 生成时不使用这一组）', "items": [
            {"key": 'GALGAME_ENDPOINT', "default": '', "desc": 'OpenAI 兼容的 chat/completions 地址', "kind": 'text', "restart": False},
            {"key": 'GALGAME_KEY', "default": '', "desc": '密钥', "kind": 'secret', "restart": False},
            {"key": 'GALGAME_MODEL', "default": '', "desc": '', "kind": 'text', "restart": False},
            {"key": 'GALGAME_TIMEOUT', "default": '60', "desc": '单次请求超时，秒', "kind": 'int', "restart": False},
            {"key": 'GALGAME_THINKING', "default": '1', "desc": '思考强度。数值越高模型想得越久、回复越慢，可选值请查所用模型的接口文档；默认 1 是最低强度。', "kind": 'int', "restart": False},
        ]},
        {"title": '四、备用模型', "items": [
            {"key": 'GALGAME_FALLBACK_MODEL', "default": '', "desc": '主模型窗口满或报错时自动切过去；GALGAME_FALLBACK_MODEL 留空就不启用', "kind": 'text', "restart": False},
            {"key": 'GALGAME_FALLBACK_ENDPOINT', "default": '', "desc": '备用模型的地址和密钥，留空就沿用上面主模型的地址和 key\n也就是说：只写 FALLBACK_MODEL 也能用，等于同一个服务商换一个模型', "kind": 'text', "restart": False},
            {"key": 'GALGAME_FALLBACK_KEY', "default": '', "desc": '', "kind": 'secret', "restart": False},
            {"key": 'GALGAME_DOCTOR', "default": '0', "desc": '开启后使用下面这组自愈模型：后台检查坏 JSON、补安全剧情；关闭时非 harness 不启用，harness 模式下交给 harness 模型。', "kind": 'switch', "restart": False},
            {"key": 'GALGAME_DOCTOR_MODEL', "default": '', "desc": '自愈模型名；留空不启用', "kind": 'text', "restart": False},
            {"key": 'GALGAME_DOCTOR_ENDPOINT', "default": '', "desc": '自愈模型的独立接口；留空复用主模型或备用模型的地址和 key', "kind": 'text', "restart": False},
            {"key": 'GALGAME_DOCTOR_KEY', "default": '', "desc": '', "kind": 'secret', "restart": False},
            {"key": 'GALGAME_DOCTOR_INTERVAL', "default": '15', "desc": '后台巡检间隔，秒', "kind": 'int', "restart": False},
            {"key": 'GALGAME_DOCTOR_STALL', "default": '90', "desc": '预取卡住多少秒算异常', "kind": 'int', "restart": False},
            {"key": 'GALGAME_DOCTOR_MAX', "default": '3', "desc": '一局最多调用自愈模型几次，防止无限重试', "kind": 'int', "restart": False},
            {"key": 'GALGAME_DOCTOR_FRAME', "default": '1', "desc": '开启后在新人上场时截取游戏画面，检查头顶是否被切、两人是否重叠、对话框上方是否露出下半身，再把 dx/dy/zoom 回写到引擎并按角色缓存。需要先开启自愈，并至少填一个能看图的模型；关闭则不检查。', "kind": 'switch', "restart": False},
            {"key": 'GALGAME_DOCTOR_VISION_MODEL', "default": '', "desc": '构图检查用的视觉模型；留空用 GALGAME_DOCTOR_MODEL\n文本模型看不了图，这里要填支持图片输入的模型', "kind": 'text', "restart": False},
            {"key": 'GALGAME_DOCTOR_FRAME_MAX', "default": '8', "desc": '一局最多检查几次立绘构图，防止反复调用', "kind": 'int', "restart": False},
            {"key": 'GALGAME_HARNESS_SELF_HEAL', "default": '1', "desc": '开启后允许 harness 自己修复坏响应；关闭时只由引擎按上面的开关处理。', "kind": 'switch', "restart": False},
        ]},
        {"title": '五、多智能体', "items": [
            {"key": 'GALGAME_SUBAGENTS', "default": '0', "desc": '开启后每张非玩家 persona 卡单独调用一次子模型，各自只拿到自己的卡、世界观和 game/agent.md；主模型按 game/director.md 补旁白、重排并写选择。关闭时由一个模型写全部内容。', "kind": 'switch', "restart": False},
            {"key": 'GALGAME_SUBAGENT_MODEL', "default": '', "desc": '子模型用的模型名。留空就用上面的 GALGAME_MODEL。', "kind": 'text', "restart": False},
            {"key": 'GALGAME_SUBAGENT_LINES', "default": '2', "desc": '每个子模型这一轮给几句台词', "kind": 'int', "restart": False},
            {"key": 'GALGAME_DIARY_EVERY', "default": '50', "desc": '每多少拍给每个角色写一次日记（做过什么、对别人的印象）', "kind": 'int', "restart": False},
        ]},
        {"title": '六、内容来源：harness 还是语言模型', "items": [
            {"key": 'GALGAME_USING_HARNESS', "default": '1', "desc": '开启后交给当前 harness 生成（通过 savedata/harness/ 的文件队列），不再使用第三、四节的对话模型；用 renpy.exe 直接启动时没有 harness，会自动回退到对话模型并在日志里写明。关闭时使用上面的对话模型生成。', "kind": 'switch', "restart": False},
            {"key": 'GALGAME_HOST', "default": 'harness', "desc": '启动方标记。harness 启动时应设成 harness；renpy.exe 启动时保持空', "kind": 'text', "restart": False},
            {"key": 'GALGAME_HARNESS_TIMEOUT', "default": '45', "desc": '等 harness 回包最多多少秒，超时这一批走错误提示', "kind": 'int', "restart": False},
        ]},
        {"title": '七、生图（五张图分别控制）', "items": [
            {"key": 'GALGAME_GEN_SCENE', "default": '0', "desc": '开启后缺少背景图时，调用生图模型补 picture/scene/<time>_<place>.jpg（例如 dusk_classroom.jpg）；关闭时不生成。', "kind": 'switch', "restart": False},
            {"key": 'GALGAME_GEN_STANDING', "default": '0', "desc": '开启后缺少立绘时，调用生图模型补 picture/standing/<角色id>/<立绘id>.webp；关闭时不生成。', "kind": 'switch', "restart": False},
            {"key": 'GALGAME_GEN_UI_CHOICE', "default": '0', "desc": '开启后缺少选项框装饰时，调用生图模型补 picture/ui/choice.png；关闭时不生成。', "kind": 'switch', "restart": False},
            {"key": 'GALGAME_GEN_UI_DIALOGUE', "default": '0', "desc": '开启后缺少对话栏装饰时，调用生图模型补 picture/ui/dialogue.png；关闭时不生成。', "kind": 'switch', "restart": False},
            {"key": 'GALGAME_GEN_UI_TITLE', "default": '0', "desc": '开启后缺少首页装饰时，调用生图模型补 picture/ui/title.png；关闭时不生成。', "kind": 'switch', "restart": False},
            {"key": 'GALGAME_IMAGE_ENDPOINT', "default": '', "desc": '生图接口\nOpenAI 兼容写带 compatible-mode 的 /images/generations，引擎自动分辨', "kind": 'text', "restart": True},
            {"key": 'GALGAME_IMAGE_KEY', "default": '', "desc": '生图密钥，留空时复用上面的 GALGAME_KEY', "kind": 'secret', "restart": True},
            {"key": 'GALGAME_IMAGE_MODEL', "default": '', "desc": '', "kind": 'text', "restart": True},
            {"key": 'GALGAME_IMAGE_SIZE', "default": '1280*720', "desc": '背景出图尺寸（宽*高，万相 2.1 每边 512-1440）', "kind": 'text', "restart": True},
            {"key": 'GALGAME_IMAGE_SIZE_PORTRAIT', "default": '960*1440', "desc": "立绘出图尺寸。Ren'Py 里没有 Pillow，运行时生成的立绘是白底的，这个包自带抠图，但是如果要精致请找模型，可以试试https://github.com/TongjiAI4E/VN_Sprite_Expression_Workflow", "kind": 'text', "restart": True},
            {"key": 'GALGAME_ART_NOTE', "default": '日系校园恋爱视觉小说，干净线条，柔和自然光，低饱和蓝灰配暖橙点缀，人物比例写实偏二次元，背景轻微景深', "desc": '全作统一画风说明，gen_art.py 会追加到每条立绘提示里', "kind": 'text', "restart": False},
        ]},
        {"title": '八、语音，使用前请查看自己的语音模型api文档进行配置，这里的设置可能会修改。', "items": [
            {"key": 'GALGAME_VOICE', "default": '0', "desc": '开启后角色台词会先合成语音存到 game/voice/，显示时播放；关闭时不生成语音。', "kind": 'switch', "restart": False},
            {"key": 'GALGAME_VOICE_MODE', "default": 'tts', "desc": '语音类型，tts 为文生声， clone 为声生声。', "kind": 'text', "restart": False},
            {"key": 'GALGAME_VOICE_API', "default": 'dashscope', "desc": '语音供应商：dashscope（阿里云）、mimo、openai_official 或 other。旧 openai 值保留兼容接口。', "kind": 'text', "restart": False},
            {"key": 'GALGAME_VOICE_ENDPOINT', "default": '', "desc": '语音接口。openai 协议要填完整的 /audio/speech 地址；\n百炼留空默认 https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation', "kind": 'text', "restart": False},
            {"key": 'GALGAME_VOICE_KEY', "default": '', "desc": '语音密钥，留空复用 GALGAME_KEY', "kind": 'secret', "restart": False},
            {"key": 'GALGAME_VOICE_MODEL', "default": 'qwen3-tts-flash', "desc": '模型：百炼文生声写 qwen3-tts-flash；OpenAI 兼容按服务商填', "kind": 'text', "restart": False},
            {"key": 'GALGAME_VOICE_NAME', "default": 'Cherry', "desc": '百炼文生声的固定音色（Cherry/Serena/Ethan…，见百炼音色列表）；\n人物卡 frontmatter 写 voice_name 可以逐个角色覆盖', "kind": 'text', "restart": False},
            {"key": 'GALGAME_VOICE_LANG', "default": 'Chinese', "desc": '百炼文生声的语种：Chinese / English / Japanese / Auto 等', "kind": 'text', "restart": False},
            {"key": 'GALGAME_VOICE_CLONE_WORKSPACE', "default": '', "desc": '百炼声音复刻：业务空间 WorkspaceId（百炼控制台可查）；clone 模式必填', "kind": 'text', "restart": False},
            {"key": 'GALGAME_VOICE_CLONE_MODEL', "default": 'qwen-audio-3.1-tts-plus', "desc": '复刻音色的目标模型，必须和后面合成用的模型一致', "kind": 'text', "restart": False},
            {"key": 'GALGAME_VOICE_CLONE_PREFIX', "default": 'galgame', "desc": '复刻音色名前缀，只能数字/英文，最长 10 位', "kind": 'text', "restart": False},
            {"key": 'GALGAME_VOICE_FORMAT', "default": 'wav', "desc": '音频格式：wav / mp3（百炼固定按 wav 存）', "kind": 'text', "restart": False},
            {"key": 'GALGAME_VOICE_PLAYER', "default": '0', "desc": '开启后也生成「我」的语音，需要在 persona/me.md 写「## 声音」；关闭时不生成。', "kind": 'switch', "restart": False},
            {"key": 'GALGAME_VOICE_TIMEOUT', "default": '60', "desc": '单条语音超时，秒', "kind": 'int', "restart": False},
        ]},
        {"title": '九、上下文与记忆', "items": [
            {"key": 'GALGAME_CONTEXT_LIMIT', "default": '32000', "desc": '你所用模型的上下文窗口（token），不是越大越好；超过这个比例就压缩历史并考虑切备用模型', "kind": 'int', "restart": False},
            {"key": 'GALGAME_CONTEXT_RATIO', "default": '0.75', "desc": '', "kind": 'float', "restart": False},
            {"key": 'GALGAME_SUMMARY_KEEP', "default": '20', "desc": '压缩时保留最近多少拍原文，其余合并成摘要', "kind": 'int', "restart": False},
            {"key": 'GALGAME_HISTORY_FEED', "default": '8', "desc": '每次请求喂给模型最近多少拍', "kind": 'int', "restart": False},
        ]},
        {"title": '十、场景与镜头', "items": [
            {"key": 'GALGAME_SCENE_MIN_STAY', "default": '5', "desc": '同一背景至少停留多少拍才允许切换，防止背景来回跳', "kind": 'int', "restart": False},
            {"key": 'GALGAME_SCENE_LOCK', "default": '1', "desc": '开启后模型只能在 day / dusk / night 里选，一批最多换一次，并且要满足最短停留；目标组合没有图就保持当前场景。关闭后每拍都可以跟着模型给的 time/place 换。', "kind": 'switch', "restart": False},
            {"key": 'GALGAME_BGM_MIN_STAY', "default": '5', "desc": 'BGM 最少停留多少拍，防止模型频繁切换', "kind": 'int', "restart": False},
            {"key": 'GALGAME_SHOT_VARY', "default": '1', "desc": '开启后镜头会有变化（wide / medium / close），决定立绘远近；关闭时镜头固定。', "kind": 'switch', "restart": False},
        ]},
        {"title": '十一、剧情节奏', "items": [
            {"key": 'GALGAME_PLAN_AHEAD', "default": '40', "desc": '滚动预生成的窗口', "kind": 'int', "restart": False},
            {"key": 'GALGAME_BEAT_MIN', "default": '20', "desc": '每拍最少字数', "kind": 'int', "restart": False},
            {"key": 'GALGAME_BEAT_MAX', "default": '50', "desc": '', "kind": 'int', "restart": False},
            {"key": 'GALGAME_BEAT_SENTENCES', "default": '2', "desc": '', "kind": 'int', "restart": False},
            {"key": 'GALGAME_BEAT_LINES', "default": '2', "desc": '', "kind": 'int', "restart": False},
        ]},
        {"title": '十二、选项框密度', "items": [
            {"key": 'GALGAME_CHOICE_WINDOW', "default": '30', "desc": '统计窗口：每多少拍统计一次', "kind": 'int', "restart": False},
            {"key": 'GALGAME_CHOICE_MIN', "default": '1', "desc": '窗口内至少几次、最多几次选择', "kind": 'int', "restart": False},
            {"key": 'GALGAME_CHOICE_MAX', "default": '2', "desc": '', "kind": 'int', "restart": False},
            {"key": 'GALGAME_MENU_OPTIONS_MIN', "default": '', "desc": '单次最少选项数，留空沿用旧配置', "kind": 'text', "restart": False},
            {"key": 'GALGAME_MENU_OPTIONS_MAX', "default": '', "desc": '单次最多选项数，留空沿用旧配置', "kind": 'text', "restart": False},
            {"key": 'GALGAME_CHOICE_GAP', "default": '12', "desc": '两次选择之间至少隔多少拍', "kind": 'int', "restart": False},
        ]},
        {"title": '十三、章节', "items": [
            {"key": 'GALGAME_ENABLE_CHAPTER', "default": '1', "desc": '开启后有章节推进，第一章写完接第二章；关闭则不分章，剧情一直往下走。', "kind": 'switch', "restart": False},
            {"key": 'GALGAME_ENDLESS', "default": '1', "desc": '开启后没有结局，剧情一直往下走；关闭则允许模型给出 ending，故事可以收束。', "kind": 'switch', "restart": False},
            {"key": 'GALGAME_CHAPTER_LENGTH', "default": '40', "desc": '一章多少拍；到 60% 时提前生成下一章大纲', "kind": 'int', "restart": False},
        ]},
        {"title": '十四、显示', "items": [
            {"key": 'GALGAME_TITLE_MUSIC', "default": '', "desc": '标题音乐路径（相对 game/，例如 bgm/title.ogg；留空则静音，重启生效）', "kind": 'text', "restart": True},
            {"key": 'GALGAME_TEXT_CPS', "default": '36', "desc": '打字机速度，字/秒', "kind": 'int', "restart": False},
            {"key": 'GALGAME_FONT', "default": '', "desc": '显示字体：填 game/fonts/ 下的文件名（.ttf/.otf/.ttc）。\n设置页点「切换」循环选择；保存后需要重启才生效。', "kind": 'text', "restart": True},
        ]},
        {"title": '十五、调试', "items": [
            {"key": 'GALGAME_DEVELOPER', "default": '0', "desc": '开发者工具与控制台（默认关闭，重启生效；与调试日志开关独立）', "kind": 'switch', "restart": True},
            {"key": 'GALGAME_DEBUG', "default": '1', "desc": '开启后写 ai_debug.log，验收看日志和 savedata/history.json，不要靠截图；关闭则不写日志。', "kind": 'switch', "restart": False},
            {"key": 'GALGAME_AUTOSTART', "default": '0', "desc": '开启后跳过主菜单直接进游戏，只给自动化流程用；关闭时正常停在主菜单。', "kind": 'switch', "restart": True},
        ]},
    ]

    # 玩家设置：画面、游戏、文本、音频、键盘。设置页按标签页展示，
    # desc 只写标题，不写括号里的说明或默认值。
    PLAYER_SCHEMA = [
        {"title": '画面显示', "items": [
            {"key": 'GALGAME_DISPLAY_MODE', "default": 'window', "desc": '显示模式', "kind": 'text', "restart": False},
            {"key": 'GALGAME_ASPECT', "default": '16:9', "desc": '画面比例', "kind": 'text', "restart": False},
            {"key": 'GALGAME_ALWAYS_ON_TOP', "default": '1', "desc": '允许悬浮窗', "kind": 'switch', "restart": False},
        ]},
        {"title": '游戏设置', "items": [
            {"key": 'GALGAME_TRANSITIONS', "default": '1', "desc": '场景转场', "kind": 'switch', "restart": False},
            {"key": 'GALGAME_SKIP_READ', "default": '0', "desc": '自动跳过已读文本', "kind": 'switch', "restart": False},
            {"key": 'GALGAME_SKIP_UNSEEN', "default": '0', "desc": '未读文本快进', "kind": 'switch', "restart": False},
            {"key": 'GALGAME_SKIP_AFTER_CHOICE', "default": '0', "desc": '选择后的快进是否解除', "kind": 'switch', "restart": False},
            {"key": 'GALGAME_CTRL_SKIP', "default": 'read', "desc": 'Ctrl 键的快捷方式', "kind": 'text', "restart": False},
            {"key": 'GALGAME_AUTO_AFTER_CHOICE', "default": '0', "desc": '选择后自动模式是否解除', "kind": 'switch', "restart": False},
            {"key": 'GALGAME_MOUSE_HIDE', "default": '0', "desc": '自动隐藏鼠标指针', "kind": 'int', "restart": False},
            {"key": 'GALGAME_SLOT_CLICK', "default": 'single', "desc": '存档、读档的鼠标操作', "kind": 'text', "restart": False},
        ]},
        {"title": '文本', "items": [
            {"key": 'GALGAME_AFM_TIME', "default": '15', "desc": '自动播放等待时间（5–30 秒/250 字符）', "kind": 'int', "restart": False},
            {"key": 'GALGAME_TEXT_SCALE', "default": '100', "desc": '字号缩放（90–115%）', "kind": 'int', "restart": False},
            {"key": 'GALGAME_TEXTBOX_OPACITY', "default": '100', "desc": '对话框不透明度', "kind": 'int', "restart": False},
            {"key": 'GALGAME_TEXTBOX_COLOR', "default": '#fffcf6', "desc": '对话框颜色', "kind": 'text', "restart": False},
            {"key": 'GALGAME_VIEWPOINT_COLOR', "default": '#f5dfb6', "desc": '观点变更时对话框颜色', "kind": 'text', "restart": False},
            {"key": 'GALGAME_TEXT_UNREAD_COLOR', "default": '#242a32', "desc": '未读文字颜色', "kind": 'text', "restart": False},
            {"key": 'GALGAME_TEXT_READ_COLOR', "default": '#525a64', "desc": '已读文字颜色', "kind": 'text', "restart": False},
        ]},
        {"title": '音频设置', "items": [
            {"key": 'GALGAME_ALL_MUTE', "default": '0', "desc": '全部静音（保留原音量）', "kind": 'switch', "restart": False},
            {"key": 'GALGAME_VOL_MASTER', "default": '80', "desc": '主音量', "kind": 'int', "restart": False},
            {"key": 'GALGAME_VOL_BGM', "default": '80', "desc": 'BGM', "kind": 'int', "restart": False},
            {"key": 'GALGAME_VOL_BGM_TALK', "default": '60', "desc": 'BGM（角色说话时）', "kind": 'int', "restart": False},
            {"key": 'GALGAME_VOL_SFX', "default": '80', "desc": '游戏音效', "kind": 'int', "restart": False},
            {"key": 'GALGAME_VOL_VOICE', "default": '90', "desc": '角色语音', "kind": 'int', "restart": False},
        ]},
        {"title": '键盘', "items": [
            {"key": 'GALGAME_KEY_SAVE', "default": 'F2+S', "desc": '打开存档界面', "kind": 'text', "restart": False},
            {"key": 'GALGAME_KEY_LOAD', "default": 'F3+L', "desc": '打开读档界面', "kind": 'text', "restart": False},
            {"key": 'GALGAME_KEY_QSAVE', "default": 'F11', "desc": '快速存档', "kind": 'text', "restart": False},
            {"key": 'GALGAME_KEY_QLOAD', "default": 'F12', "desc": '快速读档', "kind": 'text', "restart": False},
            {"key": 'GALGAME_KEY_SETTINGS', "default": 'F8', "desc": '打开设置', "kind": 'text', "restart": False},
            {"key": 'GALGAME_KEY_FULLSCREEN', "default": 'F4', "desc": '窗口全屏切换', "kind": 'text', "restart": False},
            {"key": 'GALGAME_KEY_ADVANCE', "default": 'Enter', "desc": '下一句/确定', "kind": 'text', "restart": False},
            {"key": 'GALGAME_KEY_AUTO', "default": 'F6+A', "desc": '自动模式', "kind": 'text', "restart": False},
            {"key": 'GALGAME_KEY_SKIP', "default": 'F7+F', "desc": '快进模式', "kind": 'text', "restart": False},
            {"key": 'GALGAME_KEY_CTRL', "default": 'Ctrl', "desc": 'Ctrl 快进', "kind": 'text', "restart": False},
            {"key": 'GALGAME_KEY_HISTORY', "default": 'F5+R', "desc": '打开历史记录', "kind": 'text', "restart": False},
            {"key": 'GALGAME_KEY_HISTORY_PREV', "default": 'PageUp', "desc": '历史记录上一页', "kind": 'text', "restart": False},
            {"key": 'GALGAME_KEY_HISTORY_NEXT', "default": 'PageDown', "desc": '历史记录下一页', "kind": 'text', "restart": False},
            {"key": 'GALGAME_KEY_BACK', "default": 'Backspace', "desc": '上一句', "kind": 'text', "restart": False},
            {"key": 'GALGAME_KEY_REWIND', "default": 'D', "desc": '快退', "kind": 'text', "restart": False},
            {"key": 'GALGAME_KEY_TITLE', "default": 'F10', "desc": '返回标题', "kind": 'text', "restart": False},
            {"key": 'GALGAME_KEY_HIDE', "default": 'Delete', "desc": '隐藏对话框', "kind": 'text', "restart": False},
            {"key": 'GALGAME_KEY_REPLAY', "default": 'F9', "desc": '语音重播', "kind": 'text', "restart": False},
            {"key": 'GALGAME_KEY_SELF_VOICE', "default": '', "desc": '界面朗读开关（默认不绑定，避免占用语音收藏 V）', "kind": 'text', "restart": False},
            {"key": 'GALGAME_KEY_FAV', "default": 'V', "desc": '语音收藏', "kind": 'text', "restart": False},
        ]},
    ]

    for _psec in PLAYER_SCHEMA:
        OPTIONS_SCHEMA.append({"title": _psec["title"], "items": _psec["items"], "player": True})

    OPTIONS_SCHEMA_VERSION = 1
    OPTIONS_SECRET_KEYS = ['GALGAME_DOCTOR_KEY', 'GALGAME_FALLBACK_KEY', 'GALGAME_IMAGE_KEY', 'GALGAME_KEY', 'GALGAME_VOICE_KEY']
    OPTIONS_KNOWN_KEYS = [it["key"] for sec in OPTIONS_SCHEMA for it in sec["items"]]
    OPTIONS_DEFAULTS = {it["key"]: it["default"] for sec in OPTIONS_SCHEMA for it in sec["items"]}
    OPTIONS_DESCS = {it["key"]: it["desc"] for sec in OPTIONS_SCHEMA for it in sec["items"]}
    OPTIONS_KINDS = {it["key"]: it["kind"] for sec in OPTIONS_SCHEMA for it in sec["items"]}

    def text_cps_value(value=None):
        """Schema default is authoritative; zero keeps Ren'Py instant display."""
        default = OPTIONS_DEFAULTS["GALGAME_TEXT_CPS"]
        try:
            return max(0, int(default if value in (None, "") else value))
        except (TypeError, ValueError):
            return max(0, int(default))

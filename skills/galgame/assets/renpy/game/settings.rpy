# 玩家设置页：画面、游戏、文本、音频、键盘。
# 值仍然存在 options.txt 里，写盘沿用 options_store.rpy 的整份原子写。

init 5 python:
    import colorsys
    import math
    import os
    import re
    import shutil
    import time

    OPTION_ITEM_MAP = {it["key"]: it for sec in OPTIONS_SCHEMA for it in sec["items"]}

    SETTINGS_COLOR_TARGETS = [
        ("GALGAME_TEXTBOX_COLOR", "普通对话框"),
        ("GALGAME_VIEWPOINT_COLOR", "观点变更时对话框"),
        ("GALGAME_TEXT_UNREAD_COLOR", "未读文字"),
        ("GALGAME_TEXT_READ_COLOR", "已读文字"),
    ]

    SETTINGS_ADV_LABELS = {
        "GALGAME_GENRE": "题材",
        "GALGAME_HEROINE": "指定女主角",
        "GALGAME_HEROINE_AUTO": "自动选女主角",
        "GALGAME_SAVE_DIR": "Ren'Py 存档目录名",
        "GALGAME_PLAYER_SPRITE": "玩家「我」的立绘",
        "GALGAME_ALWAYS_ON_TOP": "允许悬浮窗",
        "GALGAME_DEVELOPER": "开发者工具与控制台（重启生效）",
        "GALGAME_TITLE_MUSIC": "标题音乐（重启生效）",
        "GALGAME_DETAIL_INTERVAL": "长期设定回写间隔",
        "GALGAME_PERSONA_MAX": "长期设定上限",
        "GALGAME_AUTO_CHARACTER": "允许新增角色",
        "GALGAME_AUTO_CHARACTER_MAX": "每批新增角色上限",
        "GALGAME_TEMP_CAST_MAX": "临时配角上限",
        "GALGAME_SCENE_MIN_STAY": "场景最短停留",
        "GALGAME_SCENE_LOCK": "场景锁定",
        "GALGAME_SHOT_VARY": "镜头变化",
        "GALGAME_SUMMARY_KEEP": "压缩保留拍数",
        "GALGAME_PLAN_AHEAD": "每批拍数",
        "GALGAME_BEAT_MIN": "每拍最少字数",
        "GALGAME_BEAT_MAX": "每拍最多字数",
        "GALGAME_BEAT_SENTENCES": "每拍最多句数",
        "GALGAME_BEAT_LINES": "每拍最多行数",
        "GALGAME_CHOICE_WINDOW": "选择统计窗口",
        "GALGAME_CHOICE_MIN": "窗口内最少选择",
        "GALGAME_CHOICE_MAX": "窗口内最多选择",
        "GALGAME_CHOICE_GAP": "两次选择最短间隔",
        "GALGAME_ENABLE_CHAPTER": "启用章节",
        "GALGAME_ENDLESS": "无限故事",
        "GALGAME_CHAPTER_LENGTH": "每章拍数",
        "GALGAME_USING_HARNESS": "使用 Harness 模型",
        "GALGAME_HOST": "启动来源标记",
        "GALGAME_HARNESS_TIMEOUT": "Harness 等待超时",
        "GALGAME_ENDPOINT": "对话接口地址",
        "GALGAME_KEY": "对话密钥",
        "GALGAME_MODEL": "对话模型名",
        "GALGAME_TIMEOUT": "单次请求超时",
        "GALGAME_THINKING": "思考强度",
        "GALGAME_FALLBACK_MODEL": "备用模型",
        "GALGAME_FALLBACK_ENDPOINT": "备用接口地址",
        "GALGAME_FALLBACK_KEY": "备用密钥",
        "GALGAME_DOCTOR": "使用 DSH 自愈",
        "GALGAME_SUBAGENTS": "子智能体模式",
        "GALGAME_SUBAGENT_MODEL": "子智能体模型",
        "GALGAME_SUBAGENT_LINES": "每个角色每轮台词数",
        "GALGAME_DIARY_EVERY": "日记间隔",
        "GALGAME_REINJECT_EVERY": "重注入间隔",
        "GALGAME_CONTEXT_LIMIT": "上下文预算",
        "GALGAME_CONTEXT_RATIO": "上下文压缩比例",
        "GALGAME_HISTORY_FEED": "喂给模型的近况",
        "GALGAME_GEN_SCENE": "背景生图",
        "GALGAME_GEN_STANDING": "立绘生图",
        "GALGAME_GEN_UI_CHOICE": "选项框装饰生图",
        "GALGAME_GEN_UI_DIALOGUE": "对话栏装饰生图",
        "GALGAME_GEN_UI_TITLE": "首页装饰生图",
        "GALGAME_IMAGE_ENDPOINT": "生图接口",
        "GALGAME_IMAGE_KEY": "生图密钥",
        "GALGAME_IMAGE_MODEL": "生图模型",
        "GALGAME_IMAGE_SIZE": "背景出图尺寸",
        "GALGAME_IMAGE_SIZE_PORTRAIT": "立绘出图尺寸",
        "GALGAME_ART_NOTE": "统一画风说明",
        "GALGAME_VOICE": "启用语音",
        "GALGAME_VOICE_MODE": "生成模式",
        "GALGAME_VOICE_API": "语音协议",
        "GALGAME_VOICE_ENDPOINT": "语音接口",
        "GALGAME_VOICE_KEY": "语音密钥",
        "GALGAME_VOICE_MODEL": "语音模型",
        "GALGAME_VOICE_NAME": "默认音色",
        "GALGAME_VOICE_LANG": "语音语种",
        "GALGAME_VOICE_CLONE_WORKSPACE": "声音复刻空间",
        "GALGAME_VOICE_CLONE_MODEL": "声音复刻模型",
        "GALGAME_VOICE_CLONE_PREFIX": "声音复刻前缀",
        "GALGAME_VOICE_FORMAT": "音频格式",
        "GALGAME_VOICE_PLAYER": "玩家的语音",
        "GALGAME_VOICE_TIMEOUT": "单条语音超时",
        "GALGAME_BGM_MIN_STAY": "BGM 最短停留",
        "GALGAME_TEXT_CPS": "打字机速度",
        "GALGAME_DISPLAY_MODE": "显示模式",
        "GALGAME_ASPECT": "画面比例",
        "GALGAME_DEBUG": "调试开关",
        "GALGAME_AUTOSTART": "自动启动",
    }

    SETTINGS_ADV_CHOICES = {
        "GALGAME_VOICE_MODE": [("tts", "TTS"), ("clone", "克隆")],
        "GALGAME_VOICE_LANG": [("Chinese", "中文"), ("Japanese", "日语"), ("English", "英文")],
        "GALGAME_VOICE_API": [("dashscope", "阿里云"), ("mimo", "MiMo"), ("openai_official", "OpenAI"), ("other", "其他")],
        "GALGAME_HOST": [("harness", "Harness"), ("", "直接启动")],
    }

    SETTINGS_FORCE_SWITCH = {"GALGAME_THINKING"}

    # 玩家设置和原来的高级设置合成一条列表；分组、小标题、顺序都在这里定。
    SETTINGS_LAYOUT = [
        {"id": "game", "title": "游戏设置", "type": "game"},
        {"id": "game1", "title": "游戏设置1", "type": "adv", "groups": [
            ("作品与角色", [
                "GALGAME_GENRE", "GALGAME_HEROINE", "GALGAME_HEROINE_AUTO",
                "GALGAME_SAVE_DIR", "GALGAME_PLAYER_SPRITE", "GALGAME_ALWAYS_ON_TOP",
            ]),
            ("世界观与注入", [
                "GALGAME_DETAIL_INTERVAL", "GALGAME_PERSONA_MAX",
                "GALGAME_AUTO_CHARACTER", "GALGAME_AUTO_CHARACTER_MAX",
                "GALGAME_TEMP_CAST_MAX",
            ]),
            ("场景与镜头", ["GALGAME_SCENE_MIN_STAY", "GALGAME_SCENE_LOCK", "GALGAME_SHOT_VARY"]),
            ("上下文与记忆", ["GALGAME_SUMMARY_KEEP"]),
            ("剧情节奏", [
                "GALGAME_PLAN_AHEAD", "GALGAME_BEAT_MIN", "GALGAME_BEAT_MAX",
                "GALGAME_BEAT_SENTENCES", "GALGAME_BEAT_LINES",
            ]),
            ("选项框密度", [
                "GALGAME_CHOICE_WINDOW", "GALGAME_CHOICE_MIN",
                "GALGAME_CHOICE_MAX", "GALGAME_CHOICE_GAP",
                "GALGAME_MENU_OPTIONS_MIN", "GALGAME_MENU_OPTIONS_MAX",
            ]),
        ]},
        {"id": "chapter", "title": "章节", "type": "adv", "groups": [
            ("", ["GALGAME_ENABLE_CHAPTER", "GALGAME_ENDLESS", "GALGAME_CHAPTER_LENGTH"]),
        ]},
        {"id": "model", "title": "模型", "type": "adv", "groups": [
            ("接入方式", [
                "GALGAME_USING_HARNESS", "GALGAME_HOST", "GALGAME_HARNESS_TIMEOUT",
                "GALGAME_ENDPOINT", "GALGAME_KEY", "GALGAME_MODEL",
                "GALGAME_TIMEOUT", "GALGAME_THINKING",
            ]),
            ("备用与自愈", [
                "GALGAME_FALLBACK_MODEL", "GALGAME_FALLBACK_ENDPOINT",
                "GALGAME_FALLBACK_KEY", "GALGAME_DOCTOR",
            ]),
            ("多智能体", [
                "GALGAME_SUBAGENTS", "GALGAME_SUBAGENT_MODEL", "GALGAME_SUBAGENT_LINES",
                "GALGAME_DIARY_EVERY",
            ]),
            ("上下文", [
                "GALGAME_REINJECT_EVERY", "GALGAME_CONTEXT_LIMIT",
                "GALGAME_CONTEXT_RATIO", "GALGAME_HISTORY_FEED",
            ]),
        ]},
        {"id": "art", "title": "生图", "type": "adv", "groups": [
            ("", [
                "GALGAME_GEN_SCENE", "GALGAME_GEN_STANDING", "GALGAME_GEN_UI_CHOICE",
                "GALGAME_GEN_UI_DIALOGUE", "GALGAME_GEN_UI_TITLE",
                "GALGAME_IMAGE_ENDPOINT", "GALGAME_IMAGE_KEY", "GALGAME_IMAGE_MODEL",
                "GALGAME_IMAGE_SIZE", "GALGAME_IMAGE_SIZE_PORTRAIT", "GALGAME_ART_NOTE",
            ]),
        ]},
        {"id": "display", "title": "画面显示", "type": "display"},
        {"id": "text", "title": "文本", "type": "text"},
        {"id": "audio", "title": "音频", "type": "audio"},
        {"id": "keys", "title": "键盘", "type": "keys"},
        {"id": "debug", "title": "调试", "type": "adv", "groups": [
            ("", ["GALGAME_DEVELOPER", "GALGAME_DEBUG", "GALGAME_AUTOSTART"]),
        ]},
    ]
    SETTINGS_TABS = [(x["id"], x["title"]) for x in SETTINGS_LAYOUT]
    SETTINGS_TITLES = dict(SETTINGS_TABS)
    SETTINGS_LAYOUT_BY_ID = {x["id"]: x for x in SETTINGS_LAYOUT}

    SETTINGS_TEXT_GROUPS = []

    SETTINGS_AUDIO_KEYS = [
        "GALGAME_VOICE", "GALGAME_VOICE_MODE", "GALGAME_VOICE_API",
        "GALGAME_VOICE_ENDPOINT", "GALGAME_VOICE_KEY", "GALGAME_VOICE_MODEL",
        "GALGAME_VOICE_NAME", "GALGAME_VOICE_LANG", "GALGAME_VOICE_CLONE_WORKSPACE",
        "GALGAME_VOICE_CLONE_MODEL", "GALGAME_VOICE_CLONE_PREFIX",
        "GALGAME_VOICE_FORMAT", "GALGAME_VOICE_PLAYER", "GALGAME_VOICE_TIMEOUT",
    ]

    SETTINGS_KEYS = [
        ("GALGAME_KEY_SAVE", "打开存档界面"),
        ("GALGAME_KEY_LOAD", "打开读档界面"),
        ("GALGAME_KEY_QSAVE", "快速存档"),
        ("GALGAME_KEY_QLOAD", "快速读档"),
        ("GALGAME_KEY_SETTINGS", "打开设置"),
        ("GALGAME_KEY_FULLSCREEN", "窗口全屏切换"),
        ("GALGAME_KEY_ADVANCE", "下一句 / 确定"),
        ("GALGAME_KEY_AUTO", "自动模式"),
        ("GALGAME_KEY_SKIP", "快进模式"),
        ("GALGAME_KEY_CTRL", "Ctrl 快进"),
        ("GALGAME_KEY_HISTORY", "打开历史记录"),
        ("GALGAME_KEY_HISTORY_PREV", "历史记录上一页"),
        ("GALGAME_KEY_HISTORY_NEXT", "历史记录下一页"),
        ("GALGAME_KEY_BACK", "上一句"),
        ("GALGAME_KEY_REWIND", "快退"),
        ("GALGAME_KEY_TITLE", "返回标题"),
        ("GALGAME_KEY_HIDE", "隐藏对话框"),
        ("GALGAME_KEY_REPLAY", "语音重播"),
        ("GALGAME_KEY_SELF_VOICE", "界面朗读开关（可不绑定）"),
        ("GALGAME_KEY_FAV", "语音收藏"),
    ]

    def settings_value(key, default=""):
        try:
            value = os.environ.get(key, "").strip() or _FILE_CFG.get(key, "")
        except Exception:
            value = ""
        if value in (None, ""):
            value = OPTIONS_DEFAULTS.get(key, default)
        return str(value)

    def settings_int(key, default=0):
        try:
            return int(float(settings_value(key, str(default))))
        except (TypeError, ValueError):
            return int(default)

    def settings_clamp(value, low, high):
        return max(low, min(high, value))

    def settings_flush():
        if not getattr(store, "settings_dirty", False):
            return True
        ok = options_write(
            options_current_values(_FILE_CFG),
            OPTIONS_UNKNOWN,
            OPTIONS_KEY_EXTRA,
        )
        if ok:
            store.settings_dirty = False
        return ok

    def settings_env_locked(key):
        try:
            return bool(os.environ.get(key, "").strip())
        except Exception:
            return False

    def settings_set(key, value, refresh=True):
        if settings_env_locked(key):
            renpy.notify("这一项由启动器环境变量控制，游戏内修改无效")
            return
        value = str(value)
        _FILE_CFG[key] = value
        store.settings_dirty = True
        if key == "GALGAME_DISPLAY_MODE" or key == "GALGAME_ASPECT" or key == "GALGAME_ALWAYS_ON_TOP":
            apply_display_settings()
        elif key in ("GALGAME_AFM_TIME", "GALGAME_TRANSITIONS", "GALGAME_ALL_MUTE", "GALGAME_TEXT_SCALE"):
            apply_player_preferences()
        elif key.startswith("GALGAME_VOL"):
            apply_audio_settings()
        elif key in ("GALGAME_SKIP_UNSEEN", "GALGAME_SKIP_AFTER_CHOICE", "GALGAME_MOUSE_HIDE", "GALGAME_AUTO_AFTER_CHOICE"):
            apply_game_settings()
        elif key.startswith("GALGAME_KEY_"):
            apply_keymap_settings()
        elif key == "GALGAME_FONT":
            apply_font_live()
        if refresh:
            renpy.restart_interaction()

    def settings_switch_tab(tab):
        store.settings_tab = tab
        if tab == "text":
            settings_load_color()
        renpy.restart_interaction()

    def settings_open(tab=None):
        store.settings_tab = tab or getattr(store, "settings_tab", "display")
        store.settings_font = settings_value("GALGAME_FONT", "SourceHanSansLite.ttf")
        store.settings_dirty = False
        store._settings_open_values = dict(_FILE_CFG)
        store._pending_settings_snapshot = None
        settings_load_sliders()
        settings_load_color()
        settings_make_picker()
        settings_apply_game()
        renpy.show_screen("player_settings")

    def settings_restart_changes():
        snap = getattr(store, "_settings_open_values", None)
        if snap is None:
            return []
        return [
            key for key in OPTION_RESTART_KEYS
            if str(_FILE_CFG.get(key, "")) != str(snap.get(key, ""))
        ]

    def settings_request_restart(action):
        keys = settings_restart_changes()
        if not keys:
            return False
        store._pending_option_updates = options_current_values(_FILE_CFG)
        store._pending_option_restart_keys = tuple(keys)
        store._pending_settings_snapshot = dict(store._settings_open_values)
        renpy.show_screen("options_restart_confirm", keys=keys)
        return True

    def settings_confirm(close=True):
        if settings_request_restart("confirm"):
            return
        if not settings_flush():
            renpy.notify("保存设置失败，请检查配置目录权限")
            return
        store._settings_open_values = dict(_FILE_CFG)
        if close:
            renpy.hide_screen("player_settings")
        else:
            renpy.notify("设置已保存")
        renpy.restart_interaction()

    def settings_close():
        settings_confirm()

    def settings_go_home():
        if settings_request_restart("home"):
            return
        if not settings_flush():
            renpy.notify("保存设置失败，请检查配置目录权限")
            return
        stop_doctor()
        renpy.hide_screen("player_settings")
        try:
            renpy.run(MainMenu(confirm=True))
        except Exception:
            renpy.run(MainMenu())

    def settings_load_sliders():
        store.sv_master = settings_clamp(settings_int("GALGAME_VOL_MASTER", 100), 0, 100)
        store.sv_bgm = settings_clamp(settings_int("GALGAME_VOL_BGM", 100), 0, 100)
        store.sv_bgm_talk = settings_clamp(settings_int("GALGAME_VOL_BGM_TALK", 60), 0, 100)
        store.sv_sfx = settings_clamp(settings_int("GALGAME_VOL_SFX", 100), 0, 100)
        store.sv_voice = settings_clamp(settings_int("GALGAME_VOL_VOICE", 100), 0, 100)
        store.sv_opacity = settings_clamp(settings_int("GALGAME_TEXTBOX_OPACITY", 100), 0, 100)
        store.sv_cps = settings_clamp(text_cps_value(settings_value("GALGAME_TEXT_CPS")), 0, 100)
        store.sv_afm = settings_clamp(settings_int("GALGAME_AFM_TIME", 15), 5, 30)
        store.sv_text_scale = settings_clamp(settings_int("GALGAME_TEXT_SCALE", 100), 90, 115)

    def settings_slider_commit(key, var):
        low, high = {"GALGAME_AFM_TIME": (5, 30), "GALGAME_TEXT_SCALE": (90, 115)}.get(key, (0, 100))
        if settings_env_locked(key):
            setattr(store, var, settings_clamp(settings_int(key, OPTIONS_DEFAULTS.get(key, low)), low, high))
            renpy.restart_interaction()
            return
        value = settings_clamp(int(getattr(store, var, low)), low, high)
        setattr(store, var, value)
        settings_set(key, str(value), refresh=False)
        if key == "GALGAME_TEXT_CPS":
            try:
                store.TEXT_CPS = text_cps_value(value)
                config.default_text_cps = store.TEXT_CPS
                preferences.text_cps = store.TEXT_CPS
            except Exception:
                pass
        renpy.restart_interaction()

    # ---------- 颜色 ----------

    def settings_hex_to_hsv(value):
        value = str(value or "#ffffff").strip()
        if value.startswith("#"):
            value = value[1:]
        if len(value) == 3:
            value = "".join(c * 2 for c in value)
        try:
            r = int(value[0:2], 16) / 255.0
            g = int(value[2:4], 16) / 255.0
            b = int(value[4:6], 16) / 255.0
        except Exception:
            r, g, b = 1.0, 1.0, 1.0
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        return h, s, v

    def settings_hsv_to_hex(h, s, v):
        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        return "#%02x%02x%02x" % (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))

    def settings_load_color():
        key = getattr(store, "settings_sel_color", "GALGAME_TEXTBOX_COLOR")
        if key not in [k for k, _ in SETTINGS_COLOR_TARGETS]:
            key = "GALGAME_TEXTBOX_COLOR"
        store.settings_sel_color = key
        h, s, v = settings_hex_to_hsv(settings_value(key, "#ffffff"))
        store.settings_h = h
        store.settings_s = s
        store.settings_v = v
        store.sv_color_v = int(round(v * 100))
        store.sv_hue = int(round(h * 360))
        store.sv_sat = int(round(s * 100))
        store.settings_hex = settings_hsv_to_hex(h, s, v)
        store.settings_hue_bar = h

    def settings_pick_color(key):
        store.settings_sel_color = key
        settings_load_color()
        settings_make_picker()
        renpy.restart_interaction()

    def settings_color_apply():
        v = settings_clamp(int(getattr(store, "sv_color_v", 100)), 0, 100) / 100.0
        store.settings_v = v
        hexv = settings_hsv_to_hex(store.settings_h, store.settings_s, v)
        store.settings_hex = hexv
        settings_set(store.settings_sel_color, hexv, refresh=False)
        renpy.restart_interaction()

    def settings_brightness_changed():
        settings_color_apply()

    def settings_hsv_changed():
        store.settings_h = settings_clamp(int(getattr(store, "sv_hue", 0)), 0, 360) / 360.0
        store.settings_s = settings_clamp(int(getattr(store, "sv_sat", 0)), 0, 100) / 100.0
        settings_color_apply()
        renpy.restart_interaction()

    def settings_open_color_picker():
        store.settings_picker = ColorPicker(
            300, 300,
            settings_value(store.settings_sel_color, "#ffffff"),
            mouseup_callback=settings_picker_commit,
        )
        renpy.show_screen("settings_color_picker")

    def settings_picker_commit(picker):
        try:
            hexv = picker.color.hexcode
        except Exception:
            r, g, b = picker.color.rgb[:3]
            hexv = "#%02x%02x%02x" % (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))
        settings_set(store.settings_sel_color, hexv, refresh=False)
        settings_load_color()
        renpy.restart_interaction()

    def settings_picker_hue_apply(value=None):
        picker = getattr(store, "settings_picker", None)
        if picker is None:
            return
        if value is None:
            try:
                value = picker.hue_rotation
            except Exception:
                value = getattr(store, "settings_hue_bar", 0.0)
        try:
            picker.hue_rotation = float(value)
            store.settings_hue_bar = float(value)
            h, s, v = picker.color.hsv
        except Exception:
            return
        store.settings_h = h
        store.settings_s = s
        store.settings_v = v
        store.settings_hex = settings_hsv_to_hex(h, s, v)
        settings_set(store.settings_sel_color, store.settings_hex, refresh=False)
        renpy.restart_interaction()

    def settings_make_picker():
        try:
            store.settings_picker = ColorPicker(
                240, 240,
                settings_value(store.settings_sel_color, "#ffffff"),
                mouseup_callback=settings_picker_commit,
            )
        except Exception:
            store.settings_picker = None

    def _textbox_image():
        """作者放了 picture/ui/dialogue.png 就用它，否则用内置对话栏底图。"""
        try:
            if os.path.exists(os.path.join(config.basedir, "game", "picture", "ui", "dialogue.png")):
                return Image("picture/ui/dialogue.png", xalign=0.5, yalign=1.0)
        except Exception:
            pass
        # An existing player palette may require the original dark base.
        if (text_unread_color().lower() == OPTIONS_DEFAULTS["GALGAME_TEXT_UNREAD_COLOR"]
                and text_read_color().lower() == OPTIONS_DEFAULTS["GALGAME_TEXT_READ_COLOR"]):
            return Solid(gal_ui_panel)
        return Image("gui/textbox.png", xalign=0.5, yalign=1.0)

    def textbox_background_color(color, width, height):
        alpha = textbox_alpha()
        box = Transform(_textbox_image(), xysize=(width, height), alpha=alpha)
        if str(color).lower() in ("#ffffff", "#fff"):
            return box
        layer = Transform(Solid(color, xysize=(width, height)), alpha=0.35 * alpha)
        return Fixed(box, layer, xysize=(width, height))

    def textbox_background_preview(color, opacity, width, height):
        alpha = settings_clamp(int(opacity), 0, 100) / 100.0
        box = Transform(_textbox_image(), xysize=(width, height), alpha=alpha)
        if str(color).lower() in ("#ffffff", "#fff"):
            return box
        layer = Transform(Solid(color, xysize=(width, height)), alpha=0.35 * alpha)
        return Fixed(box, layer, xysize=(width, height))

    def settings_preview(st, at, picker=None):
        cur = picker.color.hexcode if picker is not None else settings_hex
        sel = store.settings_sel_color
        if sel == "GALGAME_TEXTBOX_COLOR":
            box = cur
        elif sel == "GALGAME_VIEWPOINT_COLOR":
            box = cur
        else:
            box = settings_value("GALGAME_TEXTBOX_COLOR", "#fffcf6")
        if sel == "GALGAME_TEXT_READ_COLOR":
            txt = cur
        elif sel == "GALGAME_TEXT_UNREAD_COLOR":
            txt = cur
        else:
            txt = settings_value("GALGAME_TEXT_UNREAD_COLOR", OPTIONS_DEFAULTS["GALGAME_TEXT_UNREAD_COLOR"])
        bg = textbox_background_color(box, 360, 120)
        label = Text("abc，你好", font=settings_font_path(), size=20, color=txt, xpos=24, ypos=26)
        return Fixed(bg, label, xysize=(360, 120)), 0.05

    def settings_reset_colors():
        settings_set("GALGAME_TEXTBOX_COLOR", OPTIONS_DEFAULTS.get("GALGAME_TEXTBOX_COLOR", "#fffcf6"), refresh=False)
        settings_set("GALGAME_VIEWPOINT_COLOR", OPTIONS_DEFAULTS.get("GALGAME_VIEWPOINT_COLOR", "#f5dfb6"), refresh=False)
        settings_set("GALGAME_TEXT_UNREAD_COLOR", OPTIONS_DEFAULTS.get("GALGAME_TEXT_UNREAD_COLOR", "#242a32"), refresh=False)
        settings_set("GALGAME_TEXT_READ_COLOR", OPTIONS_DEFAULTS.get("GALGAME_TEXT_READ_COLOR", "#525a64"), refresh=False)
        settings_load_color()
        settings_make_picker()
        renpy.restart_interaction()

    # ---------- 文本效果 ----------

    def textbox_alpha():
        return settings_clamp(settings_int("GALGAME_TEXTBOX_OPACITY", 100), 0, 100) / 100.0

    def textbox_tint():
        return settings_value("GALGAME_TEXTBOX_COLOR", "#ffffff")

    def text_unread_color():
        return settings_value("GALGAME_TEXT_UNREAD_COLOR", OPTIONS_DEFAULTS["GALGAME_TEXT_UNREAD_COLOR"])

    def text_read_color():
        return settings_value("GALGAME_TEXT_READ_COLOR", OPTIONS_DEFAULTS["GALGAME_TEXT_READ_COLOR"])

    def textbox_background(width=None, height=None, color=None):
        alpha = textbox_alpha()
        tint = color or textbox_tint()
        w = width or 1280
        h = height or 185
        box = _textbox_image()
        base = Transform(box, xysize=(w, h), alpha=alpha) if width else Transform(box, alpha=alpha)
        if str(tint).lower() not in ("#ffffff", "#fff"):
            # 深色对话框上直接乘色几乎看不出来，改成半透明色层覆盖
            layer = Transform(Solid(tint, xysize=(w, h)), alpha=0.35 * alpha)
            return Fixed(base, layer, xysize=(w, h))
        return base

    def _line_key(rec, text, run_id=None):
        import hashlib
        identity = [rec.get("turn"), list(rec.get("path") or []),
                    rec.get("character") or rec.get("speaker"), text]
        if run_id:
            identity.insert(0, run_id)
        payload = json.dumps(identity, ensure_ascii=False).encode("utf-8")
        return "gal_record:" + hashlib.sha256(payload).hexdigest()

    def line_is_read(rec, text, run_id=None):
        """只查询这句是否读过，不推进已读状态，供快进闸门使用。
        用官方 seen_label/mark_label_seen 存已读，避免自己维护一套持久化集合。"""
        key = _line_key(rec, text, run_id)
        try:
            return bool(renpy.seen_label(key))
        except Exception:
            seen = getattr(persistent, "gal_read_hashes", None)
            return bool(seen and key in seen)

    def skip_read_gate():
        """关闭「未读文本快进」时，遇到没读过的台词立刻停掉快进。"""
        try:
            if (renpy.config.skipping
                    and not preferences.skip_unseen
                    and not getattr(store, "_cur_line_seen", True)):
                renpy.config.skipping = None
                store._skipping = False
        except Exception:
            pass

    def line_mark_read(rec, text, run_id=None):
        """提交已经完成显示的剧情拍。"""
        key = _line_key(rec, text, run_id)
        try:
            renpy.mark_label_seen(key)
        except Exception:
            seen = getattr(persistent, "gal_read_hashes", None)
            if not isinstance(seen, set):
                seen = set(seen or [])
            seen = set(seen)
            seen.add(key)
            if len(seen) > 8000:
                seen = set(list(seen)[-4000:])
            persistent.gal_read_hashes = seen


    # ---------- 音频 ----------

    def apply_audio_settings():
        master = settings_clamp(settings_int("GALGAME_VOL_MASTER", 100), 0, 100) / 100.0
        bgm = settings_clamp(settings_int("GALGAME_VOL_BGM", 100), 0, 100) / 100.0
        sfx = settings_clamp(settings_int("GALGAME_VOL_SFX", 100), 0, 100) / 100.0
        voice = settings_clamp(settings_int("GALGAME_VOL_VOICE", 100), 0, 100) / 100.0
        try:
            preferences.music_volume = master * bgm
            preferences.sfx_volume = master * sfx
            preferences.voice_volume = master * voice
        except Exception:
            pass
        renpy.run(SetMute(["main", "music", "sfx", "voice"], settings_value("GALGAME_ALL_MUTE", "0") in ("1", "true", "yes", "on")))
        if not getattr(store, "_voice_ducked", False):
            try:
                # 频道音量是相对倍率，基础音量由 preferences 控制
                renpy.music.set_volume(1.0, delay=0.1, channel="music")
            except Exception:
                pass

    PLAYER_STYLE_TEXT_BASES = {
        "say_dialogue": gui.text_size, "say_label": gui.name_text_size,
        "gui_text": gui.interface_text_size, "button_text": gui.button_text_size,
        "choice_button_text": gui.choice_button_text_size,
        "navigation_button_text": gui.button_text_size,
        "navigation_button_light_text": gui.button_text_size,
        "set_tab_text": 18, "set_opt_text": 15, "set_label": 16,
        "set_note": 12, "set_header_text": 18, "set_primary_text": 17,
        "set_dialog_button_text": 16, "qbar_button_text": 15,
        "hist_close_text": 20, "hist_return_text": 15,
        "clip_field": 18, "clip_secret": 18,
        "clip_field_light": 18, "clip_secret_light": 18,
    }

    def player_text_size(base):
        percent = settings_clamp(settings_int("GALGAME_TEXT_SCALE", 100), 90, 115)
        return max(1, int(round(float(base) * percent / 100.0)))

    def apply_text_scale():
        for name, base in PLAYER_STYLE_TEXT_BASES.items():
            getattr(style, name).size = player_text_size(base)
        renpy.style.rebuild()

    def apply_player_preferences():
        renpy.run(Preference("auto-forward time", settings_clamp(settings_int("GALGAME_AFM_TIME", 15), 5, 30)))
        transitions = settings_value("GALGAME_TRANSITIONS", "1") in ("1", "true", "yes", "on")
        renpy.run(Preference("transitions", "all" if transitions else "none"))
        apply_audio_settings()
        apply_text_scale()

    def optional_title_music():
        value = settings_value("GALGAME_TITLE_MUSIC", "").strip().replace("\\", "/")
        if not value:
            return None
        suffix = os.path.splitext(value)[1].lower()
        if (value.startswith("/") or ":" in value or ".." in value.split("/")
                or suffix not in (".ogg", ".opus", ".mp3", ".mp2", ".wav", ".flac")
                or not renpy.loadable(value)):
            _debug("title music unavailable: %s" % value)
            return None
        return value

    def voice_duck_start():
        try:
            bgm = settings_clamp(settings_int("GALGAME_VOL_BGM", 100), 0, 100) / 100.0
            talk = settings_clamp(settings_int("GALGAME_VOL_BGM_TALK", 60), 0, 100) / 100.0
            relative = min(1.0, talk / bgm) if bgm > 0.01 else 0.0
            renpy.music.set_volume(relative, delay=0.25, channel="music")
            store._voice_ducked = True
        except Exception:
            pass

    def voice_duck_stop():
        if not getattr(store, "_voice_ducked", False):
            return
        try:
            renpy.music.set_volume(1.0, delay=0.4, channel="music")
            store._voice_ducked = False
        except Exception:
            pass

    def voice_duck_tick():
        try:
            if getattr(store, "_voice_ducked", False) and not renpy.sound.get_playing("voice"):
                voice_duck_stop()
        except Exception:
            pass

    # ---------- 画面 ----------

    def apply_on_top():
        on = settings_value("GALGAME_ALWAYS_ON_TOP", "0") in ("1", "true", "yes", "on")
        try:
            import ctypes
            import pygame
            hwnd = pygame.display.get_wm_info().get("window")
            if hwnd:
                HWND_TOPMOST = -1
                HWND_NOTOPMOST = -2
                flags = 0x0001 | 0x0002
                ctypes.windll.user32.SetWindowPos(int(hwnd), HWND_TOPMOST if on else HWND_NOTOPMOST, 0, 0, 0, 0, flags)
        except Exception as exc:
            try:
                _debug("on top fail %s" % exc)
            except Exception:
                pass

    def apply_display_settings():
        mode = settings_value("GALGAME_DISPLAY_MODE", "window")
        try:
            preferences.fullscreen = (mode == "fullscreen")
        except Exception:
            pass
        if mode != "fullscreen":
            aspect = settings_value("GALGAME_ASPECT", "16:9")
            size = (960, 720) if aspect == "4:3" else (1280, 720)
            try:
                renpy.set_physical_size(size)
            except Exception:
                pass
        apply_on_top()

    # ---------- 游戏设置 ----------

    def apply_game_settings():
        try:
            skip_read = settings_value("GALGAME_SKIP_READ", "1") in ("1", "true", "yes", "on")
            skip_unseen = settings_value("GALGAME_SKIP_UNSEEN", "0") in ("1", "true", "yes", "on")
            ctrl_all = settings_value("GALGAME_CTRL_SKIP", "read") == "all"
            # 「自动跳过已读文本」只控制自动模式；不能拿它来放开未读快进
            preferences.skip_unseen = skip_unseen or ctrl_all
            preferences.skip_after_choices = settings_value("GALGAME_SKIP_AFTER_CHOICE", "0") in ("1", "true", "yes", "on")
        except Exception:
            pass
        seconds = settings_int("GALGAME_MOUSE_HIDE", 0)
        try:
            config.mouse_hide_time = seconds if seconds > 0 else None
        except Exception:
            pass

    def settings_apply_game():
        apply_game_settings()

    def choice_auto_handle():
        # 选择后是否解除自动模式
        if settings_value("GALGAME_AUTO_AFTER_CHOICE", "0") == "0":
            try:
                preferences.afm_enable = False
            except Exception:
                pass

    # ---------- 字体 ----------

    def settings_cycle_font():
        choices = font_choices()
        if not choices:
            return
        cur = settings_value("GALGAME_FONT", "SourceHanSansLite.ttf")
        try:
            idx = choices.index(cur)
        except ValueError:
            idx = -1
        store.settings_font = choices[(idx + 1) % len(choices)]
        settings_set("GALGAME_FONT", store.settings_font)

    def settings_font_path():
        name = getattr(store, "settings_font", None) or settings_value("GALGAME_FONT", "")
        if not name:
            name = "SourceHanSansLite.ttf"
        return "fonts/" + name

    def apply_font_live():
        # The committed configuration also wins when a restart request is cancelled.
        store.settings_font = font_pick(settings_value("GALGAME_FONT", FONT_DEFAULT))
        apply_font_path(settings_font_path())

    def settings_font_display():
        val = settings_value("GALGAME_FONT", "")
        if not val:
            return "默认"
        if val.startswith("local/"):
            return val.split("/", 1)[1]
        return val

    def settings_font_options():
        opts = []
        fonts_dir = os.path.join(config.basedir, "game", "fonts")
        if os.path.isdir(fonts_dir):
            for name in sorted(os.listdir(fonts_dir)):
                if name.lower().endswith((".ttf", ".otf")):
                    opts.append((name, name))
        local_dir = os.path.join(fonts_dir, "local")
        if os.path.isdir(local_dir):
            for name in sorted(os.listdir(local_dir)):
                if name.lower().endswith((".ttf", ".otf")):
                    opts.append(("已导入 - " + name, "local/" + name))
        sys_dirs = ["C:/Windows/Fonts"]
        appdata = os.environ.get("LOCALAPPDATA")
        if appdata:
            sys_dirs.append(os.path.join(appdata, "Microsoft", "Windows", "Fonts"))
        seen = set()
        for folder in sys_dirs:
            if not os.path.isdir(folder):
                continue
            for name in sorted(os.listdir(folder)):
                if not name.lower().endswith((".ttf", ".otf")):
                    continue
                low = name.lower()
                if low in seen:
                    continue
                seen.add(low)
                opts.append((name + " - 系统", os.path.join(folder, name)))
        return opts

    def settings_open_font_picker():
        store.settings_font_list = settings_font_options()
        renpy.show_screen("settings_font_picker")

    def settings_pick_font(value):
        if os.path.isabs(value):
            try:
                local_dir = os.path.join(config.basedir, "game", "fonts", "local")
                os.makedirs(local_dir, exist_ok=True)
                name = "sys_" + os.path.basename(value)
                dest = os.path.join(local_dir, name)
                if not os.path.exists(dest):
                    shutil.copy2(value, dest)
                value = "local/" + name
            except Exception:
                renpy.notify("字体导入失败")
                return
        store.settings_font = value
        settings_set("GALGAME_FONT", value)
        renpy.hide_screen("settings_font_picker")

    # ---------- 键盘 ----------

    KEY_DISPLAY = {
        "return": "Enter",
        "space": "Space",
        "backspace": "Backspace",
        "delete": "Delete",
        "page up": "PageUp",
        "page down": "PageDown",
        "left ctrl": "Ctrl",
        "right ctrl": "Ctrl",
        "ctrl": "Ctrl",
        "tab": "Tab",
        "escape": "Escape",
        "left shift": "Shift",
        "right shift": "Shift",
        "left alt": "Alt",
        "right alt": "Alt",
    }

    SETTINGS_KEY_LIMITS = {
        "GALGAME_KEY_ADVANCE": ["Enter", "Space"],
        "GALGAME_KEY_CTRL": ["Ctrl"],
        "GALGAME_KEY_HISTORY_PREV": ["PageUp"],
        "GALGAME_KEY_HISTORY_NEXT": ["PageDown"],
        "GALGAME_KEY_BACK": ["Backspace"],
    }

    CAPTURE_KEYS = [("K_" + c, c.upper()) for c in "abcdefghijklmnopqrstuvwxyz"]
    CAPTURE_KEYS += [("K_%d" % d, str(d)) for d in range(10)]
    CAPTURE_KEYS += [("K_F%d" % i, "F%d" % i) for i in range(1, 13)]
    CAPTURE_KEYS += [
        ("K_RETURN", "Enter"), ("K_SPACE", "Space"), ("K_BACKSPACE", "Backspace"),
        ("K_DELETE", "Delete"), ("K_PAGEUP", "PageUp"), ("K_PAGEDOWN", "PageDown"),
        ("K_TAB", "Tab"), ("K_INSERT", "Insert"), ("K_HOME", "Home"), ("K_END", "End"),
        ("K_LEFT", "Left"), ("K_RIGHT", "Right"), ("K_UP", "Up"), ("K_DOWN", "Down"),
        ("K_MINUS", "-"), ("K_EQUALS", "="), ("K_LEFTBRACKET", "["), ("K_RIGHTBRACKET", "]"),
        ("K_SEMICOLON", ";"), ("K_QUOTE", "'"), ("K_COMMA", ","), ("K_PERIOD", "."),
        ("K_SLASH", "/"), ("K_BACKSLASH", "\\"), ("K_BACKQUOTE", "`"),
        ("K_LCTRL", "Ctrl"), ("K_RCTRL", "Ctrl"), ("K_LSHIFT", "Shift"),
        ("K_RSHIFT", "Shift"), ("K_LALT", "Alt"), ("K_RALT", "Alt"),
    ]

    def key_display_name(name):
        low = str(name or "").lower()
        if low in KEY_DISPLAY:
            return KEY_DISPLAY[low]
        if len(low) == 1:
            return low.upper()
        return low.capitalize()

    def key_capture_start(key):
        store.key_capture_target = key
        store.key_capture_down = []
        store.key_capture_all = []
        store.key_capture_text = ""
        store.key_capture_hint = ""
        renpy.show_screen("key_capture")

    def key_capture_cancel():
        store.key_capture_target = ""
        store.key_capture_down = []
        store.key_capture_all = []
        renpy.hide_screen("key_capture")

    def key_capture_key(display):
        if display == "Escape":
            key_capture_cancel()
            return
        down = getattr(store, "key_capture_down", [])
        allkeys = getattr(store, "key_capture_all", [])
        if display not in down:
            down = down + [display]
            store.key_capture_down = down
            if display not in allkeys:
                allkeys = allkeys + [display]
                store.key_capture_all = allkeys
            store.key_capture_text = " + ".join(down)
            store.key_capture_hint = ""
            renpy.restart_interaction()

    def key_capture_commit_pending():
        allkeys = list(getattr(store, "key_capture_all", []))
        if not allkeys:
            return
        store.key_capture_down = []
        store.key_capture_all = []
        key_capture_commit(allkeys)

    def key_capture_commit(keys):
        target = getattr(store, "key_capture_target", "")
        if not target or not keys:
            return
        keys = [key_display_name(k) for k in keys]
        if target != "GALGAME_KEY_ADVANCE" and any(k in ("Enter", "Space") for k in keys):
            store.key_capture_hint = "Enter 和 Space 保留给「下一句」"
            store.key_capture_down = []
            store.key_capture_text = ""
            renpy.restart_interaction()
            return
        limits = SETTINGS_KEY_LIMITS.get(target)
        if limits and (len(keys) != 1 or keys[0] not in limits):
            store.key_capture_hint = "这一项只能绑定 " + " 或 ".join(limits)
            store.key_capture_down = []
            store.key_capture_text = ""
            renpy.restart_interaction()
            return
        settings_set(target, "+".join(keys))
        key_capture_cancel()
        renpy.notify("快捷键已更新")

    def key_capture_names():
        return [key_display_name(k) for k in getattr(store, "key_capture_down", [])]

    def settings_key_label(key):
        return settings_value(key, "").replace("+", " + ")

    def settings_key_conflicts():
        combos = {}
        counts = {}
        for key, _label in SETTINGS_KEYS:
            if key in ("GALGAME_KEY_ADVANCE", "GALGAME_KEY_CTRL"):
                continue  # 这两个交给原生 dismiss / skip
            combo = _key_combo(settings_value(key, ""))
            combos[key] = combo
            if combo:
                counts[combo] = counts.get(combo, 0) + 1
        return set(key for key, combo in combos.items() if combo and counts.get(combo, 0) > 1)

    # ---------- 高级分组 ----------

    def settings_advanced_display(item):
        key = item["key"]
        val = settings_value(key)
        if "KEY" in key:
            return "已填写" if val else "未填写"
        if not val:
            return "（空）"
        flat = val.replace(chr(10), " ")
        return flat if len(flat) <= 46 else flat[:46] + "…"

    def settings_advanced_set(key, value):
        settings_set(key, value, refresh=False)
        if key == "GALGAME_VOICE_API":
            settings_voice_api_changed(value)
        try:
            apply_live_options()
        except Exception:
            pass
        renpy.restart_interaction()

    def settings_voice_api_changed(value):
        """切换语音协议时，把明显不匹配的端点和模型换成对应服务的默认值。"""
        if value in ("mimo", "openai_official"):
            model = "mimo-v2.5-tts" if value == "mimo" else "gpt-4o-mini-tts"
            settings_set("GALGAME_VOICE_MODEL", model, refresh=False)
            return
        if value == "other":
            return
        if value == "openai":
            if not settings_value("GALGAME_VOICE_ENDPOINT", ""):
                chat = settings_value("GALGAME_ENDPOINT", "")
                if chat:
                    if "/chat/completions" in chat:
                        ep = chat.replace("/chat/completions", "/audio/speech")
                    else:
                        ep = chat.rstrip("/") + "/audio/speech"
                    settings_set("GALGAME_VOICE_ENDPOINT", ep, refresh=False)
            model = settings_value("GALGAME_VOICE_MODEL", "")
            if (not model) or model.startswith("qwen"):
                settings_set("GALGAME_VOICE_MODEL", "tts-1", refresh=False)
        else:
            model = settings_value("GALGAME_VOICE_MODEL", "")
            if (not model) or model in ("tts-1", "gpt-4o-mini-tts"):
                settings_set("GALGAME_VOICE_MODEL", "qwen3-tts-flash", refresh=False)

    def settings_edit_start(key):
        store.settings_edit_key = key
        store.settings_edit_value = settings_value(key)
        reset_text_state("settings_edit_value")
        set_text_focus("settings_edit_value")
        renpy.show_screen("settings_value_edit")

    def settings_apply_edit():
        key = getattr(store, "settings_edit_key", "")
        if not key:
            return
        settings_set(key, store.settings_edit_value, refresh=False)
        if key in [k for k, _label in SETTINGS_COLOR_TARGETS]:
            settings_load_color()
        try:
            apply_live_options()
        except Exception:
            pass
        renpy.hide_screen("settings_value_edit")
        renpy.restart_interaction()

    def settings_preview_props():
        sel = getattr(store, "settings_sel_color", "GALGAME_TEXTBOX_COLOR")
        cur = getattr(store, "settings_hex", "#242a32")
        if sel in ("GALGAME_TEXT_UNREAD_COLOR", "GALGAME_TEXT_READ_COLOR"):
            txt = cur
        else:
            txt = settings_value("GALGAME_TEXT_UNREAD_COLOR", "#242a32")
        return {"font": settings_font_path(), "size": player_text_size(20), "color": txt, "xmaximum": 312}

    class GalTypingPreview(renpy.Displayable):
        def __init__(self, cps, props):
            super(GalTypingPreview, self).__init__()
            self.cps = cps
            self.props = props
            self.sample = "abc，你好"
            self.period = len(self.sample) / float(cps) + 1.2 if cps else 0
            self.cycle = None
            self.child = None

        def render(self, width, height, st, at):
            cycle = int(st / self.period) if self.period else 0
            if cycle != self.cycle:
                self.cycle = cycle
                self.child = Text(self.sample, slow=bool(self.cps), slow_cps=self.cps, **self.props)
            elapsed = st - cycle * self.period
            if self.period:
                renpy.redraw(self, max(0.001, min(0.03, self.period - elapsed)))
            result = renpy.Render(width, height)
            result.place(self.child, st=elapsed, at=elapsed)
            return result

    # ---------- 快捷键 ----------

    def settings_toggle_fullscreen():
        mode = "fullscreen" if settings_value("GALGAME_DISPLAY_MODE", "window") == "window" else "window"
        settings_set("GALGAME_DISPLAY_MODE", mode)

    def _native_keymap(name):
        cache = getattr(store, "_native_keymap_cache", None)
        if cache is None:
            cache = {}
            store._native_keymap_cache = cache
        if name not in cache:
            cache[name] = list(config.keymap.get(name, []))
        return cache[name]

    _EDIT_DISMISS_KEYS = ("K_RETURN", "K_KP_ENTER", "K_SPACE")

    def edit_keys_begin():
        """编辑框打开期间暂停 dismiss：回车/空格只用于输入或提交，不推进剧情。"""
        try:
            depth = int(getattr(store, "_edit_key_depth", 0)) + 1
            store._edit_key_depth = depth
            if depth == 1:
                store._edit_dismiss_saved = list(config.keymap.get("dismiss") or [])
                config.keymap["dismiss"] = [
                    k for k in store._edit_dismiss_saved if k not in _EDIT_DISMISS_KEYS
                ]
        except Exception:
            pass
        renpy.clear_keymap_cache()

    def edit_keys_end():
        try:
            depth = max(0, int(getattr(store, "_edit_key_depth", 1)) - 1)
            store._edit_key_depth = depth
            saved = getattr(store, "_edit_dismiss_saved", None)
            if depth == 0 and saved is not None:
                config.keymap["dismiss"] = saved
                store._edit_dismiss_saved = None
        except Exception:
            pass
        renpy.clear_keymap_cache()

    def apply_keymap_settings():
        try:
            advance = settings_value("GALGAME_KEY_ADVANCE", "Enter")
            keep = ("K_SPACE",) if advance == "Space" else ("K_RETURN", "K_KP_ENTER", "K_SPACE")
            drop = ("K_RETURN", "K_KP_ENTER") if advance == "Space" else ()
            dismiss = [k for k in _native_keymap("dismiss") if k not in drop]
            for _k in ("mouseup_1",) + keep:
                if _k not in dismiss:
                    dismiss.append(_k)
            config.keymap["dismiss"] = dismiss
            combos = [_key_combo(settings_value(key, "")) for key, _label in SETTINGS_KEYS]
            combos = [c for c in combos if c]

            def uses(name, bare=False):
                for combo in combos:
                    if name in combo and (not bare or len(combo) == 1):
                        return True
                return False

            # 先恢复原生键，再只删掉确实被自定义快捷键占用的键。
            for name in ("toggle_fullscreen", "progress_screen", "self_voicing", "screenshot", "rollback", "rollforward"):
                config.keymap[name] = list(_native_keymap(name))
            if uses("f11"):
                config.keymap["toggle_fullscreen"] = [k for k in config.keymap["toggle_fullscreen"] if k != "K_F11"]
            if uses("f2"):
                config.keymap["progress_screen"] = [k for k in config.keymap["progress_screen"] if k != "K_F2"]
            if uses("v", True):
                config.keymap["self_voicing"] = [k for k in config.keymap["self_voicing"] if k.lower() != "k_v"]
            if uses("s", True):
                config.keymap["screenshot"] = [k for k in config.keymap["screenshot"] if k.lower() != "noshift_k_s"]
            if uses("pageup"):
                config.keymap["rollback"] = [k for k in config.keymap["rollback"] if "PAGEUP" not in k.upper()]
            if uses("pagedown"):
                config.keymap["rollforward"] = [k for k in config.keymap["rollforward"] if "PAGEDOWN" not in k.upper()]
        except Exception as exc:
            try:
                _debug("keymap apply fail %s" % exc)
            except Exception:
                pass
        renpy.clear_keymap_cache()

    def _key_combo(value):
        parts = [p.strip().lower().replace(" ", "") for p in str(value or "").split("+") if p.strip()]
        fixed = []
        for p in parts:
            if p in ("leftctrl", "rightctrl"):
                p = "ctrl"
            elif p in ("leftshift", "rightshift"):
                p = "shift"
            elif p in ("leftalt", "rightalt"):
                p = "alt"
            fixed.append(p)
        return tuple(sorted(set(fixed)))

    _KEYSYM_ALIAS = {
        "ENTER": "RETURN", "RETURN": "RETURN",
        "CTRL": "LCTRL", "SHIFT": "LSHIFT", "ALT": "LALT",
        "ESC": "ESCAPE", "ESCAPE": "ESCAPE", "SPACE": "SPACE",
        "DEL": "DELETE", "INS": "INSERT",
    }

    def screen_key(value):
        """把设置里的键名（PageUp / F8 / p）转成屏幕语言能用的 keysym（K_PAGEUP）。"""
        v = str(value or "").strip()
        if not v:
            return None
        if "+" in v:
            return None          # 屏幕 key 语句不支持组合键
        v = re.sub(r"[^0-9A-Za-z]", "", v).upper()
        v = _KEYSYM_ALIAS.get(v, v)
        return ("K_" + v) if v else None

    def _bindings():
        result = []
        for key, _label in SETTINGS_KEYS:
            if key in ("GALGAME_KEY_ADVANCE", "GALGAME_KEY_CTRL"):
                continue  # 这两个交给原生 dismiss / skip
            combo = _key_combo(settings_value(key, ""))
            if combo:
                result.append((combo, key))
        return result

    def history_page(delta):
        try:
            adj = store.hist_adj
            step = adj.page or 420
            low = 0
            high = max(0, (adj.range or 0) - step)
            adj.value = max(low, min(high, (adj.value or 0) + delta * step))
            renpy.restart_interaction()
        except Exception as exc:
            try:
                _debug("history page fail %s" % exc)
            except Exception:
                pass

    def gal_slot_ui_action(operation, slot):
        operation(slot)

    def slot_click_action(action, ident):
        if settings_value("GALGAME_SLOT_CLICK", "single") != "double":
            return action
        return Function(slot_double_click, ident, action)

    def slot_double_click(ident, action):
        now = time.time()
        if getattr(store, "_slot_click_id", None) == ident and now - getattr(store, "_slot_click_t", 0) < 0.45:
            store._slot_click_id = None
            renpy.run(action)
        else:
            store._slot_click_id = ident
            store._slot_click_t = now
            renpy.notify("再点一次确认")

    def run_key_action(key):
        import pygame
        in_main = bool(getattr(store, "main_menu", False))
        if in_main and key not in ("GALGAME_KEY_SETTINGS", "GALGAME_KEY_FULLSCREEN", "GALGAME_KEY_SELF_VOICE"):
            return
        if key == "GALGAME_KEY_SAVE":
            capture_pending_thumb()
            renpy.show_screen("ai_slots", mode="save")
        elif key == "GALGAME_KEY_LOAD":
            renpy.show_screen("ai_slots", mode="load")
        elif key == "GALGAME_KEY_QSAVE":
            capture_pending_thumb()
            save_state("quick")
        elif key == "GALGAME_KEY_QLOAD":
            load_and_jump("quick")
        elif key == "GALGAME_KEY_SETTINGS":
            settings_open()
        elif key == "GALGAME_KEY_FULLSCREEN":
            settings_toggle_fullscreen()
        elif key == "GALGAME_KEY_AUTO":
            renpy.run(Preference("auto-forward", "toggle"))
        elif key == "GALGAME_KEY_SKIP":
            renpy.run(Skip())
        elif key == "GALGAME_KEY_HISTORY":
            renpy.run(ShowMenu("history"))
        elif key == "GALGAME_KEY_BACK":
            renpy.run(Jump("ai_rewind"))
        elif key == "GALGAME_KEY_REWIND":
            renpy.run(Jump("ai_rewind_many"))
        elif key == "GALGAME_KEY_TITLE":
            renpy.run(MainMenu(confirm=True))
        elif key == "GALGAME_KEY_HIDE":
            hide_ui_keep_stage()
        elif key == "GALGAME_KEY_REPLAY":
            replay_voice()
        elif key == "GALGAME_KEY_SELF_VOICE":
            renpy.run(Preference("self voicing", "toggle"))
        elif key == "GALGAME_KEY_FAV":
            toggle_voice_fav()

    ROUTER_BLOCKED = (
        "key_capture", "input", "player_settings", "ai_option_edit", "slot_name_edit",
        "ai_settings", "ai_slots", "ai_confirm", "options_restart_confirm",
        "start_choice", "start_regen_confirm", "confirm", "voice_favorites", "_accessibility",
    )

    def router_blocked():
        for name in ROUTER_BLOCKED:
            if renpy.get_screen(name):
                return True
        return False

    def router_key_down(display):
        # 键盘事件走 Keymap 组件（不吞事件），这里只记录并按组合触发。
        if router_blocked():
            return
        now = time.time()
        down = [item for item in getattr(store, "_router_down", []) if now - item[1] < 1.2]
        down.append((display, now))
        store._router_down = down
        names = set()
        for name, _t in down:
            names.update(_key_combo(name))
        for combo, key in _bindings():
            if set(combo) <= names:
                store._router_down = []
                try:
                    run_key_action(key)
                except (renpy.game.JumpException, renpy.game.JumpOutException):
                    raise
                except Exception as exc:
                    try:
                        _debug("key action %s fail %s" % (key, exc))
                    except Exception:
                        pass
                return

    ROUTER_KEYMAP = dict((_k, Function(router_key_down, _d)) for _k, _d in CAPTURE_KEYS)
    ROUTER_WIDGET = renpy.display.behavior.Keymap(capture=False, **ROUTER_KEYMAP)

    # 启动时套用画面、音频、按键设置
    config.start_callbacks.append(apply_display_settings)
    config.start_callbacks.append(apply_audio_settings)
    config.start_callbacks.append(apply_game_settings)
    config.start_callbacks.append(apply_keymap_settings)
    config.periodic_callbacks.append(voice_duck_tick)
    try:
        config.start_interact_callbacks.append(skip_read_gate)
    except Exception:
        pass
    config.periodic_callbacks.append(_box_watchdog)

# ---------- 状态 ----------

default settings_tab = "display"
default settings_font = "SourceHanSansLite.ttf"
default settings_dirty = False
default settings_sel_color = "GALGAME_TEXTBOX_COLOR"
default settings_picker = None
default settings_font_list = []
default settings_edit_key = ""
default settings_edit_value = ""
default settings_h = 0.0
default settings_s = 0.0
default settings_v = 1.0
default settings_hex = "#ffffff"
default settings_hue_bar = 0.0
default sv_master = 100
default sv_bgm = 100
default sv_bgm_talk = 60
default sv_sfx = 100
default sv_voice = 100
default sv_opacity = 100
default sv_cps = text_cps_value()
default sv_afm = 15
default sv_text_scale = 100
default sv_color_v = 100
default sv_hue = 0
default sv_sat = 0
default key_capture_target = ""
default key_capture_down = []
default key_capture_all = []
default key_capture_text = ""
default key_capture_hint = ""
default _voice_ducked = False
default hist_adj = renpy.display.behavior.Adjustment()
default _slot_click_id = None
default _slot_click_t = 0.0
default _router_down = []


## 设置样式 ####################################################################

style settings_hue_bar is bar:
    xysize (240, 26)
    base_bar At(Transform("#000", xysize=(240, 26)), spectrum())
    thumb Transform("selector_bg", xysize=(18, 30))
    thumb_offset 9


## 设置主界面 ##################################################################

screen player_settings():
    predict False
    modal True
    zorder 1100
    add Solid(gal_ui_wash)

    frame:
        align (0.5, 0.5)
        xsize 1200
        ysize 672
        padding (0, 0)
        background gal_ui_skin_panel

        hbox:
            spacing 12

            # 左侧标签：玩家设置 + 全部分组设置
            frame:
                xsize 206
                yfill True
                padding (14, 22)
                background Solid(gal_ui_card)
                vbox:
                    spacing 2
                    text "设置" size player_text_size(26) color gal_ui_ink
                    null height 12
                    hbox:
                        spacing 4
                        xfill True
                        viewport:
                            id "settings_side_vp"
                            ysize 572
                            xfill True
                            mousewheel True
                            scrollbars None
                            vbox:
                                spacing 2
                                xfill True
                                for _tid, _tlabel in SETTINGS_TABS:
                                    textbutton _tlabel:
                                        style "set_tab"
                                        text_style "set_tab_text"
                                        action Function(settings_switch_tab, _tid)
                                        selected (settings_tab == _tid)
                        vbar:
                            value YScrollValue("settings_side_vp")
                            style "settings_vscroll"
                            ysize 572

            # 右侧内容
            frame:
                xfill True
                yfill True
                padding (30, 22)
                background None
                vbox:
                    spacing 12
                    $ _tab_title = SETTINGS_TITLES.get(settings_tab, "设置")
                    $ _layout = SETTINGS_LAYOUT_BY_ID.get(settings_tab)
                    fixed:
                        ysize 40
                        text _tab_title size player_text_size(22) color gal_ui_ink yalign 0.5
                        hbox:
                            xalign 1.0
                            yalign 0.5
                            spacing 22
                            textbutton "回到首页":
                                style "set_header_button"
                                text_style "set_header_text"
                                action Function(settings_go_home)
                            textbutton "关闭":
                                style "set_header_button"
                                text_style "set_header_text"
                                action Function(settings_close)

                    hbox:
                        spacing 6
                        xfill True
                        viewport:
                            id "settings_vp"
                            ysize 514
                            scrollbars None
                            mousewheel True
                            draggable (settings_tab != "text")
                            vbox:
                                spacing 16
                                xfill True
                                if settings_tab == "display":
                                    use settings_page_display
                                elif settings_tab == "game":
                                    use settings_page_game
                                elif settings_tab == "text":
                                    use settings_page_text
                                elif settings_tab == "audio":
                                    use settings_page_audio
                                elif settings_tab == "keys":
                                    use settings_page_keys
                                elif _layout and _layout.get("type") == "adv":
                                    use settings_page_advanced(_layout)
                        vbar:
                            value YScrollValue("settings_vp")
                            style "settings_vscroll"
                            ysize 514
                    hbox:
                        xalign 1.0
                        spacing 8
                        textbutton "保存设置":
                            style "set_opt"
                            text_style "set_opt_text"
                            action Function(settings_confirm, False)
                        textbutton "保存且退出设置":
                            style "set_primary"
                            text_style "set_primary_text"
                            action Function(settings_confirm)

    key "K_ESCAPE" action Function(settings_close)



screen settings_row(title, note=""):
    vbox:
        spacing 6
        text title style "set_label"
        if note:
            text note style "set_note"


screen settings_seg(label, key, opts):
    vbox:
        spacing 8
        text label style "set_label"
        hbox:
            spacing 8
            for _v, _l in opts:
                textbutton _l:
                    style "set_opt"
                    text_style "set_opt_text"
                    action Function(settings_set, key, _v)
                    selected (settings_value(key) == _v)


screen settings_switch(label, key):
    use settings_seg(label, key, [("1", "开启"), ("0", "关闭")])


screen settings_slider(label, key, var):
    vbox:
        spacing 6
        fixed:
            xsize 420
            ysize 22
            text label style "set_label"
            text str(getattr(store, var, 0)) size player_text_size(15) color gal_ui_accent xalign 1.0
        bar:
            value (StaticValue(getattr(store, var, 0), 100) if settings_env_locked(key) else VariableValue(var, 100, step=1, force_step=True, action=Function(settings_slider_commit, key, var)))
            style "settings_bar"
            xsize 420


## 画面显示 ####################################################################

screen settings_range_slider(label, key, var, low, high, suffix=""):
    vbox:
        spacing 6
        fixed:
            xsize 420
            ysize 26
            text label style "set_label"
            text (str(getattr(store, var, low)) + suffix) size player_text_size(15) color gal_ui_accent xalign 1.0
        bar:
            value (StaticValue(settings_clamp(settings_int(key, low), low, high) - low, high - low) if settings_env_locked(key) else VariableValue(var, high - low, offset=low, step=1, force_step=True, action=Function(settings_slider_commit, key, var)))
            style "settings_bar"
            xsize 420


screen settings_page_display():
    use settings_seg("显示模式", "GALGAME_DISPLAY_MODE", [("window", "窗口"), ("fullscreen", "全屏")])
    use settings_seg("画面比例", "GALGAME_ASPECT", [("16:9", "16:9"), ("4:3", "4:3")])


## 游戏设置 ####################################################################

screen settings_page_game():
    use settings_switch("场景转场", "GALGAME_TRANSITIONS")
    use settings_switch("自动跳过已读文本", "GALGAME_SKIP_READ")
    use settings_switch("未读文本快进", "GALGAME_SKIP_UNSEEN")
    use settings_seg("选择后的快进是否解除", "GALGAME_SKIP_AFTER_CHOICE", [("0", "解除"), ("1", "不解除")])
    use settings_seg("ctrl 键的快捷方式", "GALGAME_CTRL_SKIP", [("all", "快进所有"), ("read", "仅快进已读")])
    use settings_seg("选择后自动模式是否解除", "GALGAME_AUTO_AFTER_CHOICE", [("0", "解除"), ("1", "不解除")])
    use settings_seg("自动隐藏鼠标指针", "GALGAME_MOUSE_HIDE", [("0", "不隐藏"), ("5", "5 秒"), ("10", "10 秒"), ("20", "20 秒")])
    use settings_seg("存档、读档的鼠标操作", "GALGAME_SLOT_CLICK", [("single", "单击"), ("double", "双击")])


## 文本 ########################################################################

screen settings_page_text():
    # Native persistent preference remains the only self-voicing source of truth.
    # This preserves changes made through Ren'Py's accessibility menu and V key.
    vbox:
        spacing 8
        text "界面朗读（系统语音）" style "set_label"
        hbox:
            spacing 8
            textbutton "开启":
                style "set_opt"
                text_style "set_opt_text"
                action Preference("self voicing", "enable")
            textbutton "关闭":
                style "set_opt"
                text_style "set_opt_text"
                action Preference("self voicing", "disable")
        text "使用操作系统语音朗读界面与对白；新用户默认关闭。" style "set_note"
        textbutton "辅助功能":
            style "set_opt"
            text_style "set_opt_text"
            action Show("_accessibility")
    use settings_range_slider("字号", "GALGAME_TEXT_SCALE", "sv_text_scale", 90, 115, "%")
    use settings_range_slider("自动播放等待时间", "GALGAME_AFM_TIME", "sv_afm", 5, 30)
    text "单位：秒 / 250 字符；实际等待时间随文本长度变化。" style "set_note"
    use settings_slider("对话框不透明度", "GALGAME_TEXTBOX_OPACITY", "sv_opacity")

    hbox:
        spacing 18
        text "字体" style "set_label" yalign 0.5
        button:
            style "set_opt"
            action Function(settings_open_font_picker)
            text settings_font_display() style "set_opt_text" substitute False

    null height 4
    frame:
        background Solid(gal_ui_card)
        padding (18, 14)
        xfill True
        vbox:
            spacing 10
            text "颜色设置" size player_text_size(18) color gal_ui_accent
            hbox:
                spacing 10
                for _ck, _cl in SETTINGS_COLOR_TARGETS:
                    textbutton _cl:
                        style "set_opt"
                        text_style "set_opt_text"
                        action Function(settings_pick_color, _ck)
                        selected (settings_sel_color == _ck)

            hbox:
                spacing 16
                vbox:
                    spacing 10
                    if settings_picker:
                        if settings_env_locked(settings_sel_color):
                            add settings_picker.swatch(xsize=240, ysize=240)
                        else:
                            add settings_picker
                        bar:
                            value (StaticValue(settings_picker.hue_rotation, 1.0) if settings_env_locked(settings_sel_color) else FieldValue(settings_picker, "hue_rotation", 1.0, action=Function(settings_picker_hue_apply)))
                            style "settings_hue_bar"
                            xsize 240
                    else:
                        text "色盘加载中…" style "set_note"
                vbox:
                    spacing 10
                    xsize 112
                    if settings_picker:
                        add settings_picker.swatch(xsize=80, ysize=80)
                        add settings_picker.hexcode(style='set_note')
                    else:
                        frame:
                            xysize (80, 80)
                            background Solid(settings_hex)
                    textbutton "重置":
                        style "set_opt"
                        text_style "set_opt_text"
                        action Function(settings_reset_colors)
                vbox:
                    spacing 6
                    xsize 360
                    hbox:
                        frame:
                            background Solid(gal_ui_accent)
                            padding (8, 2)
                            text "预览" size player_text_size(11) color gal_ui_panel
                    $ _pv_sel = settings_sel_color
                    $ _pv_cur = settings_hex
                    $ _pv_box = _pv_cur if _pv_sel in ("GALGAME_TEXTBOX_COLOR", "GALGAME_VIEWPOINT_COLOR") else settings_value("GALGAME_TEXTBOX_COLOR", "#fffcf6")
                    $ _pv_txt = _pv_cur if _pv_sel in ("GALGAME_TEXT_UNREAD_COLOR", "GALGAME_TEXT_READ_COLOR") else settings_value("GALGAME_TEXT_UNREAD_COLOR", "#242a32")
                    frame:
                        xysize (360, 120)
                        padding (0, 0)
                        background textbox_background_preview(_pv_box, sv_opacity, 360, 120)
                        fixed:
                            xysize (312, 70)
                            xpos 24
                            ypos 22
                            add GalTypingPreview(sv_cps, settings_preview_props()) id "gal_settings_typing_preview"
                    fixed:
                        xsize 360
                        ysize 22
                        text "打字机速度" style "set_label"
                        text ("瞬显" if sv_cps == 0 else str(sv_cps)) size player_text_size(15) color gal_ui_accent xalign 1.0
                    bar:
                        value (StaticValue(sv_cps, 100) if settings_env_locked("GALGAME_TEXT_CPS") else VariableValue("sv_cps", 100, step=1, force_step=True, action=Function(settings_slider_commit, "GALGAME_TEXT_CPS", "sv_cps")))
                        style "settings_bar"
                        xsize 360


    for _group in SETTINGS_TEXT_GROUPS:
        $ _gt = _group[0]
        $ _keys = _group[1]
        null height 10
        if _gt:
            text _gt size player_text_size(14) color gal_ui_accent
        for _key in _keys:
            $ _item = OPTION_ITEM_MAP.get(_key)
            if _item:
                use settings_adv_row(_item)


## 音频 ########################################################################

screen settings_page_audio():
    use settings_switch("全部静音", "GALGAME_ALL_MUTE")
    $ _title_music_item = OPTION_ITEM_MAP.get("GALGAME_TITLE_MUSIC")
    if _title_music_item:
        use settings_adv_row(_title_music_item)
    for _key in SETTINGS_AUDIO_KEYS:
        $ _item = OPTION_ITEM_MAP.get(_key)
        if _item:
            use settings_adv_row(_item)

    null height 10
    use settings_slider("主音量", "GALGAME_VOL_MASTER", "sv_master")
    use settings_slider("BGM", "GALGAME_VOL_BGM", "sv_bgm")
    use settings_slider("BGM，角色说话时", "GALGAME_VOL_BGM_TALK", "sv_bgm_talk")
    use settings_slider("游戏音效", "GALGAME_VOL_SFX", "sv_sfx")
    use settings_slider("角色语音", "GALGAME_VOL_VOICE", "sv_voice")

    null height 10
    $ _item = OPTION_ITEM_MAP.get("GALGAME_BGM_MIN_STAY")
    if _item:
        use settings_adv_row(_item)


## 键盘 ########################################################################

screen settings_page_keys():
    text "点击某一项后，按下想要的键；组合键请同时按下、一起松开。" style "set_note"
    $ _conflicts = settings_key_conflicts()
    for _kk, _kl in SETTINGS_KEYS:
        $ _bad = _kk in _conflicts
        $ _hist_combo = _kk in ("GALGAME_KEY_HISTORY_PREV", "GALGAME_KEY_HISTORY_NEXT") and "+" in settings_value(_kk, "")
        hbox:
            xfill True
            spacing 12
            hbox:
                xsize 555
                yalign 0.5
                spacing 12
                text _kl style "set_label"
                if _bad:
                    text "按键冲突" size player_text_size(12) color gal_ui_error
                elif _hist_combo:
                    text "历史翻页不支持组合键，请绑单个键" size player_text_size(12) color gal_ui_error
            if _bad:
                frame:
                    xalign 1.0
                    yalign 0.5
                    background Solid(gal_ui_error)
                    padding (2, 2)
                    textbutton settings_key_label(_kk):
                        style "set_opt"
                        text_style "set_opt_text"
                        action Function(key_capture_start, _kk)
            else:
                textbutton settings_key_label(_kk):
                    style "set_opt"
                    text_style "set_opt_text"
                    xalign 1.0
                    yalign 0.5
                    action Function(key_capture_start, _kk)


## 高级分组 ####################################################################

screen settings_adv_row(item):
    $ _k = item["key"]
    $ _kind = item.get("kind", "text")
    $ _val = settings_value(_k)
    $ _locked = settings_env_locked(_k)
    $ _is_on = str(_val).lower() in ("1", "true", "yes", "on", "开")
    $ _desc = (item.get("desc") or "").strip()
    $ _title = SETTINGS_ADV_LABELS.get(_k) or (_desc.splitlines()[0] if _desc else _k)
    $ _choices = SETTINGS_ADV_CHOICES.get(_k)
    vbox:
        spacing 6
        vbox:
            xfill True
            spacing 8
            vbox:
                xmaximum 600
                spacing 2
                text _title size player_text_size(16) color gal_ui_ink
                hbox:
                    spacing 10
                    if _title != _k:
                        text _k size player_text_size(11) color gal_ui_muted
                    if item.get("restart"):
                        text "需重启" size player_text_size(11) color gal_ui_accent
                    if _locked:
                        text "环境变量控制" size player_text_size(11) color gal_ui_accent
            if _choices:
                hbox:
                    xalign 1.0
                    yalign 0.5
                    spacing 8
                    for _cv, _cl in _choices:
                        textbutton _cl:
                            style "set_opt"
                            text_style "set_opt_text"
                            action Function(settings_advanced_set, _k, _cv)
                            sensitive (not _locked)
                            selected (_val == _cv)
            elif _kind == "switch" or _k in SETTINGS_FORCE_SWITCH:
                hbox:
                    xalign 1.0
                    yalign 0.5
                    spacing 8
                    textbutton "开启":
                        style "set_opt"
                        text_style "set_opt_text"
                        action Function(settings_advanced_set, _k, "1")
                        sensitive (not _locked)
                        selected _is_on
                    textbutton "关闭":
                        style "set_opt"
                        text_style "set_opt_text"
                        action Function(settings_advanced_set, _k, "0")
                        sensitive (not _locked)
                        selected (not _is_on)
            else:
                textbutton settings_advanced_display(item):
                    style "set_opt"
                    text_style "set_opt_text"
                    xalign 1.0
                    yalign 0.5
                    action Function(settings_edit_start, _k)
                    sensitive (not _locked)
        frame:
            ysize 1
            xfill True
            background Solid(gal_ui_divider)


screen settings_page_advanced(sec):
    for _group in (sec.get("groups") or []):
        $ _gt = _group[0]
        $ _keys = _group[1]
        if _gt:
            text _gt size player_text_size(14) color gal_ui_accent
            null height 2
        for _key in _keys:
            $ _item = OPTION_ITEM_MAP.get(_key)
            if _item and (_key != "GALGAME_VOICE_ENDPOINT" or settings_value("GALGAME_VOICE_API") in ("other", "openai", "")):
                use settings_adv_row(_item)
        null height 8


screen settings_value_edit():
    on "show" action Function(edit_keys_begin)
    on "hide" action [Function(reset_show_key), Function(reset_text_state, "settings_edit_value"), Function(edit_keys_end)]
    modal True
    zorder 1400
    add Solid(gal_ui_wash)
    frame:
        style "gal_ui_dialog"
        at (gal_ui_enter if settings_value("GALGAME_TRANSITIONS", "1") == "1" else gal_ui_still)
        xsize 880
        padding (32, 26)
        background gal_ui_skin_panel
        vbox:
            spacing 12
            $ _is_secret = "KEY" in (settings_edit_key or "")
            text settings_edit_key size player_text_size(16) color gal_ui_accent
            if _is_secret:
                text "密钥会写进同目录的 key.txt。" size player_text_size(12) color gal_ui_muted
            use clip_input("settings_edit_value", 620, _is_secret, 580, False, True)
            hbox:
                spacing 16
                button:
                    style "set_dialog_button_primary"
                    xysize (120, 40)
                    action Function(settings_apply_edit)
                    text "确定" style "set_dialog_button_primary_text" align (0.5, 0.5)
                button:
                    style "set_dialog_button"
                    xysize (120, 40)
                    action Hide("settings_value_edit")
                    text "取消" style "set_dialog_button_text" align (0.5, 0.5)
    key "K_RETURN" action Function(settings_apply_edit)
    key "K_ESCAPE" action Hide("settings_value_edit")


## 字体选择 ####################################################################

screen settings_font_picker():
    modal True
    zorder 1400
    add Solid(gal_ui_wash)
    frame:
        style "gal_ui_dialog"
        at (gal_ui_enter if settings_value("GALGAME_TRANSITIONS", "1") == "1" else gal_ui_still)
        xsize 760
        ysize 660
        padding (26, 22)
        background gal_ui_skin_panel
        vbox:
            spacing 12
            fixed:
                ysize 46
                text "字体选择" size player_text_size(22) color gal_ui_ink yalign 0.5
                textbutton "关闭":
                    style "set_header_button"
                    text_style "set_header_text"
                    action Hide("settings_font_picker")
                    xalign 1.0
                    yalign 0.5
            hbox:
                spacing 6
                xfill True
                viewport:
                    id "settings_font_vp"
                    ysize 540
                    xfill True
                    mousewheel True
                    scrollbars None
                    vbox:
                        spacing 2
                        for _label, _value in settings_font_list:
                            button:
                                style "set_tab"
                                action Function(settings_pick_font, _value)
                                text _label style "set_tab_text" substitute False
                vbar:
                    value YScrollValue("settings_font_vp")
                    style "settings_vscroll"
                    ysize 540


## 按键录入 ####################################################################

screen key_capture():
    modal True
    zorder 1300
    add Solid(gal_ui_wash)
    frame:
        style "gal_ui_dialog"
        at (gal_ui_enter if settings_value("GALGAME_TRANSITIONS", "1") == "1" else gal_ui_still)
        xsize 620
        padding (34, 28)
        background gal_ui_skin_panel
        vbox:
            spacing 14
            text "按下要设置的键" size player_text_size(22) color gal_ui_ink
            text (key_capture_text or "等待按键…") size player_text_size(32) color gal_ui_accent xalign 0.5
            if key_capture_hint:
                text key_capture_hint size player_text_size(14) color gal_ui_error
            text "组合键请同时按下；松开后生效。Esc 取消。" size player_text_size(13) color gal_ui_muted
            hbox:
                xalign 0.5
                textbutton "取消":
                    style "set_opt"
                    text_style "set_opt_text"
                    action Function(key_capture_cancel)
            if key_capture_down:
                timer 1.6 action Function(key_capture_commit_pending)
    for _ck, _cd in CAPTURE_KEYS:
        key _ck action Function(key_capture_key, _cd)
    key "K_ESCAPE" action Function(key_capture_cancel)



init 100 python:
    def _text_cps_startup():
        store.TEXT_CPS = text_cps_value(_cfg("GALGAME_TEXT_CPS"))
        config.default_text_cps = store.TEXT_CPS
        preferences.text_cps = store.TEXT_CPS

    config.start_callbacks.append(_text_cps_startup)

style set_tab is gal_ui_button:
    xfill True
    padding (14, 6)

style set_tab_text is gal_ui_button_text:
    size 17

style set_opt is gal_ui_button:
    padding (12, 6)

style set_opt_text is gal_ui_button_text:
    size 16

style set_label is text:
    size 18
    color gal_ui_ink

style set_note is text:
    size 14
    color gal_ui_muted

style set_rule is frame:
    background Solid(gal_ui_divider)
    ysize 1
    xfill True

style settings_bar is gal_ui_slider

style settings_vscroll is gal_ui_scroll

style set_header_button is gal_ui_button

style set_header_text is gal_ui_button_text

style set_primary is gal_ui_primary

style set_primary_text is gal_ui_primary_text

style set_dialog_button is gal_ui_button:
    xminimum 120

style set_dialog_button_text is gal_ui_button_text:
    text_align 0.5

style set_dialog_button_primary is gal_ui_primary:
    xminimum 120

style set_dialog_button_primary_text is gal_ui_primary_text:
    text_align 0.5

# Modified for GalGameFramework 1.7.4 (2026-11-10): use schema CPS defaults.
# Modified for GalGameFramework 1.7.2 (2026-11-10): restore route effects, music and pending reactions.
# Modified for GalGameFramework 1.7.2 (2026-11-09): descriptive speech labels for player controls.
# Modified for GalGameFramework 1.7.1 (2026-11-09): editable JSON slots and scaled player text.
# Modified for GalGameFramework 1.7.0 (2026-11-09): remove audited unused screens and transforms.
# Copyright 2026 ACE_yumoooo
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# galgame 框架 · 实时生成版
# Ren'Py 只负责渲染：文本、选项、每个选项的即时反应都由 ai.rpy 提供。
# 角色、场景、立绘全部来自 game/ 下的数据文件，这里不写死任何具体作品。

define narrator = Character(None, what_italic=False)

default ai_opt_sections = []
default ai_opt_flat = {}
default ai_opt_edit_key = ""
default ai_opt_edit_value = ""
default ai_opt_lock_ok = False
default ai_opt_dirty = False
default ai_show_key = False
default _text_states = {}
default _text_focus = ""

init -10 python:
    config.rollback_enabled = False
    config.has_autosave = False
    config.autosave_on_choice = False
    config.save_on_mobile_background = False

init 1 python:
    # 所有图片都在 game/picture/ 下：
    #   picture/scene/<time>_<place>.jpg          背景
    #   picture/standing/<角色名字>/<id>.webp     立绘，id 来自人物卡「立绘」表
    #   picture/ui/choice.png / dialogue.png / title.png   界面装饰，可选
    # 缺文件用占位，保证没有美术也能把流程跑完。老的 scene/、illustration/ 仍然兼容。
    _IMG_EXTS = (".jpg", ".jpeg", ".webp", ".png")
    _missing_art = []

    def _pic_dirs():
        game = os.path.join(config.basedir, "game")
        return [
            os.path.join(game, "picture", "scene"),
            os.path.join(game, "scene"),
        ]

    def _stand_dirs():
        game = os.path.join(config.basedir, "game")
        return [
            os.path.join(game, "picture", "standing"),
            os.path.join(game, "illustration"),
        ]

    def _find_in(dirs, sub, stem):
        for base in dirs:
            folder = os.path.join(base, sub) if sub else base
            for ext in _IMG_EXTS:
                if os.path.exists(os.path.join(folder, stem + ext)):
                    rel = os.path.relpath(os.path.join(folder, stem + ext), os.path.join(config.basedir, "game"))
                    return rel.replace(os.sep, "/")
        return None

    def _bg_placeholder(name):
        # 没美术时给一块深色底加提示，保证流程照跑。
        try:
            return Composite(
                (1280, 720),
                (0, 0), Solid("#0b1017", size=(1280, 720)),
                (48, 336), Text("缺少背景  picture/scene/" + name, size=26, color="#3f4c5c"),
            )
        except Exception:
            return Solid("#0b1017")

    def _register_images():
        for scene in SCENES:
            path = _find_in(_pic_dirs(), None, scene)
            if path:
                renpy.image("bg " + scene, Image(path))
            else:
                _missing_art.append("scene/" + scene)
                renpy.image("bg " + scene, _bg_placeholder(scene))

        # 立绘：每个角色用名字做目录，图片名就是人物卡里的 id
        for entry in _persona_entries():
            folder_name = entry.get("dir") or entry.get("name") or entry.get("id")
            ids = list((entry.get("standings") or {}).keys())
            for sid in ids:
                path = _find_in(_stand_dirs(), folder_name, sid)
                if not path and entry.get("illustration"):
                    path = _find_in(_stand_dirs(), entry["illustration"], sid)
                if path:
                    renpy.image("standing " + folder_name + " " + sid, Image(path))
                else:
                    _missing_art.append("standing/%s/%s" % (folder_name, sid))
                    renpy.image("standing " + folder_name + " " + sid, Null(width=460, height=980))
            # 人物卡没写立绘表时，按 MOODS 兜底
            if not ids:
                for sid in MOODS:
                    path = _find_in(_stand_dirs(), folder_name, sid)
                    if path:
                        renpy.image("standing " + folder_name + " " + sid, Image(path))
                    else:
                        _missing_art.append("standing/%s/%s" % (folder_name, sid))
                        renpy.image("standing " + folder_name + " " + sid, Null(width=460, height=980))

        # 目录里存在、但人物卡没登记的文件也注册上，方便手动放图
        for base in _stand_dirs():
            if not os.path.isdir(base):
                continue
            for name in os.listdir(base):
                folder = os.path.join(base, name)
                if not os.path.isdir(folder):
                    continue
                for fn in sorted(os.listdir(folder)):
                    stem, ext = os.path.splitext(fn)
                    if ext.lower() not in _IMG_EXTS:
                        continue
                    key = "standing " + name + " " + stem
                    if not renpy.image_exists(key, exact=True):
                        rel = os.path.relpath(os.path.join(folder, fn), os.path.join(config.basedir, "game"))
                        renpy.image(key, Image(rel.replace(os.sep, "/")))

    def _register_ui():
        """界面装饰：有图就用 Frame，没图保持默认样式。"""
        ui = os.path.join(config.basedir, "game", "picture", "ui")
        choice = os.path.join(ui, "choice.png")
        dialogue = os.path.join(ui, "dialogue.png")
        title = os.path.join(ui, "title.png")
        if os.path.exists(choice):
            try:
                style.choice_button.background = Frame("picture/ui/choice.png", 18, 18)
            except Exception as exc:
                _debug("choice 装饰失败 %s" % exc)
        if os.path.exists(dialogue):
            # 真正的对话栏底图由 settings.rpy 的 _textbox_image() 读取：
            # say 屏幕内联覆盖了 style.window.background，在这里设了也看不到。
            _debug("发现 picture/ui/dialogue.png，将用作对话栏底图")
        if os.path.exists(title):
            try:
                gui.main_menu_background = "picture/ui/title.png"
            except Exception as exc:
                _debug("title 装饰失败 %s" % exc)

    _register_images()
    _register_ui()
    if _missing_art:
        _debug("缺美术 %d 项，已用占位：%s" % (len(_missing_art), ", ".join(_missing_art[:12])))

transform heroine_pos:
    xpos 0.5
    xanchor 0.5
    yalign 0.0
    zoom 1.45

transform heroine_far:
    xpos 0.5
    xanchor 0.5
    yalign 0.0
    zoom 1.35

transform heroine_near:
    xpos 0.5
    xanchor 0.5
    yalign 0.0
    zoom 1.6

transform heroine_left:
    xpos 0.28
    xanchor 0.5
    yalign 0.0
    zoom 1.35

transform heroine_center:
    xpos 0.5
    xanchor 0.5
    yalign 0.0
    zoom 1.35

transform heroine_right:
    xpos 0.72
    xanchor 0.5
    yalign 0.0
    zoom 1.35

transform heroine_left3:
    xpos 0.2
    xanchor 0.5
    yalign 0.0
    zoom 1.0

transform heroine_center3:
    xpos 0.5
    xanchor 0.5
    yalign 0.0
    zoom 1.0

transform heroine_right3:
    xpos 0.8
    xanchor 0.5
    yalign 0.0
    zoom 1.0

label splashscreen:
    $ load_options_editor()
    $ apply_player_preferences()
    $ cleanup_tmp_leftovers()
    $ preload_all()
    $ ensure_ui_art()
    $ start_doctor()
    $ renpy.show_screen("stage_bg")
    $ renpy.show_screen("stage_hero")
    # 不在启动/回主菜单时预热：这时还没点开始或继续，发出去就是白花一次模型调用。
    # 预取改在 game_loading 的进度条里做，见 ai.rpy 的 _load_tick。
    if _on("GALGAME_AUTOSTART", "0"):
        jump start
    return

label start:
    $ renpy.store.gal_replay_cached_quick = False
    $ st = new_state()
    $ force_reinject(st)
    $ start_doctor()
    $ invalidate_background_boxes()
    $ clear_stage_cast()
    $ renpy.store._cur_scene = None
    $ renpy.store._cur_bgm = None
    $ renpy.store._dyn_bg = None
    $ renpy.music.stop(channel="music", fadeout=0.2)
    $ _opening = opening_records()
    # Keep the opening list length stable while loading appends generated beats.
    $ st["history"] = list(_opening)
    $ st["cursor"] = 0
    $ ensure_voice(st, _opening)
    $ save_history(st)
    $ load_begin("正在进入游戏", "正在生成剧情…", "start", 0.05)
    $ renpy.call_screen("game_loading")
    $ play_opening_records(st, len(_opening))
    jump ai_loop

label ai_resume:
    $ st = renpy.store._loaded
    $ saved_cursor = st.get("cursor", 0)
    $ force_reinject(st)
    $ prepare_resume(st)
    $ start_doctor()
    $ clear_stage_cast()
    $ renpy.store._cur_scene = None
    $ renpy.store._cur_bgm = None
    $ renpy.music.stop(channel="music", fadeout=0.3)
    $ restore_playback_state(st)
    $ save_history(st)
    $ saved_record = None
    if not st.get("_choice_reaction") and saved_cursor and st.get("cursor") == saved_cursor:
        $ saved_record = next((rec for rec in reversed(_history_records(st)) if rec.get("turn") == saved_cursor), None)
    $ load_begin("正在继续游戏", "正在读取存档…", "resume", 0.05, resume_record=saved_record)
    $ renpy.call_screen("game_loading")
    if st.get("_choice_reaction"):
        $ play_choice_reaction(st)
    elif saved_record is not None:
        $ play_record(saved_record, st)
        $ restore_playback_state(st)
    jump ai_loop

label ai_loop:
    while True:
        if st.get("ended"):
            $ renpy.show_screen("chapter_toast", text="结局 · " + st["ended"])
            $ renpy.pause(3.0, hard=False)
            $ renpy.full_restart()
        $ drain_prefetch(st)
        $ drain_detail(st)
        $ ensure_detail(st)
        $ drain_compress(st)
        $ ensure_compress(st)
        $ drain_chapter(st)
        $ ensure_chapter(st)
        $ roll_chapter(st)
        $ drain_diary()
        $ ensure_diary(st)
        $ drain_art()
        $ _rec = next_record(st)
        if not _rec:
            $ ensure_prefetch(st)
            $ _box = getattr(renpy.store, "_prefetch_box", None) or getattr(renpy.store, "_prefetch_busy_box", None)
            $ _next = take_prefetch(_box) if _box else None
            if _next:
                $ _added = append_batch(st, _next)
                if _added:
                    $ autosave()
                else:
                    $ invalidate_prefetch()
                    $ append_batch(st, error_batch("生成内容为空或全部重复"))
            else:
                $ invalidate_prefetch()
                $ append_batch(st, error_batch("生成超时，稍后再试"))
            $ _rec = next_record(st)
            if not _rec:
                $ renpy.pause(0.5, hard=False)
                $ _rec = next_record(st)
        if _rec:
            $ st["cursor"] = _rec["turn"]
            $ _boxes = None
            if _rec.get("choices") and _rec.get("chosen") is None:
                $ _stored = getattr(renpy.store, "_branch_boxes", None)
                if _stored and _stored[0] == list(_rec.get("path", [])) and _stored[2] == _rec["turn"]:
                    $ _boxes = _stored[1]
                else:
                    $ _boxes = start_branch_prefetch(st, _rec["choices"], _rec.get("path", []))
            else:
                if not _rec.get("ending"):
                    $ ensure_prefetch(st)
            $ play_record(_rec, st)
            if _rec.get("ending"):
                $ st["ended"] = _rec["ending"]
            if _rec.get("choices") and _rec.get("chosen") is None:
                if _boxes is None:
                    $ _boxes = start_branch_prefetch(st, _rec["choices"], _rec.get("path", []))
                $ _items = [(gal_literal_text(str((c.get("label") or c.get("hint") or "……")).strip() or "……"), i) for i, c in enumerate(_rec["choices"]) if hasattr(c, "get")]
                $ _idx = renpy.display_menu(_items)
                $ _cached = has_path(st, list(_rec.get("path") or []) + [_idx])
                if not _cached and any(i == _idx and not box.get("done") for i, box in _boxes):
                    $ renpy.notify("正在准备分支后续…")
                $ drain_branches(st, _boxes, _rec.get("path", []), not _cached, selected=_idx)
                $ commit_choice(st, _rec, _idx)
                $ play_choice_reaction(st)
                $ renpy.store._branch_boxes = None
                $ ensure_prefetch(st)
                $ save_history(st)
                $ save_state("auto", quiet=True, use_pending=False, thumb=True)
            elif _rec.get("choices") and _rec.get("chosen") is not None:
                $ st["path"] = list(_rec.get("path") or []) + [_rec["chosen"]]
            $ save_history(st)

label ai_rewind:
    $ rewind(st)
    $ clear_stage_cast()
    $ renpy.store._cur_scene = None
    $ renpy.store._cur_bgm = None
    $ renpy.music.stop(channel="music", fadeout=0.3)
    $ restore_playback_state(st)
    $ save_history(st)
    jump ai_loop

label ai_rewind_many:
    $ rewind_many(st, 5)
    $ clear_stage_cast()
    $ renpy.store._cur_scene = None
    $ renpy.store._cur_bgm = None
    $ renpy.music.stop(channel="music", fadeout=0.3)
    $ restore_playback_state(st)
    $ save_history(st)
    jump ai_loop

label ai_last_choice:
    $ _ok = jump_last_choice(st)
    if not _ok:
        $ renpy.notify("还没有可以回到的选择")
        jump ai_loop
    $ clear_stage_cast()
    $ renpy.store._cur_scene = None
    $ renpy.store._cur_bgm = None
    $ renpy.music.stop(channel="music", fadeout=0.3)
    $ restore_playback_state(st)
    $ save_history(st)
    jump ai_loop

label ai_history_jump:
    $ _ht = getattr(renpy.store, "_history_target", None)
    if _ht:
        $ restore_record(st, _ht)
        $ renpy.store._history_target = None
        $ invalidate_background_boxes()
        $ renpy.store._cur_scene = None
        $ renpy.store._cur_bgm = None
        $ clear_stage_cast()
        $ renpy.music.stop(channel="music", fadeout=0.3)
        $ restore_playback_state(st)
        $ save_history(st)
    jump ai_loop

style clip_field is input:
    color gal_ui_ink
    size 18
    layout "nobreak"

style clip_secret is clip_field:
    # Keep masked and visible keys at the same size so toggling visibility does
    # not change the field height or make the text appear clipped.
    size 18

style clip_field_light is input:
    color gal_ui_ink
    size 18
    layout "nobreak"

style clip_secret_light is clip_field_light:
    size 18

style text_scroll:
    ysize 6
    left_bar Solid(gal_ui_divider)
    right_bar Solid(gal_ui_divider)
    thumb Solid(gal_ui_accent)

style clip_input_viewport is viewport:
    xfill False
    yfill False

screen clip_input(var, maxlen=200, secret=False, width=500, eye=False, light=False):
    # secret 字段默认遮住，点眼睛显示；普通字段只有传了 eye 才显示眼睛，
    # 点了以后把当前值遮成星号，再点恢复。每个编辑框单独打开，互不影响。
    $ _eyed = bool(secret or eye)
    $ _show = bool(getattr(store, "ai_show_key", False))
    $ _hidden = (not _show) if secret else (_show if eye else False)
    $ _field_w = (width - 46) if _eyed else width
    $ _focused = getattr(store, "_text_focus", "") == var
    $ _adjustment = _text_adjustment(var)
    $ _ti = SelectableInput(
        var, var,
        length=maxlen,
        multiline=False,
        viewport_width=_field_w,
        scroll_adjustment=_adjustment,
        mask=("*" if _hidden else None),
        style=(("clip_secret_light" if _hidden else "clip_field_light") if light else ("clip_secret" if _hidden else "clip_field")),
    )
    $ _input_width = max(_field_w, _field_w + _ti._max_scroll())
    $ _adjustment.range = max(1, int(_input_width))
    $ _adjustment.page = max(1, int(_field_w))
    $ _adjustment.value = max(0, min(int(_adjustment.value), max(0, int(_input_width - _field_w))))
    hbox:
        spacing 6
        frame:
            xsize (width + 20)
            padding (10, 5)
            background (gal_ui_skin_input_focus if _focused else gal_ui_skin_input)
            vbox:
                spacing 2
                hbox:
                    spacing 4
                    viewport:
                        style "clip_input_viewport"
                        xsize _field_w
                        ysize 40
                        child_size (_input_width, 40)
                        xadjustment _adjustment
                        add _ti
                    if _eyed:
                        imagebutton:
                            id ("eye_" + var)
                            style "clip_icon"
                            xysize (40, 40)
                            yalign 0.5
                            idle (("q_icon_eye_off_dark" if getattr(store, "ai_show_key", False) else "q_icon_eye_dark") if light else ("q_icon_eye_off" if getattr(store, "ai_show_key", False) else "q_icon_eye"))
                            hover (("q_icon_eye_off_dark_h" if getattr(store, "ai_show_key", False) else "q_icon_eye_dark_h") if light else ("q_icon_eye_off_h" if getattr(store, "ai_show_key", False) else "q_icon_eye_h"))
                            action Function(toggle_show_key)
                            alt ("隐藏密钥" if getattr(store, "ai_show_key", False) else "显示密钥")
                if _input_width > _field_w:
                    add TextScrollBar(var, _field_w) id ("sb_" + var)

screen ai_settings():
    predict False
    on "hide" action [Function(reset_show_key), Function(reset_text_state, "ai_cfg_endpoint"), Function(reset_text_state, "ai_cfg_model"), Function(reset_text_state, "ai_cfg_key")]
    modal True
    zorder 300
    frame:
        align (0.5, 0.5)
        padding (36, 28)
        xsize 760
        background gal_ui_panel
        vbox:
            spacing 8
            text "模型设置" size 26 color gal_ui_ink
            text "保存后同时写进运行时和 options.txt，下一批生效。" size 14 color gal_ui_muted
            null height 8
            text "接口地址" size 14 color gal_ui_accent
            use clip_input("ai_cfg_endpoint", 200, False, 430)
            text "模型名" size 14 color gal_ui_accent
            use clip_input("ai_cfg_model", 80, False, 430)
            text "API Key" size 14 color gal_ui_accent
            use clip_input("ai_cfg_key", 200, True, 430)
            null height 10
            hbox:
                spacing 18
                textbutton "保存" action Function(apply_ai_settings)
                textbutton "关闭" action Hide("ai_settings")
    key "K_ESCAPE" action Hide("ai_settings")

screen ai_option_edit():
    predict False
    on "show" action Function(edit_keys_begin)
    on "hide" action [Function(reset_show_key), Function(reset_text_state, "ai_opt_edit_value"), Function(edit_keys_end)]
    modal True
    zorder 1010
    add Solid(gal_ui_wash)
    frame:
        align (0.5, 0.5)
        xsize 860
        padding (30, 24)
        background gal_ui_panel
        vbox:
            spacing 10
            text ai_opt_edit_key size 22 color gal_ui_ink
            $ _edit_item = ai_opt_flat.get(ai_opt_edit_key)
            if _edit_item and _edit_item.get("comment"):
                text _edit_item["comment"] size 13 color gal_ui_muted xmaximum 780
            $ _is_secret = "KEY" in (ai_opt_edit_key or "")
            use clip_input("ai_opt_edit_value", 600, _is_secret, 560)
            hbox:
                spacing 16
                textbutton "确定" action Function(apply_option_edit)
                textbutton "取消" action Hide("ai_option_edit")
    key "K_RETURN" action Function(apply_option_edit)
    key "K_ESCAPE" action Hide("ai_option_edit")

screen chapter_toast(text=""):
    zorder 160
    frame:
        align (0.5, 0.3)
        background gal_ui_skin_toast
        padding (24, 10)
        text gal_literal_tags(text) size 28 color gal_ui_ink xalign 0.5 substitute False
    timer 2.5 action Hide("chapter_toast")

# 背景与立绘走常驻 screen，好处是运行时刚生成、刚替换的图不用重新注册就能显示。
screen stage_bg():
    zorder -50
    $ _bg = getattr(store, "_dyn_bg", None)
    if _bg is not None:
        add _bg
    else:
        # 没有背景图时给一块深色底，避免显示成透明棋盘
        add Solid("#0b0f18")

screen stage_hero():
    # 立绘在文本框下面，不能盖住对话框和底部功能栏
    zorder -10
    $ _cast = getattr(store, "_dyn_cast", None)
    if _cast:
        for _d, _at in _cast:
            add _d at _at
    # 立绘构图自愈：新人上场后截图，等视觉模型回包再改位置
    if (getattr(store, "_frame_probe", None) is not None
            or getattr(store, "_frame_probe_busy", False)
            or getattr(store, "_frame_plan_ready", None) is not None):
        timer 0.25 repeat True action Function(frame_tick)

screen quick_menu():
    zorder 100
    # 全局快捷键：挂在游戏内常驻的功能栏上，菜单打开时由设置页自行屏蔽
    add ROUTER_WIDGET
    if quick_menu:
        $ button_gap = 2
        $ tip = GetTooltip("quick_menu")
        if tip:
            frame:
                xpos gui.name_xpos
                xanchor 0.0
                ypos 0.953
                yanchor 0.5
                xmaximum 200
                background gal_ui_skin_toast
                padding (14, 8)
                text tip size 14 color gal_ui_ink substitute False

        hbox:
            align (1.0, 0.992)
            xoffset (-3 * button_gap)
            frame:
                style "qbar_frame"
                background None
                hbox:
                    style_prefix "toolbar"
                    spacing button_gap

                    textbutton "SAVE" action [Function(capture_pending_thumb), Show("ai_slots", mode="save")] tooltip "保存" alt "保存"
                    textbutton "LOAD" action Show("ai_slots", mode="load") tooltip "读取" alt "读取"
                    textbutton "Q.SAVE" action slot_click_action([Function(capture_pending_thumb), Function(save_state, "quick")], "quick-save") tooltip "快速保存" alt "快速保存"
                    textbutton "Q.LOAD" action slot_click_action(Function(load_and_jump, "quick"), "quick-load") tooltip "快速读取" alt "快速读取"
                    textbutton "SETTING" action Function(settings_open) tooltip "设置" alt "设置"

                    null width 5
                    add Solid("#e0c49633", xysize=(1, 20))
                    null width 5

                    imagebutton:
                        style "toolbar_icon"
                        idle "toolbar_icon_last"
                        hover "toolbar_icon_last_h"
                        action Jump("ai_last_choice")
                        tooltip "回到上一个选择"
                        alt "回到上一个选择"
                    imagebutton:
                        style "toolbar_icon"
                        idle "toolbar_icon_rewind"
                        hover "toolbar_icon_rewind_h"
                        action Jump("ai_rewind_many")
                        tooltip "快退"
                        alt "快退"
                    imagebutton:
                        style "toolbar_icon"
                        idle "toolbar_icon_back"
                        hover "toolbar_icon_back_h"
                        action Jump("ai_rewind")
                        tooltip "上一句"
                        alt "上一句"
                    imagebutton:
                        style "toolbar_icon"
                        idle "toolbar_icon_history"
                        hover "toolbar_icon_history_h"
                        action ShowMenu("history")
                        tooltip "历史记录"
                        alt "历史记录"
                    imagebutton:
                        style "toolbar_icon"
                        idle "toolbar_icon_auto"
                        hover "toolbar_icon_auto_h"
                        selected_idle "toolbar_icon_auto_h"
                        selected_hover "toolbar_icon_auto_h"
                        selected preferences.afm_enable
                        action Preference("auto-forward", "toggle")
                        tooltip "自动播放"
                        alt "自动播放"
                    imagebutton:
                        style "toolbar_icon"
                        idle "toolbar_icon_skip"
                        hover "toolbar_icon_skip_h"
                        action Skip()
                        alternate Skip(fast=True, confirm=True)
                        tooltip "快进"
                        alt "快进"
                    imagebutton:
                        style "toolbar_icon"
                        idle "toolbar_icon_replay"
                        hover "toolbar_icon_replay_h"
                        action Function(replay_voice)
                        tooltip "重放当前语音"
                        alt "重放当前语音"
                    imagebutton:
                        style "toolbar_icon"
                        idle "toolbar_icon_fav"
                        hover "toolbar_icon_fav_h"
                        selected_idle "toolbar_icon_fav_h"
                        selected_hover "toolbar_icon_fav_h"
                        selected current_voice_faved()
                        action Function(toggle_voice_fav)
                        tooltip ("取消收藏当前语音" if current_voice_faved() else "收藏当前语音")
                        alt ("取消收藏当前语音" if current_voice_faved() else "收藏当前语音")
                    imagebutton:
                        style "toolbar_icon"
                        idle "toolbar_icon_hide"
                        hover "toolbar_icon_hide_h"
                        action Function(hide_ui_keep_stage)
                        tooltip "隐藏页面"
                        alt "隐藏页面"


style qbar_frame:
    background Frame("gui/quick/bar.png", 24, 24)
    padding (16, 6)

## 功能栏图标：Lucide（ISC），统一用 Transform 染色
image q_icon_last = Transform("gui/quick/last_choice.png", xysize=(22, 22), xalign=0.5, yalign=0.5, matrixcolor=TintMatrix(gal_ui_ink))
image q_icon_last_h = Transform("gui/quick/last_choice.png", xysize=(22, 22), xalign=0.5, yalign=0.5, matrixcolor=TintMatrix(gal_ui_accent))
image q_icon_rewind = Transform("gui/quick/rewind.png", xysize=(22, 22), xalign=0.5, yalign=0.5, matrixcolor=TintMatrix(gal_ui_ink))
image q_icon_rewind_h = Transform("gui/quick/rewind.png", xysize=(22, 22), xalign=0.5, yalign=0.5, matrixcolor=TintMatrix(gal_ui_accent))
image q_icon_back = Transform("gui/quick/back_line.png", xysize=(22, 22), xalign=0.5, yalign=0.5, matrixcolor=TintMatrix(gal_ui_ink))
image q_icon_back_h = Transform("gui/quick/back_line.png", xysize=(22, 22), xalign=0.5, yalign=0.5, matrixcolor=TintMatrix(gal_ui_accent))
image q_icon_history = Transform("gui/quick/history.png", xysize=(22, 22), xalign=0.5, yalign=0.5, matrixcolor=TintMatrix(gal_ui_ink))
image q_icon_history_h = Transform("gui/quick/history.png", xysize=(22, 22), xalign=0.5, yalign=0.5, matrixcolor=TintMatrix(gal_ui_accent))
image q_icon_auto = Transform("gui/quick/auto.png", xysize=(22, 22), xalign=0.5, yalign=0.5, matrixcolor=TintMatrix(gal_ui_ink))
image q_icon_auto_h = Transform("gui/quick/auto.png", xysize=(22, 22), xalign=0.5, yalign=0.5, matrixcolor=TintMatrix(gal_ui_accent))
image q_icon_skip = Transform("gui/quick/skip.png", xysize=(22, 22), xalign=0.5, yalign=0.5, matrixcolor=TintMatrix(gal_ui_ink))
image q_icon_skip_h = Transform("gui/quick/skip.png", xysize=(22, 22), xalign=0.5, yalign=0.5, matrixcolor=TintMatrix(gal_ui_accent))
image q_icon_replay = Transform("gui/quick/replay_voice.png", xysize=(22, 22), xalign=0.5, yalign=0.5, matrixcolor=TintMatrix(gal_ui_ink))
image q_icon_replay_h = Transform("gui/quick/replay_voice.png", xysize=(22, 22), xalign=0.5, yalign=0.5, matrixcolor=TintMatrix(gal_ui_accent))
image q_icon_fav = Transform("gui/quick/favorites.png", xysize=(22, 22), xalign=0.5, yalign=0.5, matrixcolor=TintMatrix(gal_ui_ink))
image q_icon_fav_h = Transform("gui/quick/favorites.png", xysize=(22, 22), xalign=0.5, yalign=0.5, matrixcolor=TintMatrix(gal_ui_accent))
image q_icon_hide = Transform("gui/quick/hide.png", xysize=(22, 22), xalign=0.5, yalign=0.5, matrixcolor=TintMatrix(gal_ui_ink))
image q_icon_hide_h = Transform("gui/quick/hide.png", xysize=(22, 22), xalign=0.5, yalign=0.5, matrixcolor=TintMatrix(gal_ui_accent))
image q_icon_eye = Transform("gui/quick/eye.png", xysize=(22, 22), xalign=0.5, yalign=0.5, matrixcolor=TintMatrix(gal_ui_ink))
image q_icon_eye_dark = Transform("gui/quick/eye.png", xysize=(22, 22), xalign=0.5, yalign=0.5, matrixcolor=TintMatrix("#6f6457"))
image q_icon_eye_dark_h = Transform("gui/quick/eye.png", xysize=(22, 22), xalign=0.5, yalign=0.5, matrixcolor=TintMatrix("#a9742f"))
image q_icon_eye_off_dark = Transform("gui/quick/hide.png", xysize=(22, 22), xalign=0.5, yalign=0.5, matrixcolor=TintMatrix("#6f6457"))
image q_icon_eye_off_dark_h = Transform("gui/quick/hide.png", xysize=(22, 22), xalign=0.5, yalign=0.5, matrixcolor=TintMatrix("#a9742f"))
image q_icon_eye_h = Transform("gui/quick/eye.png", xysize=(22, 22), xalign=0.5, yalign=0.5, matrixcolor=TintMatrix(gal_ui_accent))
image q_icon_eye_off = Transform("gui/quick/hide.png", xysize=(22, 22), xalign=0.5, yalign=0.5, matrixcolor=TintMatrix(gal_ui_ink))
image q_icon_eye_off_h = Transform("gui/quick/hide.png", xysize=(22, 22), xalign=0.5, yalign=0.5, matrixcolor=TintMatrix(gal_ui_accent))

screen voice_favorites():
    predict False
    modal True
    zorder 300
    add Solid(gal_ui_wash)
    frame:
        style "gal_ui_dialog"
        at (gal_ui_enter if settings_value("GALGAME_TRANSITIONS", "1") == "1" else gal_ui_still)
        xsize 880
        ysize 560
        padding (28, 22)
        background gal_ui_skin_panel
        vbox:
            spacing 10
            fixed:
                ysize 36
                text "语音收藏" size player_text_size(24) color gal_ui_ink yalign 0.5
                textbutton "关闭" style "gal_ui_button" text_style "gal_ui_button_text" action Hide("voice_favorites") xalign 1.0 yalign 0.5
            hbox:
                spacing 14
                textbutton ("取消收藏当前这句" if current_voice_faved() else "收藏当前这句") action Function(toggle_voice_fav)
                text "会记下角色、台词和语音文件，下次启动还在。" size player_text_size(13) color gal_ui_muted yalign 0.5
            viewport:
                ysize 430
                scrollbars "vertical"
                style_prefix "gal_ui"
                mousewheel True
                draggable True
                vbox:
                    spacing 8
                    $ _favs = voice_fav_list()
                    if not _favs:
                        text "还没有收藏。听到喜欢的语音时，点上面的按钮。" size player_text_size(15) color gal_ui_muted
                    for _i, _e in enumerate(_favs):
                        frame:
                            background Solid(gal_ui_card)
                            padding (14, 10)
                            xfill True
                            hbox:
                                spacing 12
                                vbox:
                                    spacing 3
                                    xmaximum 500
                                    text gal_literal_tags(_e.get("character") or "旁白") substitute False size player_text_size(15) color gal_ui_accent
                                    text gal_literal_tags(_e.get("text") or "") substitute False size player_text_size(14) color gal_ui_ink
                                textbutton "播放" action Function(play_voice_fav, _i)
                                textbutton "移除" action Function(remove_voice_fav, _i)

    key "K_ESCAPE" action Hide("voice_favorites")


## 通用确认框：覆盖 Ren'Py 默认样式，文案走 translations.rpy
screen confirm(message, yes_action, no_action):
    modal True
    zorder 200
    use gal_ui_confirm_body(renpy.translate_string(message), yes_action, no_action)
    key "game_menu" action no_action
    key "K_ESCAPE" action no_action

## 通知：底部居中的小胶囊，和功能栏同一套配色
transform gal_toolbar_notice:
    on show, replace:
        yoffset -52
        alpha 0.0
        easeout 0.20 yoffset 0 alpha 1.0
    on hide:
        easein 0.20 yoffset -52 alpha 0.0

screen notify(message):
    zorder 2000
    if message in (
        "已快速存档", "再点一次确认", "无效的存档槽位", "这个槽位是空的或已损坏",
        "还没有可以回到的选择", "还没有可重放的语音", "当前没有可收藏的语音",
        "已收藏", "已取消收藏",
    ):
        frame at (gal_toolbar_notice if settings_value("GALGAME_TRANSITIONS", "1") == "1" else gal_ui_still):
            xpos 24
            ypos 20
            background gal_ui_skin_toast
            padding (18, 10)
            text "[message!tq]" style "notify_text"
        timer 1.8 action Hide("notify")
    else:
        use gal_standard_notice(message)

screen gal_standard_notice(message):
    frame at (gal_ui_enter if settings_value("GALGAME_TRANSITIONS", "1") == "1" else gal_ui_still):
        align (0.5, 0.9)
        yoffset -20
        background gal_ui_skin_toast
        padding (24, 10)
        text "[message!tq]" style "notify_text" xmaximum 740
    timer 3.25 action Hide("notify")


## 保存设置时，有需要重启的项就弹这个确认
screen options_restart_confirm(keys=()):
    modal True
    zorder 1200
    add Solid(gal_ui_wash)
    frame:
        style "gal_ui_dialog"
        at (gal_ui_enter if settings_value("GALGAME_TRANSITIONS", "1") == "1" else gal_ui_still)
        xsize 600
        padding (30, 26)
        background gal_ui_skin_panel
        vbox:
            xfill True
            spacing 14
            text "需要重启才能生效" size 22 color gal_ui_ink
            text "以下设置改动需要重启游戏：" size 14 color gal_ui_ink
            for k in keys:
                text ("- " + option_restart_label(k)) size 14 color gal_ui_error
            text "点「是」会保存全部修改和当前进度（自动存档）并重启；点「否」会放弃本次全部修改，包括不需要重启的项。" size 13 color gal_ui_ink xmaximum 540
            hbox:
                style_prefix "qbar"
                spacing 22
                xalign 0.5
                textbutton "是" style "start_danger_button" text_style "start_danger_button_text" action [Function(confirm_options_restart), Hide("options_restart_confirm")]
                textbutton "否" action [Function(cancel_options_restart), Hide("options_restart_confirm")]
    key "game_menu" action [Function(cancel_options_restart), Hide("options_restart_confirm")]


## 开始游戏：先问清是重新生成还是重新开始
screen start_choice():
    predict False
    modal True
    zorder 250
    add Solid(gal_ui_wash)
    frame:
        style "gal_ui_dialog"
        at (gal_ui_enter if settings_value("GALGAME_TRANSITIONS", "1") == "1" else gal_ui_still)
        xsize 768
        padding (34, 26)
        background gal_ui_skin_panel
        vbox:
            spacing 16
            fixed:
                ysize 46
                vbox:
                    spacing 1
                    text "开始游戏" size 26 color gal_ui_ink
                    text "选择这一局的起点。" size 12 color gal_ui_muted
                hbox:
                    style_prefix "qbar"
                    xalign 1.0
                    yalign 0.5
                    textbutton "取消" action Hide("start_choice")
            hbox:
                spacing 18
                button:
                    xsize 340
                    padding (20, 18)
                    background gal_ui_skin_card
                    hover_background gal_ui_skin_hover
                    action Show("start_regen_confirm")
                    has vbox
                    spacing 8
                    text "重新生成" size 20 color gal_ui_error
                    text "清空剧情历史与全部存档（含快速存档），从第一拍重新生成。" size 13 color gal_ui_ink
                    null height 4
                    frame:
                        background Solid(gal_ui_card)
                        padding (9, 3)
                        text "会删除存档" size 11 color gal_ui_error
                button:
                    xsize 340
                    padding (20, 18)
                    background gal_ui_skin_card
                    hover_background gal_ui_skin_hover
                    action If(os.path.isfile(slot_path("quick")), Function(restart_cached_quick), [Hide("start_choice"), Start()])
                    has vbox
                    spacing 8
                    text "重新开始" size 20 color gal_ui_accent
                    text "有快速存档时从第一拍重播缓存，播完再生成。没有快速存档时开启新局。" size 13 color gal_ui_ink
                    null height 4
                    frame:
                        background Solid(gal_ui_selected)
                        padding (9, 3)
                        text "快速存档不变" size 11 color gal_ui_accent
            text "重新生成会同时删除自动存档和普通槽位，操作前会再确认一次。" size 12 color gal_ui_muted
    key "K_ESCAPE" action Hide("start_choice")


screen start_regen_confirm():
    modal True
    zorder 400
    add Solid(gal_ui_wash)
    frame:
        style "gal_ui_dialog"
        at (gal_ui_enter if settings_value("GALGAME_TRANSITIONS", "1") == "1" else gal_ui_still)
        xsize 540
        padding (30, 26)
        background gal_ui_skin_panel
        vbox:
            spacing 18
            text "重新生成？" size 22 color gal_ui_ink
            text "全部剧情历史、自动存档、快速存档和普通存档都会被删除，且无法恢复。" size 14 color gal_ui_error
            hbox:
                style_prefix "qbar"
                spacing 12
                xalign 1.0
                textbutton "重新生成" style "start_danger_button" text_style "start_danger_button_text" action [Function(wipe_progress), Hide("start_regen_confirm"), Hide("start_choice"), Start()]
                textbutton "取消" default_focus True action Hide("start_regen_confirm")
    key "K_ESCAPE" action Hide("start_regen_confirm")


## 历史记录：左侧头像/名字，右侧图标按钮；正文和按钮分栏，长句不会压到图标
style hist_return:
    background Solid("#8a6a3f")
    hover_background Solid("#a07c48")
    padding (18, 8)

style hist_return_text:
    size 15
    idle_color "#f7efdf"
    hover_color "#ffffff"
    outlines [(1, gal_ui_wash, 0, 0)]

screen history():
    tag menu
    predict False
    modal True
    add Solid(gal_ui_wash)
    $ _rows = history_view_records()
    $ _favs = {e.get("voice") for e in voice_fav_list() if e.get("voice")}
    $ _page_prev = screen_key(settings_value("GALGAME_KEY_HISTORY_PREV", "PageUp"))
    $ _page_next = screen_key(settings_value("GALGAME_KEY_HISTORY_NEXT", "PageDown"))
    # overlay 的键盘路由在菜单上下文里不跑，翻页键必须由屏幕自己收
    if _page_prev:
        key _page_prev action Function(history_page, -1)
    if _page_next:
        key _page_next action Function(history_page, 1)
    frame:
        align (0.5, 0.5)
        xsize 1040
        ysize 660
        padding (30, 24)
        background gal_ui_skin_panel
        vbox:
            spacing 12
            fixed:
                ysize 44
                text "历史记录" size player_text_size(26) color gal_ui_ink yalign 0.5
                textbutton "语音收藏列表" style "gal_ui_button" text_style "gal_ui_button_text" action Show("voice_favorites") xalign 0.91 yalign 0.5
                textbutton "×" action Return() style "hist_close" text_style "hist_close_text" xalign 1.0 yalign 0.5 tooltip "返回游戏" alt "返回游戏"
            viewport:
                ysize 540
                yadjustment hist_adj
                scrollbars "vertical"
                style_prefix "gal_ui"
                mousewheel True
                draggable True
                yinitial 1.0
                vbox:
                    spacing 8
                    for _h in _rows:
                        $ _who = str(_h.get("character") or _h.get("speaker") or "")
                        $ _speech = bool(_h.get("is_speech"))
                        $ _voice = _h.get("voice")
                        $ _avatar = history_avatar(_who, _h.get("standing")) if _speech else None
                        frame:
                            xfill True
                            padding (10, 8)
                            background Solid(gal_ui_card)
                            hover_background Solid(gal_ui_hover)
                            hbox:
                                spacing 8
                                if _speech and not is_narrator(_who):
                                    vbox:
                                        xsize 96
                                        spacing 6
                                        frame:
                                            xfill True
                                            padding (5, 4)
                                            background Solid(gal_ui_control)
                                            text gal_literal_tags(_who) substitute False size player_text_size(14) color gal_ui_accent xmaximum 86 xalign 0.5
                                        if _avatar:
                                            frame:
                                                xysize (96, 128)
                                                padding (0, 0)
                                                background Solid(gal_ui_control)
                                                add Transform(Image(_avatar), crop_relative=(0.28, 0.0, 0.44, 0.72), zoom=0.18)
                                frame:
                                    xsize (660 if (_speech and not is_narrator(_who)) else 764)
                                    padding (10, 8)
                                    background Solid(gal_ui_panel)
                                    $ _what = history_display_text(_h)
                                    $ _chosen = _h.get("chosen")
                                    $ _choices = _h.get("choices") or []
                                    vbox:
                                        text gal_literal_tags(_what) size player_text_size(17) color (gal_ui_ink if _speech else gal_ui_muted) substitute False
                                        if type(_chosen) is int and 0 <= _chosen < len(_choices) and isinstance(_choices[_chosen], Mapping):
                                            $ _choice_text = str(_choices[_chosen].get("label") or "")
                                            if _choice_text:
                                                text gal_literal_tags("选择：" + _choice_text) size player_text_size(15) color gal_ui_accent substitute False
                                frame:
                                    xsize 148
                                    ysize 72
                                    padding (4, 4)
                                    background Solid(gal_ui_panel)
                                    yalign 0.5
                                    vbox:
                                        yalign 0.5
                                        spacing 2
                                        hbox:
                                            xalign 0.5
                                            spacing 2
                                            imagebutton:
                                                style "hist_icon"
                                                idle "q_icon_back"
                                                hover "q_icon_back_h"
                                                action Function(history_jump, _h.get("turn", 0), _h.get("path", []))
                                                tooltip "回到这一句"
                                                alt "回到这一句"
                                            if _speech and (_voice or VOICE_ON):
                                                imagebutton:
                                                    style "hist_icon"
                                                    idle "q_icon_replay"
                                                    hover "q_icon_replay_h"
                                                    action Function(history_replay, _h)
                                                    tooltip "重播"
                                                    alt "重播"
                                                imagebutton:
                                                    style "hist_icon"
                                                    idle "q_icon_fav"
                                                    hover "q_icon_fav_h"
                                                    selected_idle "q_icon_fav_h"
                                                    selected_hover "q_icon_fav_h"
                                                    selected (_voice in _favs)
                                                    action Function(history_toggle_fav, _h)
                                                    tooltip ("取消收藏" if _voice in _favs else "收藏")
                                                    alt ("取消收藏" if _voice in _favs else "收藏")
                    if not _rows:
                        text "还没有对话记录。" size player_text_size(16) color gal_ui_muted
    use gal_ui_tip(GetTooltip(), 660)
    key "K_ESCAPE" action Return()


## 进入游戏前的加载条：等首块剧情和语音都准备好再放行
screen game_loading():
    modal True
    zorder 300
    add Solid(gal_ui_canvas)
    frame:
        align (0.5, 0.5)
        xsize 640
        padding (38, 30)
        background gal_ui_skin_panel
        vbox:
            spacing 14
            text _load_title size 26 color gal_ui_ink xalign 0.5
            text _load_text size 14 color gal_ui_muted xalign 0.5
            use gal_ui_progress(_load_progress)
            text ("%d%%" % int(_load_progress * 100)) size 12 color gal_ui_muted xalign 0.5
    if getattr(store, "_load_done", False):
        timer 0.05 action Return()
    else:
        timer 0.05 repeat True action Function(load_tick)


default slot_name_target = ""
default slot_name_value = ""

screen slot_name_edit():
    predict False
    modal True
    zorder 450
    on "show" action Function(edit_keys_begin)
    on "hide" action Function(edit_keys_end)
    add Solid(gal_ui_wash)
    frame:
        style "gal_ui_dialog"
        at (gal_ui_enter if settings_value("GALGAME_TRANSITIONS", "1") == "1" else gal_ui_still)
        xsize 580
        padding (28, 24)
        background gal_ui_skin_panel
        vbox:
            spacing 18
            text "存档名称（最多 64 字，留空恢复默认）" size player_text_size(18) color gal_ui_ink
            input:
                value VariableInputValue("slot_name_value")
                length 64
                xmaximum 500
                color gal_ui_ink
                size player_text_size(20)
            hbox:
                style_prefix "qbar"
                spacing 18
                textbutton "保存名称" action Function(commit_slot_name)
                textbutton "取消" action Hide("slot_name_edit")
    key "K_RETURN" action Function(commit_slot_name)
    key "K_ESCAPE" action Hide("slot_name_edit")

screen ai_slots(mode="save"):
    predict False
    modal True
    zorder 200
    default page = 1
    default selected_slot = "quick" if mode == "quick" else "1"
    default copy_source = None

    $ _manual = selected_slot in GAL_MANUAL_SLOTS
    $ _info = gal_slot_preview(selected_slot)
    $ _has_files = slot_has_files(selected_slot)
    $ _thumb = slot_thumb_data(selected_slot) if _info else None
    $ _label = gal_slot_label(selected_slot)
    $ _start = (page - 1) * GAL_SLOTS_PER_PAGE
    $ _can_save = mode == "save" and not main_menu and _manual

    add Solid(gal_ui_wash)
    frame:
        align (0.5, 0.5)
        xysize (1200, 664)
        padding (28, 24)
        background gal_ui_skin_panel
        vbox:
            spacing 12
            fixed:
                xysize (1144, 48)
                text ("存档" if mode == "save" else "读档" if mode == "load" else "快速存档") size player_text_size(28) color gal_ui_ink yalign 0.5
                hbox:
                    style_prefix "qbar"
                    xalign 0.23
                    yalign 0.5
                    spacing 8
                    if mode != "quick":
                        textbutton "上一页" sensitive (page > 1) action [SetScreenVariable("page", page - 1), SetScreenVariable("selected_slot", GAL_MANUAL_SLOTS[max(0, _start - GAL_SLOTS_PER_PAGE)])]
                        text ("%02d / %02d" % (page, GAL_SLOT_PAGES)) yalign 0.5 color gal_ui_ink size 18
                        textbutton "下一页" sensitive (page < GAL_SLOT_PAGES) action [SetScreenVariable("page", page + 1), SetScreenVariable("selected_slot", GAL_MANUAL_SLOTS[min(len(GAL_MANUAL_SLOTS) - 1, _start + GAL_SLOTS_PER_PAGE)])]
                hbox:
                    style_prefix "qbar"
                    xalign 1.0
                    yalign 0.5
                    spacing 8
                    if copy_source is None:
                        textbutton "复制存档" sensitive (_manual and bool(_info)) action SetScreenVariable("copy_source", selected_slot)
                    else:
                        textbutton "取消复制" action SetScreenVariable("copy_source", None)
                        $ _copy = [Function(gal_copy_slot, copy_source, selected_slot), SetScreenVariable("copy_source", None)]
                        textbutton "复制到此槽" sensitive (_manual and selected_slot != copy_source) action (Show("ai_confirm", text="用 %s 的副本覆盖 %s？" % (gal_slot_label(copy_source), _label), act=_copy) if _has_files else _copy)
                    textbutton ("替换存档" if _has_files else "保存到此槽") sensitive (_can_save and copy_source is None) action (Show("ai_confirm", text="用当前进度替换 %s？" % _label, act=Function(gal_write_manual_slot, selected_slot)) if _has_files else Function(gal_write_manual_slot, selected_slot))
                    textbutton "删除存档" sensitive (selected_slot != "auto" and _has_files and copy_source is None) action Function(gal_slot_ui_action, request_slot_delete, selected_slot)
            hbox:
                spacing 20
                fixed:
                    xysize (610, 500)
                    if mode != "quick":
                        if copy_source is not None:
                            text ("来源 " + gal_slot_label(copy_source) + "，请选择目标") color gal_ui_muted size 15 xalign 0.5 yalign 0.0
                        grid 2 4:
                            align (0.5, 0.5)
                            spacing 10
                            for slot in GAL_MANUAL_SLOTS[_start:_start + GAL_SLOTS_PER_PAGE]:
                                $ _occupied = slot_has_files(slot)
                                button:
                                    style "gal_ui_button"
                                    xysize (300, 102)
                                    selected (selected_slot == slot)
                                    action SetScreenVariable("selected_slot", slot)
                                    vbox:
                                        spacing 6
                                        text gal_slot_label(slot) style "gal_ui_button_text"
                                        text ("已有存档" if _occupied else "空槽位") size 15 color gal_ui_muted
                    else:
                        text "快速存档" color gal_ui_ink size 22 align (0.5, 0.5)
                frame:
                    xysize (514, 500)
                    padding (16, 12)
                    background gal_ui_skin_card
                    vbox:
                        spacing 8
                        fixed:
                            xysize (480, 270)
                            add Solid(gal_ui_control)
                            if _thumb:
                                add Transform(im.Data(_thumb, "thumb.png"), size=(480, 270), fit="contain", align=(0.5, 0.5))
                            else:
                                text ("无截图" if _info else "存档不可用" if _has_files else "空槽位") align (0.5, 0.5) color gal_ui_muted size 20
                        hbox:
                            style_prefix "qbar"
                            spacing 12
                            text _label size player_text_size(20) color gal_ui_ink yalign 0.5
                            text (slot_time_label(selected_slot, _info) if _info else "") size 15 color gal_ui_muted yalign 0.5
                            if _manual and _info:
                                textbutton "命名" action Function(gal_slot_ui_action, open_slot_name, selected_slot)
                        if _info:
                            text gal_literal_tags(_clean_slot_name(_info.get("name")) or _info.get("_chapter") or "") substitute False color gal_ui_muted size 15
                            viewport:
                                xysize (480, 110)
                                style_prefix "gal_ui"
                                mousewheel True
                                scrollbars "vertical"
                                text gal_literal_tags(_info.get("dialogue") or "此存档没有当前拍台词") substitute False color gal_ui_ink size player_text_size(18)
            hbox:
                style_prefix "qbar"
                xalign 1.0
                spacing 10
                textbutton "读档" sensitive (bool(_info) and copy_source is None) action slot_click_action(Function(load_and_jump, selected_slot), "slot-load-" + selected_slot)
                textbutton "语音收藏夹" action Show("voice_favorites")
                textbutton ("关闭" if main_menu else "返回游戏") action Hide("ai_slots")
                if not main_menu:
                    textbutton "返回主页" action MainMenu(confirm=True)
    key "K_ESCAPE" action Hide("ai_slots")


screen ai_confirm(text="", act=None):
    modal True
    zorder 400
    use gal_ui_confirm_body(text, act, Hide("ai_confirm"), danger=True)
    key "K_ESCAPE" action Hide("ai_confirm")

style qbar_button is gal_ui_button:
    padding (9, 6)

style qbar_button_text is gal_ui_button_text:
    size 15

style qbar_icon is gal_ui_icon

style hist_icon is gal_ui_icon

style hist_close is gal_ui_icon

style hist_close_text is gal_ui_button_text:
    size 20
    align (0.5, 0.5)

style start_danger_button is gal_ui_danger

style start_danger_button_text is gal_ui_danger_text:
    size 15

style clip_icon is gal_ui_icon

style gal_ui_vscrollbar is gal_ui_scroll

style toolbar_button:
    background None
    hover_background Solid("#ffffff0c")
    padding (11, 10)

style toolbar_button_text:
    size 15
    idle_color "#d8cbb6"
    hover_color "#f0c46a"
    selected_color "#f0c46a"
    outlines [(1, "#05070bcc", 0, 0)]

style toolbar_icon:
    background None
    hover_background Solid("#ffffff0c")
    padding (8, 8)

# Toolbar uses the original artwork treatment; history keeps its own colors.
image toolbar_icon_last = Transform("gui/quick/last_choice.png", zoom=0.42, matrixcolor=TintMatrix("#d8cbb6"))
image toolbar_icon_last_h = Transform("gui/quick/last_choice.png", zoom=0.42, matrixcolor=TintMatrix("#f0c46a"))
image toolbar_icon_rewind = Transform("gui/quick/rewind.png", zoom=0.42, matrixcolor=TintMatrix("#d8cbb6"))
image toolbar_icon_rewind_h = Transform("gui/quick/rewind.png", zoom=0.42, matrixcolor=TintMatrix("#f0c46a"))
image toolbar_icon_back = Transform("gui/quick/back_line.png", zoom=0.42, matrixcolor=TintMatrix("#d8cbb6"))
image toolbar_icon_back_h = Transform("gui/quick/back_line.png", zoom=0.42, matrixcolor=TintMatrix("#f0c46a"))
image toolbar_icon_history = Transform("gui/quick/history.png", zoom=0.42, matrixcolor=TintMatrix("#d8cbb6"))
image toolbar_icon_history_h = Transform("gui/quick/history.png", zoom=0.42, matrixcolor=TintMatrix("#f0c46a"))
image toolbar_icon_auto = Transform("gui/quick/auto.png", zoom=0.42, matrixcolor=TintMatrix("#d8cbb6"))
image toolbar_icon_auto_h = Transform("gui/quick/auto.png", zoom=0.42, matrixcolor=TintMatrix("#f0c46a"))
image toolbar_icon_skip = Transform("gui/quick/skip.png", zoom=0.42, matrixcolor=TintMatrix("#d8cbb6"))
image toolbar_icon_skip_h = Transform("gui/quick/skip.png", zoom=0.42, matrixcolor=TintMatrix("#f0c46a"))
image toolbar_icon_replay = Transform("gui/quick/replay_voice.png", zoom=0.42, matrixcolor=TintMatrix("#d8cbb6"))
image toolbar_icon_replay_h = Transform("gui/quick/replay_voice.png", zoom=0.42, matrixcolor=TintMatrix("#f0c46a"))
image toolbar_icon_fav = Transform("gui/quick/favorites.png", zoom=0.42, matrixcolor=TintMatrix("#d8cbb6"))
image toolbar_icon_fav_h = Transform("gui/quick/favorites.png", zoom=0.42, matrixcolor=TintMatrix("#f0c46a"))
image toolbar_icon_hide = Transform("gui/quick/hide.png", zoom=0.42, matrixcolor=TintMatrix("#d8cbb6"))
image toolbar_icon_hide_h = Transform("gui/quick/hide.png", zoom=0.42, matrixcolor=TintMatrix("#f0c46a"))

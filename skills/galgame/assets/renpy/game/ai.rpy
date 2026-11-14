# Modified for GalGameFramework 1.7.4 (2026-11-10): consistent CPS/fonts and avoid unchanged history writes.
# Modified for GalGameFramework 1.7.3 (2026-11-10): unified progress storage and legacy seed without resurrection.
# Modified for GalGameFramework 1.7.2 (2026-11-10): transactional choices, lineage restoration and single-consume prefetch.
# Modified for GalGameFramework 1.7.2 (2026-11-09): development setting uses the restart gate.
# Modified for GalGameFramework 1.7.1 (2026-11-09): JSON slot deletion/names and current voice replay.
# Modified for GalGameFramework 1.7.0 (2026-11-09): use Image and guard BGM playback with if_changed.
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

# 实时生成层：Ren'Py 只负责显示，文本由模型按批返回
#
# 环境变量（可选）：
#   GALGAME_ENDPOINT  OpenAI 兼容的 chat/completions 地址
#   GALGAME_KEY       API Key
#   GALGAME_MODEL     模型名
# 未设置 ENDPOINT 时使用内置 mock 剧情，保证离线可玩。

init -5 python:
    import builtins
    from collections.abc import Mapping
    import base64
    import hashlib
    import ipaddress
    import json
    import os
    import re
    import shutil
    import socket
    import ssl
    import struct
    import threading
    import time
    import urllib.error
    import urllib.parse
    import urllib.request
    import uuid
    import pygame

    def _text_state_map():
        states = getattr(renpy.store, "_text_states", None)
        if not hasattr(states, "get"):
            states = {}
            renpy.store._text_states = states
        return states

    def _text_state(field_id):
        states = _text_state_map()
        st = states.get(field_id)
        if not hasattr(st, "get"):
            st = {}
            states[field_id] = st
        return st

    def _text_widget_map():
        d = getattr(renpy.store, "_text_widgets", None)
        if not hasattr(d, "get"):
            d = {}
            renpy.store._text_widgets = d
        return d

    def _text_adjustment_map():
        d = getattr(renpy.store, "_text_adjustments", None)
        if not hasattr(d, "get"):
            d = {}
            renpy.store._text_adjustments = d
        return d

    def _text_adjustment(field_id):
        d = _text_adjustment_map()
        adj = d.get(field_id)
        if adj is None:
            adj = renpy.display.behavior.Adjustment(
                range=1, value=0, step=1, page=1,
            )
            d[field_id] = adj
        return adj

    def _text_bar_adjustment_map():
        d = getattr(renpy.store, "_text_bar_adjustments", None)
        if not hasattr(d, "get"):
            d = {}
            renpy.store._text_bar_adjustments = d
        return d

    def _text_bar_to_view(field_id, value):
        a = _text_adjustment(field_id)
        try:
            v = int(value)
        except (TypeError, ValueError):
            return
        a.value = max(0, min(int(a.range), v))
        a.update()

    def _text_bar_adjustment(field_id):
        d = _text_bar_adjustment_map()
        adj = d.get(field_id)
        if adj is None:
            adj = renpy.display.behavior.Adjustment(
                range=1, value=0, step=1, page=1,
                changed=lambda v, fid=field_id: _text_bar_to_view(fid, v),
            )
            d[field_id] = adj
        return adj

    def _text_sb_state_map():
        d = getattr(renpy.store, "_text_sb_states", None)
        if not hasattr(d, "get"):
            d = {}
            renpy.store._text_sb_states = d
        return d

    def _text_sb_state(field_id):
        d = _text_sb_state_map()
        st = d.get(field_id)
        if not hasattr(st, "get"):
            st = {"dragging": False, "offset": 0.0}
            d[field_id] = st
        return st

    class TextScrollBar(renpy.display.displayable.Displayable):
        """自己画的滚动条，直接读写 viewport adjustment，不经过 Ren'Py 的 bar。"""

        def __init__(self, field_id, width, **kwargs):
            super(TextScrollBar, self).__init__(**kwargs)
            self.field_id = field_id
            self.width = max(20, int(width))

        # 视觉上只有 6px 高，但给 12px 的点击热区，方便抓取。
        HIT_HEIGHT = 12
        TRACK_HEIGHT = 6

        def size(self):
            return (self.width, self.HIT_HEIGHT)

        def _metrics(self):
            w = _text_widget_map().get(self.field_id)
            if w is None:
                return None
            try:
                maxs = max(0, int(w._max_scroll()))
                total = max(1, int(w.viewport_width + maxs))
                page = max(1, int(w.viewport_width))
                value = max(0, min(maxs, int(w.scroll_adjustment.value)))
            except Exception:
                return None
            track = float(self.width)
            thumb_w = max(20.0, track * page / float(total))
            thumb_w = min(track, thumb_w)
            frac = (value / float(maxs)) if maxs > 0 else 0.0
            frac = max(0.0, min(1.0, frac))
            thumb_x = (track - thumb_w) * frac
            return w, maxs, value, thumb_x, thumb_w

        def _set_from_x(self, x):
            m = self._metrics()
            if not m:
                return
            w, maxs, value, thumb_x, thumb_w = m
            st = _text_sb_state(self.field_id)
            avail = max(1.0, self.width - thumb_w)
            frac = (float(x) - float(st.get("offset", 0.0))) / avail
            frac = max(0.0, min(1.0, frac))
            w.scroll_adjustment.value = int(round(frac * maxs))
            w.scroll_adjustment.update()
            renpy.display.render.redraw(self, 0)

        def render(self, width, height, st, at):
            rv = renpy.display.render.Render(self.width, self.HIT_HEIGHT)
            ty = (self.HIT_HEIGHT - self.TRACK_HEIGHT) // 2
            try:
                track = renpy.display.imagelike.Solid(
                    "#ffffff18", xysize=(self.width, self.TRACK_HEIGHT))
                tr = renpy.display.render.render(track, self.width, self.TRACK_HEIGHT, st, at)
                rv.blit(tr, (0, ty))
                m = self._metrics()
                if m:
                    _, _, _, tx, tw = m
                    thumb = renpy.display.imagelike.Solid(
                        "#c9a86a", xysize=(max(1, int(tw)), self.TRACK_HEIGHT))
                    th = renpy.display.render.render(
                        thumb, max(1, int(tw)), self.TRACK_HEIGHT, st, at)
                    rv.blit(th, (int(tx), ty))
            except Exception:
                pass
            return rv

        def event(self, ev, x, y, st):
            stt = _text_sb_state(self.field_id)
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                # 这个 displayable 放在 vbox 里，Ren'Py 会把整个容器区域的事件
                # 都先递过来；必须自己判定是否真的点在条上，否则点设置里任何
                # 地方（包括眼睛图标）都会被当成拖滚动条。
                if not (0 <= x <= self.width and 0 <= y <= self.HIT_HEIGHT):
                    return None
                m = self._metrics()
                if not m:
                    return None
                _, _, _, tx, tw = m
                stt["dragging"] = True
                stt["offset"] = (x - tx) if tx <= x <= tx + tw else tw / 2.0
                self._set_from_x(x)
                raise renpy.display.core.IgnoreEvent()
            if ev.type == pygame.MOUSEMOTION and stt.get("dragging"):
                try:
                    if not pygame.mouse.get_pressed()[0]:
                        stt["dragging"] = False
                        return None
                except Exception:
                    pass
                # 拖动中允许指针移出条外，x 会在 _set_from_x 里夹紧。
                self._set_from_x(x)
                raise renpy.display.core.IgnoreEvent()
            if ev.type == pygame.MOUSEBUTTONUP and ev.button == 1 and stt.get("dragging"):
                stt["dragging"] = False
                raise renpy.display.core.IgnoreEvent()
            return None

    def set_text_focus(field_id):
        old_focus = getattr(renpy.store, "_text_focus", "")
        old_widget = _text_widget_map().get(old_focus)
        if old_widget is not None and old_focus != field_id:
            old_widget._selecting = False
            if renpy.display.focus.get_grab() is old_widget:
                renpy.display.focus.set_grab(None)
        renpy.store._text_focus = field_id
        for key, st in _text_state_map().items():
            if key != field_id and hasattr(st, "get"):
                st["selecting"] = False

    def reset_text_state(field_id):
        states = _text_state_map()
        try:
            states.pop(field_id, None)
        except Exception:
            pass
        if getattr(renpy.store, "_text_focus", "") == field_id:
            renpy.store._text_focus = ""
        adjustment = _text_adjustment_map().get(field_id)
        if adjustment is not None:
            adjustment.value = 0
            adjustment.update()
        bar_adj = _text_bar_adjustment_map().get(field_id)
        if bar_adj is not None:
            bar_adj.value = 0
            bar_adj.update()

    class SelectableInput(renpy.display.behavior.Input):
        """带鼠标选择、Shift 选择和 Ctrl+C/X/V 的单行文本框。"""

        def __init__(self, field_id, var, **kwargs):
            self.field_id = field_id
            self.var = var
            self.viewport_width = max(0, int(kwargs.pop("viewport_width", 0) or 0))
            self.scroll_adjustment = kwargs.pop("scroll_adjustment", None) or _text_adjustment(field_id)
            self._sel_start = None
            self._sel_end = None
            self._selecting = False
            self._last_click = 0.0
            self._last_click_x = 0
            self._measure_cache = {}
            self.measure_style = kwargs.get("style", "clip_field")
            if not isinstance(self.measure_style, str):
                self.measure_style = "clip_field"
            _text_widget_map()[field_id] = self
            kwargs.setdefault("default", str(getattr(renpy.store, var, "") or ""))
            kwargs.setdefault("copypaste", True)
            kwargs["changed"] = self._changed
            super(SelectableInput, self).__init__(**kwargs)
            # 关掉 Ren'Py 自带的光标。自带光标是作为文本标签插进排版里的，
            # 长文本横向滚动后，它和高亮各自依赖不同的排版计算，会差出一两个字符。
            # 下面 render 里用 _x_for_index 自己画光标，和高亮同一套坐标。
            try:
                self.caret = renpy.display.imagelike.Solid("#00000000", xysize=(1, 1))
            except Exception:
                pass
            self._restore_state()

        def _changed(self, text):
            setattr(renpy.store, self.var, text)
            self._measure_cache.clear()
            self._save_state()

        def _restore_state(self):
            content = str(getattr(renpy.store, self.var, self.content) or "")
            self.content = content
            st = _text_state(self.field_id)
            try:
                caret = int(st.get("caret", len(content)) or 0)
            except (TypeError, ValueError):
                caret = len(content)
            self.caret_pos = max(0, min(caret, len(content)))
            self._sel_start = st.get("sel_start")
            self._sel_end = st.get("sel_end")
            self._selecting = bool(st.get("selecting", False))
            self.update_text(self.content, True)
            # Rebuilding the screen must preserve the user's viewport position.
            # Caret-following is handled only after editing or moving the caret.

        def _save_state(self):
            st = _text_state(self.field_id)
            st["caret"] = int(self.caret_pos)
            st["sel_start"] = self._sel_start
            st["sel_end"] = self._sel_end
            st["selecting"] = bool(self._selecting)
            self._sync_bar()

        def per_interact(self):
            try:
                super(SelectableInput, self).per_interact()
            except Exception:
                pass
            self.shown = True
            content = str(getattr(renpy.store, self.var, self.content) or "")
            if content != self.content:
                self.content = content
                self._measure_cache.clear()
            st = _text_state(self.field_id)
            try:
                caret = int(st.get("caret", len(content)) or 0)
            except (TypeError, ValueError):
                caret = len(content)
            self.caret_pos = max(0, min(caret, len(content)))
            self._sel_start = st.get("sel_start")
            self._sel_end = st.get("sel_end")
            self._selecting = bool(st.get("selecting", False))
            self.update_text(self.content, True)

        def _display_text(self):
            mask = getattr(self, "mask", None)
            if mask:
                return str(mask)[:1] * len(self.content)
            return self.content

        def _x_for_index(self, index):
            text = self._display_text()
            index = max(0, min(len(text), int(index)))
            if index <= 0:
                return 0
            if index in self._measure_cache:
                return self._measure_cache[index]
            try:
                t = renpy.text.text.Text(text[:index], style=self.measure_style, substitute=False)
                w = t.size()[0]
            except Exception:
                try:
                    w = super(SelectableInput, self).size()[0] * index / float(max(1, len(text)))
                except Exception:
                    w = index * 10
            self._measure_cache[index] = w
            return w

        def _max_scroll(self):
            sw = self.viewport_width
            if sw <= 0:
                return 0
            total = self._x_for_index(len(self._display_text()))
            return max(0, int(total - sw))

        def _scroll_offset(self):
            try:
                value = int(self.scroll_adjustment.value)
            except (AttributeError, TypeError, ValueError):
                value = 0
            return max(0, min(self._max_scroll(), value))

        def _ensure_caret_visible(self):
            sw = self.viewport_width
            if sw <= 0:
                return
            maxs = self._max_scroll()
            cx = int(self._x_for_index(self.caret_pos))
            current = self._scroll_offset()
            if cx < current + 4:
                target = max(0, cx - 12)
            elif cx > current + sw - 12:
                target = min(maxs, cx - sw + 12)
            else:
                return
            self.scroll_adjustment.value = max(0, min(maxs, int(target)))
            self.scroll_adjustment.update()
            self._sync_bar()

        def _sync_bar(self):
            try:
                b = _text_bar_adjustment(self.field_id)
                b.range = max(1, int(self.viewport_width + self._max_scroll()))
                b.page = max(1, int(self.viewport_width))
                b.value = max(0, min(int(self.scroll_adjustment.value), int(b.range - b.page)))
                b.update()
            except Exception:
                pass

        def _index_at_x(self, x):
            text = self._display_text()
            # Viewport events already include the horizontal scroll offset.
            x = max(0, int(x))
            lo, hi = 0, len(text)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if self._x_for_index(mid) <= x:
                    lo = mid
                else:
                    hi = mid - 1
            return lo

        def _sel_range(self):
            if self._sel_start is None or self._sel_end is None:
                return None
            a = max(0, min(len(self.content), int(self._sel_start)))
            b = max(0, min(len(self.content), int(self._sel_end)))
            if a == b:
                return None
            return (min(a, b), max(a, b))

        def _clear_selection(self):
            self._sel_start = None
            self._sel_end = None
            self._save_state()

        def _delete_selection(self):
            rng = self._sel_range()
            if not rng:
                return False
            a, b = rng
            new_content = self.content[:a] + self.content[b:]
            self.caret_pos = a
            self._sel_start = None
            self._sel_end = None
            self._measure_cache.clear()
            self.update_text(new_content, True)
            self._ensure_caret_visible()
            self._save_state()
            return True

        def _insert_text(self, text):
            text = "".join(c for c in str(text or "") if ord(c) >= 32)
            if self.allow is not None:
                text = "".join(c for c in text if c in self.allow)
            if self.exclude:
                text = "".join(c for c in text if c not in self.exclude)
            if not text:
                return
            self._delete_selection()
            pos = max(0, min(len(self.content), int(self.caret_pos)))
            room = self.length - len(self.content) if self.length else len(text)
            if room <= 0:
                return
            text = text[:room]
            new_content = self.content[:pos] + text + self.content[pos:]
            self.caret_pos = pos + len(text)
            self._measure_cache.clear()
            self.update_text(new_content, True)
            self._ensure_caret_visible()
            self._save_state()

        def _copy_selection(self):
            rng = self._sel_range()
            if rng:
                text = self.content[rng[0]:rng[1]]
            else:
                text = self.content
            if text:
                clipboard_set(text)

        def _paste(self):
            text = clipboard_get()
            if text:
                self._insert_text(text)

        def _select_all(self):
            self._sel_start = 0
            self._sel_end = len(self.content)
            self.caret_pos = len(self.content)
            self.scroll_adjustment.value = 0
            self.scroll_adjustment.update()
            self._sync_bar()
            self._save_state()
            self.update_text(self.content, True)

        def _select_word(self, index):
            text = self.content
            n = len(text)
            i = max(0, min(n, int(index)))
            sep = " \t\r\n，。！？、,.!?;:；："
            a = i
            while a > 0 and text[a - 1] not in sep:
                a -= 1
            b = i
            while b < n and text[b] not in sep:
                b += 1
            if a == b:
                a, b = i, min(n, i + 1)
            self._sel_start = a
            self._sel_end = b
            self.caret_pos = b
            self._save_state()
            self.update_text(self.content, True)

        def _extend_to(self, pos):
            if self._sel_start is None:
                self._sel_start = self.caret_pos
            self.caret_pos = max(0, min(len(self.content), int(pos)))
            self._sel_end = self.caret_pos
            self._ensure_caret_visible()
            self._save_state()
            self.update_text(self.content, True)

        def size(self, *args, **kwargs):
            w, h = super(SelectableInput, self).size(*args, **kwargs)
            if self.viewport_width:
                w = max(w, self.viewport_width)
            return w, h

        def render(self, width, height, st, at):
            rv = super(SelectableInput, self).render(width, height, st, at)
            full_w = max(1, int(rv.width))
            full_h = max(1, int(rv.height))
            out = renpy.display.render.Render(full_w, full_h)
            rng = self._sel_range()
            if rng and self.editable:
                x0 = int(self._x_for_index(rng[0]))
                x1 = int(self._x_for_index(rng[1]))
                x0 = max(0, min(full_w, x0))
                x1 = max(0, min(full_w, x1))
                if x1 > x0:
                    w = max(1, x1 - x0)
                    try:
                        solid = renpy.display.imagelike.Solid("#c9a86a66", xysize=(w, full_h))
                        sr = renpy.display.render.render(solid, w, full_h, st, at)
                        out.blit(sr, (x0, 0))
                    except Exception:
                        pass
            out.blit(rv, (0, 0))
            # 自己画光标，坐标和高亮完全一致。
            if self.editable and getattr(renpy.store, "_text_focus", "") == self.field_id:
                try:
                    if int(st * 2) % 2 == 0:
                        cx = int(self._x_for_index(self.caret_pos))
                        cx = max(0, min(full_w - 2, cx))
                        ch = int(getattr(self.style, "size", 18) or 18)
                        ch = max(8, min(full_h, ch))
                        caret = renpy.display.imagelike.Solid("#f2ead9", xysize=(2, ch))
                        cr = renpy.display.render.render(caret, 2, ch, st, at)
                        out.blit(cr, (cx, (full_h - ch) // 2))
                    renpy.display.render.redraw(self, 0.5)
                except Exception:
                    pass
            out.text_input = getattr(rv, "text_input", False)
            return out

        def event(self, ev, x, y, st):
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                set_text_focus(self.field_id)
                try:
                    idx = self._index_at_x(x)
                except Exception:
                    idx = len(self.content)
                now = time.time()
                if now - self._last_click < 0.35 and abs(x - self._last_click_x) < 6:
                    self._select_word(idx)
                else:
                    self.caret_pos = idx
                    self._sel_start = idx
                    self._sel_end = idx
                    self._selecting = True
                    renpy.display.focus.set_grab(self)
                    self._ensure_caret_visible()
                    self._save_state()
                    self.update_text(self.content, True)
                self._last_click = now
                self._last_click_x = x
                renpy.display.render.redraw(self, 0)
                raise renpy.display.core.IgnoreEvent()

            if ev.type == pygame.MOUSEMOTION and self._selecting:
                # up 事件可能丢（Alt+Tab/窗口外释放），用鼠标实际状态兜底
                try:
                    if not pygame.mouse.get_pressed()[0]:
                        self._selecting = False
                        if renpy.display.focus.get_grab() is self:
                            renpy.display.focus.set_grab(None)
                        self._save_state()
                        return None
                except Exception:
                    pass
                # Ren'Py 的 MOUSEMOTION 不一定带 buttons，不能用它判断是否还在拖
                self.caret_pos = self._index_at_x(x)
                self._sel_end = self.caret_pos
                self._save_state()
                self.update_text(self.content, True)
                renpy.display.render.redraw(self, 0)
                raise renpy.display.core.IgnoreEvent()

            if ev.type == pygame.MOUSEBUTTONUP and ev.button == 1 and self._selecting:
                self._selecting = False
                if renpy.display.focus.get_grab() is self:
                    renpy.display.focus.set_grab(None)
                self._save_state()
                raise renpy.display.core.IgnoreEvent()

            if ev.type in (pygame.KEYDOWN, pygame.TEXTINPUT, pygame.TEXTEDITING):
                if getattr(renpy.store, "_text_focus", "") != self.field_id:
                    return None

            if ev.type == pygame.KEYDOWN:
                mod = ev.mod
                ctrl = mod & (pygame.KMOD_CTRL | pygame.KMOD_META)
                shift = mod & pygame.KMOD_SHIFT
                if ctrl and ev.key == pygame.K_a:
                    self._select_all()
                    raise renpy.display.core.IgnoreEvent()
                if ctrl and ev.key == pygame.K_c:
                    self._copy_selection()
                    raise renpy.display.core.IgnoreEvent()
                if ctrl and ev.key == pygame.K_x:
                    self._copy_selection()
                    self._delete_selection()
                    raise renpy.display.core.IgnoreEvent()
                if ctrl and ev.key == pygame.K_v:
                    self._paste()
                    raise renpy.display.core.IgnoreEvent()
                if shift and ev.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_HOME, pygame.K_END):
                    if self._sel_start is None:
                        self._sel_start = self.caret_pos
                    if ev.key == pygame.K_LEFT:
                        self._extend_to(self.caret_pos - 1)
                    elif ev.key == pygame.K_RIGHT:
                        self._extend_to(self.caret_pos + 1)
                    elif ev.key == pygame.K_HOME:
                        self._extend_to(0)
                    else:
                        self._extend_to(len(self.content))
                    raise renpy.display.core.IgnoreEvent()
                if ev.key in (pygame.K_BACKSPACE, pygame.K_DELETE) and self._sel_range():
                    self._delete_selection()
                    raise renpy.display.core.IgnoreEvent()
                if not shift and ev.key in (
                        pygame.K_LEFT, pygame.K_RIGHT, pygame.K_HOME, pygame.K_END,
                        pygame.K_UP, pygame.K_DOWN):
                    self._clear_selection()
                if self._sel_range() and ev.unicode and ord(ev.unicode[0]) >= 32:
                    self._delete_selection()

            if ev.type == pygame.TEXTINPUT and self._sel_range():
                self._delete_selection()

            rv = super(SelectableInput, self).event(ev, x, y, st)
            # 只有键盘/文本输入才把视线拉回光标；鼠标移动、滚轮、滚动条
            # 操作不能触发自动滚动，否则滚动条刚拖走就被拉回去。
            if ev.type in (pygame.KEYDOWN, pygame.TEXTINPUT, pygame.TEXTEDITING):
                self._ensure_caret_visible()
            self._save_state()
            return rv

    # 启动时一次读入，后续以内存为准；options_boot 会做迁移和校验。
    _FILE_CFG = options_boot()

    def _atomic_write_text(path, text):
        atomic_write_file(path, text)

    def _atomic_write_bytes(path, data):
        atomic_write_file(path, data, binary=True)

    def _on(name, default="0"):
        """数值开关：0/1；也兼容 true/false、yes/no、on/off。"""
        v = str(_cfg(name, default)).strip().lower()
        return v in ("1", "true", "yes", "on", "开")

    def _cfg(name, default=""):
        return (
            os.environ.get(name, "").strip()
            or _FILE_CFG.get(name, "").strip()
            or default
        )

    AI_ENDPOINT = _cfg(
        "GALGAME_ENDPOINT",
        "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
    )
    AI_KEY = _cfg("GALGAME_KEY")
    AI_MODEL = _cfg("GALGAME_MODEL", "qwen3.8-flash")
    AI_TIMEOUT = float(_cfg("GALGAME_TIMEOUT", "60"))
    # 思考预算：1 为最低；设 0 表示关闭思考。
    AI_THINKING = int(_cfg("GALGAME_THINKING", "1"))
    AI_FALLBACK_MODEL = _cfg("GALGAME_FALLBACK_MODEL")
    AI_FALLBACK_ENDPOINT = _cfg("GALGAME_FALLBACK_ENDPOINT")
    AI_FALLBACK_KEY = _cfg("GALGAME_FALLBACK_KEY")
    # 自愈模型：后台检测错误，修 JSON、补安全剧情。填了模型才会启用。
    DOCTOR_ON = _on("GALGAME_DOCTOR", "0")
    DOCTOR_MODEL = _cfg("GALGAME_DOCTOR_MODEL")
    DOCTOR_ENDPOINT = _cfg("GALGAME_DOCTOR_ENDPOINT")
    DOCTOR_KEY = _cfg("GALGAME_DOCTOR_KEY")
    DOCTOR_INTERVAL = max(5, int(_cfg("GALGAME_DOCTOR_INTERVAL", "15")))
    DOCTOR_STALL = max(20, int(_cfg("GALGAME_DOCTOR_STALL", "90")))
    DOCTOR_MAX = max(1, int(_cfg("GALGAME_DOCTOR_MAX", "3")))
    # 立绘构图自愈：新人上场时截图，交给视觉模型看头顶、重叠和露腿，再回写位置
    DOCTOR_FRAME = _on("GALGAME_DOCTOR_FRAME", "1")
    DOCTOR_VISION_MODEL = _cfg("GALGAME_DOCTOR_VISION_MODEL")
    DOCTOR_FRAME_MAX = max(1, int(_cfg("GALGAME_DOCTOR_FRAME_MAX", "8")))
    HARNESS_SELF_HEAL = _on("GALGAME_HARNESS_SELF_HEAL", "1")
    DOCTOR_STATE = {
        "fixes": 0, "errors": 0, "switches": 0, "frames": 0,
        "last_progress": time.time(),
    }
    DOCTOR_EVENTS = []
    CONTEXT_LIMIT = max(4000, int(_cfg("GALGAME_CONTEXT_LIMIT", "32000")))
    CONTEXT_RATIO = float(_cfg("GALGAME_CONTEXT_RATIO", "0.75"))
    SUMMARY_KEEP = max(4, int(_cfg("GALGAME_SUMMARY_KEEP", "20")))
    SCENE_MIN_STAY = max(1, int(_cfg("GALGAME_SCENE_MIN_STAY", "5")))
    # 场景锁定：1 时换场必须有正文过渡句；普通换场一批最多一次，跨天可以再换
    SCENE_LOCK = _on("GALGAME_SCENE_LOCK", "1")
    CHAPTER_LENGTH = max(10, int(_cfg("GALGAME_CHAPTER_LENGTH", "40")))
    ENABLE_CHAPTER = _on("GALGAME_ENABLE_CHAPTER", "1")
    ENDLESS = _on("GALGAME_ENDLESS", "1")
    PLAYER_SPRITE = _on("GALGAME_PLAYER_SPRITE", "0")
    HEROINE_AUTO = _on("GALGAME_HEROINE_AUTO", "1")
    # 题材词，只用于提示里的措辞，比如「校园恋爱」「都市职场」「奇幻冒险」。
    GENRE = _cfg("GALGAME_GENRE", "校园恋爱")
    # 场景时间固定三种：day 白天、dusk 黄昏、night 夜晚。
    TIME_NAMES = ("day", "dusk", "night")
    TIME_WORDS = (
        ("day", ("早上", "清晨", "早晨", "上午", "中午", "午休", "午饭", "白天",
                 "早自习", "早读", "第一节课", "第二节课", "课间", "天亮", "晨光", "正午")),
        ("dusk", ("下午", "放学", "傍晚", "夕阳", "黄昏", "日落", "天黑前")),
        ("night", ("晚上", "夜里", "天黑", "晚自习", "深夜", "入夜")),
    )
    AI_MOCK = not AI_KEY

    PLAN_AHEAD = max(1, int(_cfg("GALGAME_PLAN_AHEAD", "10")))
    BEAT_MIN = max(1, int(_cfg("GALGAME_BEAT_MIN", "20")))
    BEAT_MAX = max(BEAT_MIN, int(_cfg("GALGAME_BEAT_MAX", "50")))
    BEAT_SENTENCES = max(1, int(_cfg("GALGAME_BEAT_SENTENCES", "2")))
    BEAT_LINES = max(1, int(_cfg("GALGAME_BEAT_LINES", "2")))
    SHOT_VARY = _on("GALGAME_SHOT_VARY", "1")

    CHOICE_WINDOW = max(1, int(_cfg("GALGAME_CHOICE_WINDOW", "30")))
    CHOICE_MIN = max(0, int(_cfg("GALGAME_CHOICE_MIN", "1")))
    CHOICE_MAX = max(CHOICE_MIN, int(_cfg("GALGAME_CHOICE_MAX", "2")))
    CHOICE_GAP = max(1, int(_cfg("GALGAME_CHOICE_GAP", "12")))
    PER_BLOCK_MAX = max(1, PLAN_AHEAD * CHOICE_MAX // CHOICE_WINDOW)

    TEXT_CPS = text_cps_value(_cfg("GALGAME_TEXT_CPS"))
    config.default_text_cps = TEXT_CPS

    # 显示字体：填 game/fonts/ 下的文件名（.ttf/.otf/.ttc）
    FONT_DEFAULT = "SourceHanSansLite.ttf"
    FONT_EXTS = (".ttf", ".otf", ".ttc")

    def font_pick(name):
        name = str(name or "").strip().replace("\\", "/")
        parts = name.split("/")
        # The picker imports system fonts into local/; preserve that relative path.
        allowed = (len(parts) == 1 or (len(parts) == 2 and parts[0] == "local"))
        if (allowed and parts[-1] not in ("", ".", "..")
                and os.path.basename(parts[-1]) == parts[-1]
                and name.lower().endswith(FONT_EXTS)):
            fonts_root = os.path.realpath(os.path.join(config.basedir, "game", "fonts"))
            candidate = os.path.realpath(os.path.join(fonts_root, *parts))
            try:
                if (os.path.normcase(os.path.commonpath([fonts_root, candidate])) == os.path.normcase(fonts_root)
                        and os.path.isfile(candidate)):
                    return name
            except ValueError:
                pass
        return FONT_DEFAULT

    FONT_FILE = font_pick(_cfg("GALGAME_FONT", FONT_DEFAULT))
    FONT_PATH = "fonts/" + FONT_FILE

    HISTORY_FEED = max(2, int(_cfg("GALGAME_HISTORY_FEED", "8")))
    DETAIL_INTERVAL = max(10, int(_cfg("GALGAME_DETAIL_INTERVAL", "50")))
    PERSONA_MAX = max(5, int(_cfg("GALGAME_PERSONA_MAX", "20")))

    # 重新注入：每多少拍把世界观、人设、章节、日记摘要重灌一次，防止写久了漂移
    REINJECT_EVERY = max(5, int(_cfg("GALGAME_REINJECT_EVERY", "40")))

    # 多智能体：每个角色一个子调用，主模型补旁白并重排拍
    SUBAGENTS = _on("GALGAME_SUBAGENTS", "0")
    SUBAGENT_LINES = max(1, int(_cfg("GALGAME_SUBAGENT_LINES", "2")))
    SUBAGENT_MODEL = _cfg("GALGAME_SUBAGENT_MODEL")
    DIARY_EVERY = max(10, int(_cfg("GALGAME_DIARY_EVERY", "50")))

    # 子角色规则（game/agent.md，一份注入所有子请求）
    SUBAGENT_RULES_DEFAULT = (
        "你只扮演当前角色一个人，只写这个角色的台词。"
        "不要写旁白、动作描写、心理描写，不要替别人说话。"
        "不在场或这一轮没话说时，只输出 {\"lines\":[]}。"
        "只输出 JSON，不要 Markdown 代码块，不要解释。"
    )

    # 父合成规则（game/director.md）
    DIRECTOR_RULES_DEFAULT = (
        "你负责把各角色这一轮给出的台词接成一部视觉小说：先补旁白和动作，再按自然顺序重排拍序。"
        "台词必须原样使用，一个字都不要改，也不要新增别人没说过的话。"
        "最后给出 plan、chapter、scene_plan 和 choices，遵守场景、选项和节拍规则。"
    )

    # 让模型在剧情里自己新增角色：0 关，1 开。开启后模型可在 batch 里返回 new_characters，
    # 引擎校验后写成 persona/<id>.md 并立即注册。
    AUTO_CHARACTER = _on("GALGAME_AUTO_CHARACTER", "0")
    TEMP_CAST = set()
    AUTO_CHARACTER_MAX = max(1, int(_cfg("GALGAME_AUTO_CHARACTER_MAX", "1")))
    TEMP_CAST_MAX = max(1, int(_cfg("GALGAME_TEMP_CAST_MAX", "2")))

    # 内容由谁生成：harness 还是 options 里的模型。
    # renpy.exe 启动时没有 harness，USING_HARNESS=1 也会回退到模型，日志里会写明。
    USING_HARNESS = _on("GALGAME_USING_HARNESS", "0")
    HOST = _cfg("GALGAME_HOST", "")
    HARNESS_TIMEOUT = max(5, int(_cfg("GALGAME_HARNESS_TIMEOUT", "45")))

    # 生图来源：0 只用文件夹里的图，1 交给 harness 生成，2 交给 options 里的生图模型
    GEN_SCENE = int(_cfg("GALGAME_GEN_SCENE", "0") or 0)
    GEN_STANDING = int(_cfg("GALGAME_GEN_STANDING", "0") or 0)
    GEN_UI_CHOICE = int(_cfg("GALGAME_GEN_UI_CHOICE", "0") or 0)
    GEN_UI_DIALOGUE = int(_cfg("GALGAME_GEN_UI_DIALOGUE", "0") or 0)
    GEN_UI_TITLE = int(_cfg("GALGAME_GEN_UI_TITLE", "0") or 0)

    # ---------- 语音 ----------
    VOICE_ON = _on("GALGAME_VOICE", "0")
    VOICE_MODE = (_cfg("GALGAME_VOICE_MODE", "tts") or "tts").strip().lower()
    def voice_provider_endpoint(api, endpoint):
        return {
            "mimo": "https://api.xiaomimimo.com/v1/chat/completions",
            "openai_official": "https://api.openai.com/v1/audio/speech",
            "dashscope": endpoint if "/api/v1/" in endpoint and ".maas.aliyuncs.com/" in endpoint else "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
        }.get(api, endpoint)

    VOICE_ENDPOINT = _cfg("GALGAME_VOICE_ENDPOINT")
    # 协议：openai 走 OpenAI 兼容 /audio/speech；dashscope 走阿里云百炼。
    # 没写 GALGAME_VOICE_API 时按端点自动认。
    VOICE_API = (_cfg("GALGAME_VOICE_API", "") or "").strip().lower()
    if VOICE_API not in ("openai", "dashscope", "mimo", "openai_official", "other"):
        VOICE_API = "dashscope" if (
            "dashscope" in VOICE_ENDPOINT or "aliyuncs.com" in VOICE_ENDPOINT
        ) else "openai"
    VOICE_ENDPOINT = voice_provider_endpoint(VOICE_API, VOICE_ENDPOINT)
    VOICE_KEY = _cfg("GALGAME_VOICE_KEY") or ("" if VOICE_API in ("mimo", "openai_official") else AI_KEY)
    _VOICE_DEFAULT_MODEL = "qwen3-tts-flash" if VOICE_API == "dashscope" else "mimo-v2.5-tts" if VOICE_API == "mimo" else "tts-1"
    VOICE_MODEL = _cfg("GALGAME_VOICE_MODEL") or _VOICE_DEFAULT_MODEL
    # 百炼文生声只能选固定音色，不能读自由描述；人物卡 frontmatter 可写 voice_name。
    VOICE_NAME = _cfg("GALGAME_VOICE_NAME", "Cherry")
    VOICE_LANG = _cfg("GALGAME_VOICE_LANG", "Chinese")
    # 百炼声音复刻要业务空间专属域名；只写 WorkspaceId 即可。
    VOICE_CLONE_WS = _cfg("GALGAME_VOICE_CLONE_WORKSPACE")
    VOICE_CLONE_MODEL = _cfg("GALGAME_VOICE_CLONE_MODEL", "qwen-audio-3.1-tts-plus")
    VOICE_CLONE_PREFIX = _cfg("GALGAME_VOICE_CLONE_PREFIX", "galgame")
    VOICE_FORMAT = (_cfg("GALGAME_VOICE_FORMAT", "wav") or "wav").strip().lower()
    VOICE_PLAYER = _on("GALGAME_VOICE_PLAYER", "0")
    VOICE_TIMEOUT = max(10, int(_cfg("GALGAME_VOICE_TIMEOUT", "60")))
    VOICE_DIR = os.path.join(config.basedir, "game", "voice")
    VOICE_EXAMPLE_DIR = os.path.join(config.basedir, "game", "voice_example")
    VOICE_ID_FILE = os.path.join(config.basedir, "game", "voice_ids.json")
    VOICE_DS_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
    TEMP_CAST_VOICE = {}

    # 所有图片统一放在 game/picture/ 下
    PIC_ROOT = os.path.join(config.basedir, "game", "picture")
    PIC_SCENE = os.path.join(PIC_ROOT, "scene")
    PIC_STANDING = os.path.join(PIC_ROOT, "standing")
    PIC_UI = os.path.join(PIC_ROOT, "ui")
    UI_CHOICE = os.path.join(PIC_UI, "choice.png")
    UI_DIALOGUE = os.path.join(PIC_UI, "dialogue.png")
    UI_TITLE = os.path.join(PIC_UI, "title.png")

    # ---------- BGM ----------
    BGM_DIR = os.path.join(config.basedir, "game", "bgm")
    BGM_MIN_STAY = max(1, int(_cfg("GALGAME_BGM_MIN_STAY", "5")))

    def _scan_bgm():
        found = {}
        if not os.path.isdir(BGM_DIR):
            return found
        for fn in sorted(os.listdir(BGM_DIR)):
            stem, ext = os.path.splitext(fn)
            if ext.lower() not in (".mp3", ".ogg", ".wav", ".m4a", ".opus"):
                continue
            if not stem.isdigit():
                continue
            found[str(int(stem))] = "bgm/" + fn
        return found

    BGM_FILES = _scan_bgm()
    BGM_IDS = tuple(sorted(BGM_FILES, key=lambda x: int(x)))

    def _read_bgm_doc():
        if not os.path.isdir(BGM_DIR):
            return ""
        names = [
            n for n in sorted(os.listdir(BGM_DIR))
            if n.lower().endswith(".md") and not n.startswith("_")
        ]
        if "bgm.md" in names:
            names.remove("bgm.md")
            names.insert(0, "bgm.md")
        for n in names:
            try:
                with open(os.path.join(BGM_DIR, n), "r", encoding="utf-8") as f:
                    text = f.read().strip()
                if text:
                    return text
            except OSError:
                pass
        return ""

    def _bgm_prompt():
        if not BGM_IDS:
            return ""
        doc = _read_bgm_doc()
        out = (
            "【BGM】可用 id：" + "、".join(BGM_IDS)
            + "。0 表示停止；不写或 null 表示沿用上一拍。"
        )
        if doc:
            out += chr(10) + doc
        out += (
            chr(10) + "换 BGM 要克制：能沿用就沿用，一批最多换一次；"
            "只有剧情明显转场、情绪变化或地点变化时才换，按上面的用法选。"
        )
        return out

    def _bgm_norm(raw):
        s = str(raw).strip()
        if s in ("", "none", "null"):
            return None
        if s == "0":
            return "0"
        try:
            s = str(int(s))
        except (TypeError, ValueError):
            return None
        return s if s in BGM_FILES else None

    # Ren'Py 自带的 Python 没有系统 CA，HTTPS 需要自带一份证书包。
    _CA_FILE = os.path.join(config.basedir, "game", "cacert.pem")
    if not os.path.exists(_CA_FILE):
        _CA_FILE = None

    _STAND_KEYS = {
        "id": "id", "编号": "id",
        "角色": "character", "character": "character",
        "衣服": "clothes", "clothing": "clothes", "clothes": "clothes",
        "动作": "action", "action": "action",
        "表情": "expression", "expression": "expression",
        "什么时候用": "when", "when": "when", "场合": "when", "使用场合": "when",
    }

    def _md_section(body, title):
        if not body or ("## " + title) not in body:
            return ""
        part = body.split("## " + title, 1)[1]
        if chr(10) + "## " in part:
            part = part.split(chr(10) + "## ", 1)[0]
        return part.strip()

    def _parse_standings(body):
        """读人物卡「## 立绘」。主格式是键值块：

            ### 冷淡
            id：guarded
            动作：站着，双手在身前交叠
            表情：眼睑下垂，嘴角平直
            什么时候用：默认；防备时

        也兼容旧的表格和 `- guarded：冷淡` 列表。返回 {id: {character, action, expression, when}}。
        """
        out = {}
        if "## 立绘" not in body:
            return out
        section = body.split("## 立绘", 1)[1].split("\n## ", 1)[0]
        items = []
        cur = {}

        def flush():
            if cur.get("id"):
                items.append(dict(cur))
            cur.clear()

        for raw in section.splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.startswith("|"):
                cells = [c.strip() for c in line.strip("|").split("|")]
                if len(cells) < 2:
                    continue
                first = cells[0].strip("`* ")
                if _STAND_KEYS.get(first.lower()) == "id" or set(first) <= set("-: "):
                    continue
                items.append({
                    "id": first,
                    "character": cells[1].strip("`* "),
                    "action": cells[2] if len(cells) > 2 else "",
                    "expression": cells[3] if len(cells) > 3 else "",
                    "when": cells[4] if len(cells) > 4 else "",
                })
                continue
            if line.startswith("#"):
                flush()
                continue
            if line.startswith("- "):
                parts = re.split(r"[：:]", line[2:].strip(), 1)
                if len(parts) == 2 and parts[0].strip():
                    items.append({"id": parts[0].strip("`* "), "expression": parts[1].strip()})
                continue
            sep = "：" if "：" in line else (":" if ":" in line else None)
            if not sep:
                continue
            key, val = line.split(sep, 1)
            key = key.strip().strip("*` ").lower()
            val = val.strip().strip("`* ")
            mapped = _STAND_KEYS.get(key)
            if mapped == "id":
                if cur.get("id"):
                    flush()
                cur["id"] = val
            elif mapped:
                cur[mapped] = val
        flush()
        for item in items:
            sid = str(item.get("id") or "").strip()
            if not sid:
                continue
            out[sid] = {
                "character": item.get("character", ""),
                "clothes": item.get("clothes", ""),
                "action": item.get("action", ""),
                "expression": item.get("expression", ""),
                "when": item.get("when", ""),
            }
        return out

    def _gender_en(value):
        """性别统一存英文，老卡里的中文也顺手换掉。"""
        g = str(value or "").strip().lower()
        if g in ("女", "female", "f", "girl", "woman"):
            return "female"
        if g in ("男", "male", "m", "boy", "man"):
            return "male"
        if g in ("其他", "other", "nonbinary", "non-binary", "nb"):
            return "other"
        return g

    def _pkey(name):
        return str(name or "").strip().lower()

    def _load_personas():
        base = os.path.join(config.basedir, "game", "persona")
        out = {}
        if not os.path.isdir(base):
            return out
        for fn in sorted(os.listdir(base)):
            if not fn.lower().endswith(".md"):
                continue
            # 下划线开头的文件是模板或说明，不算人物卡。
            if fn.startswith("_") or fn.lower().startswith("readme"):
                continue
            try:
                with open(os.path.join(base, fn), "r", encoding="utf-8") as f:
                    text = f.read()
            except OSError:
                continue
            meta = {}
            body = text
            if text.startswith("---"):
                end = text.find("---", 3)
                if end > 0:
                    for line in text[3:end].splitlines():
                        if ":" in line:
                            k, v = line.split(":", 1)
                            # 值可能写成 "绫" / '绫'，统一剥掉引号，与 aliases 口径一致
                            meta[k.strip()] = v.strip().strip("\"'")
                    body = text[end + 3:].strip()
            pid = meta.get("id") or fn[:-3]
            name = meta.get("name") or pid
            ill = meta.get("illustration") or pid
            aliases = [
                a.strip().strip("\"'")
                for a in re.split(r"[,，]", meta.get("aliases", "").strip("[]"))
                if a.strip()
            ]
            gender = _gender_en(meta.get("gender", "") or meta.get("性别", ""))
            voice_desc = str(meta.get("voice", "") or "").strip() or _md_section(body, "声音")
            voice_name = str(meta.get("voice_name", "") or "").strip()
            lead = str(meta.get("lead", "")).lower() in ("1", "true", "yes", "女主")
            romance_raw = str(meta.get("romance", "")).strip().lower()
            if romance_raw in ("1", "true", "yes", "可攻略"):
                romance = True
            elif romance_raw in ("0", "false", "no", "不可攻略"):
                romance = False
            else:
                romance = lead
            try:
                affection0 = int(str(meta.get("affection", "0")).strip())
            except (TypeError, ValueError):
                affection0 = 0
            affection0 = max(0, min(100, affection0))
            entry = {
                "id": pid,
                "name": name,
                "gender": gender,
                "voice": voice_desc,
                "voice_name": voice_name,
                "illustration": ill,
                "aliases": aliases,
                "lead": lead,
                "romance": romance,
                "affection": affection0,
                "file": fn,
                "dir": pid,
                "standings": _parse_standings(body),
                "body": body,
            }
            out[name] = entry
            out[pid] = entry
            out[_pkey(name)] = entry
            out[_pkey(pid)] = entry
            for a in aliases:
                out[a] = entry
                out[_pkey(a)] = entry
        return out

    PERSONAS = _load_personas()

    def _persona_entries():
        seen = set()
        items = []
        # 快照迭代：后台线程可能同时往 PERSONAS 里插新角色
        for entry in list(PERSONAS.values()):
            if id(entry) in seen:
                continue
            seen.add(id(entry))
            items.append(entry)
        return items

    def is_player_card(entry):
        return str(entry.get("id", "")).lower() in ("me", "player") or entry.get("name") == "我"

    def standing_ids(persona):
        """立绘 id 只认人物卡「## 立绘」的五行键值块，不扫目录猜编号。
        没有这一节就没有可选立绘，引擎按 default_standing 兜底渲染。"""
        if persona and persona.get("standings"):
            return list(persona["standings"].keys())
        return []

    def default_standing(persona):
        ids = standing_ids(persona)
        return ids[0] if ids else DEFAULT_MOOD

    def standing_value(sid):
        """立绘 id 对外统一成整数；人物卡里写成非数字的就原样当字符串。"""
        s = str(sid if sid is not None else "").strip()
        return int(s) if s.isdigit() else s

    def resolve_persona(name):
        if not name:
            return None
        key = str(name).strip()
        return PERSONAS.get(key) or PERSONAS.get(_pkey(key))

    # 女主角由 persona/ 目录决定：GALGAME_HEROINE 指定 > frontmatter 里 lead: true > 文件名排序第一。
    def _pick_heroine():
        items = _persona_entries()
        want = _cfg("GALGAME_HEROINE")
        if want:
            p = resolve_persona(want)
            if p:
                return p
        if HEROINE_AUTO and items:
            # 留空时按初始好感度高低选，好感度相同再偏向 lead 卡；玩家卡不参选
            ranked = sorted(
                [e for e in items if not is_player_card(e)] or items,
                key=lambda e: (int(e.get("affection", 0)), 1 if e.get("lead") else 0),
                reverse=True,
            )
            return ranked[0]
        for e in items:
            if e["lead"]:
                return e
        if items:
            return sorted(items, key=lambda e: e["id"])[0]
        return None

    HEROINE = _pick_heroine()
    HEROINE_NAME = HEROINE["name"] if HEROINE else "她"
    HEROINE_ILL = HEROINE["illustration"] if HEROINE else "heroine"
    HEROINE_FILE = (
        os.path.join(config.basedir, "game", "persona", HEROINE["file"]) if HEROINE else ""
    )

    def persona_path():
        return HEROINE_FILE

    # ---------- 世界观 ----------

    SEIKAI_FILE = os.path.join(config.basedir, "game", "seikai.md")

    def read_seikai():
        try:
            with open(SEIKAI_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            return ""

    def seikai_section(title):
        text = read_seikai()
        if not text or ("## " + title) not in text:
            return ""
        part = text.split("## " + title, 1)[1]
        if "\n## " in part:
            part = part.split("\n## ", 1)[0]
        return part.strip()

    def write_seikai_situation(summary):
        """只重写「## 当前局势」一节，前面人工写的部分原样保留。"""
        summary = (summary or "").strip()
        if not summary:
            return
        text = read_seikai()
        block = "## 当前局势" + chr(10) + chr(10) + summary + chr(10)
        if "## 当前局势" in text:
            head, rest = text.split("## 当前局势", 1)
            if "\n## " in rest:
                tail = "\n## " + rest.split("\n## ", 1)[1]
            else:
                tail = ""
            new_text = head.rstrip() + chr(10) + chr(10) + block + tail
        else:
            new_text = text.rstrip() + chr(10) + chr(10) + block
        try:
            with open(SEIKAI_FILE, "w", encoding="utf-8") as f:
                f.write(new_text)
        except OSError:
            pass

    def _world_prompt(full):
        """full=False 时只注入一句话、世界规则、禁忌与尺度，省 token。"""
        if not read_seikai():
            return ""
        if full:
            return "【世界观】以下是这个世界的设定，任何剧情都不能违反。" + chr(10) + read_seikai()
        parts = []
        for title in ("一句话", "世界规则", "禁忌与尺度", "当前局势"):
            body = seikai_section(title)
            if body:
                parts.append(title + "：" + body)
        if not parts:
            return "【世界观】" + read_seikai()
        return "【世界观摘要】" + chr(10) + chr(10).join(parts)

    def _writing_prompt(st=None, count=None, director=False):
        """game/prompt.md：写作规范，跟世界观一起注入。占位符在请求时替换。"""
        path = os.path.join(config.basedir, "game", "prompt.md")
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read().strip()
        except OSError:
            return ""
        if not text:
            return ""
        n = int(count or PLAN_AHEAD)
        repl = {
            "<N>": str(n),
            "<BATCH_LENGTH_RULE>": (
                "每条已提供台词安排一个发言拍；另加必要旁白，整合轮没有固定总拍数。"
                if director else "本批拍数：%d" % n
            ),
            "<BATCH_LENGTH_CHECK>": (
                "是否恰好引用所有已提供的编号，并用必要旁白连接剧情？"
                if director else "是否以本轮指定的 %d 拍为目标，且没有为了凑拍而补写角色台词？" % n
            ),
            "<DIRECTOR_LINE_ID>": '"line_id": 1, ' if director else "",
            "<BEAT_MIN>": str(BEAT_MIN),
            "<BEAT_MAX>": str(BEAT_MAX),
            "<BEAT_SENTENCES>": str(BEAT_SENTENCES),
            "<BEAT_LINES>": str(BEAT_LINES),
            "<TIME_PLACE>": "、".join(t + "+" + p for t, p in TIME_PLACE),
            "<BGM_IDS>": ("、".join(BGM_IDS) if BGM_IDS else "无（bgm 一律写 null）"),
            "<CHOICE_RULE>": (
                "这一块最多 %d 次选择；距离上次选择不足 %d 拍时不要给 choices；"
                "整体保持每 %d 拍 %d-%d 次选择。"
                % (PER_BLOCK_MAX, CHOICE_GAP, CHOICE_WINDOW, CHOICE_MIN, CHOICE_MAX)
            ),
            "<HEROINE_NAME>": HEROINE_NAME,
            "<ENDING_RULE>": (
                "故事没有结局，不要写 ending。"
                if ENDLESS else
                '要收束这一部时，输出 "ending":"结局标题"，并把最后几拍写成收束，不要再开新线。'
            ),
        }
        for key, value in repl.items():
            text = text.replace(key, value)
        return text

    def need_reinject(st):
        if not st.get("_inject_model"):
            return True
        if st.get("_inject_model") != active_model():
            return True
        return st.get("cursor", 0) - st.get("_injected_at", 0) >= REINJECT_EVERY

    def mark_injected(st):
        st["_injected_at"] = st.get("cursor", 0)
        st["_inject_model"] = active_model()

    def force_reinject(st):
        """开始/继续时强制下一批做一次完整注入：世界观、prompt.md、人物卡。"""
        if st is None:
            return
        st["_inject_model"] = ""
        st["_injected_at"] = -1
        _debug("force reinject")

    def _system_prompt(st, full=None, count=None):
        if full is None:
            full = need_reinject(st)
        head = _world_prompt(full)
        if full:
            head += chr(10) + chr(10) + "【重新注入】以上设定是当前唯一有效的版本，此前所有与它冲突的描写作废。"
        write = _writing_prompt(st, count)
        bgm = _bgm_prompt()
        return (
            (head + chr(10) + chr(10) if head else "")
            + (write + chr(10) + chr(10) if write else "")
            + _personas_prompt() + chr(10) + chr(10)
            + _player_rule()
            + _standing_rule()
            + _new_character_rule()
            + (bgm + chr(10) + chr(10) if bgm else "")
            + _format_spec()
        )

    def _strip_card_frontmatter(text):
        text = str(text or "")
        if text.startswith("---"):
            end = text.find("---", 3)
            if end > 0:
                text = text[end + 3:]
        return text.strip()

    def _persona_body(entry):
        """读人物卡正文（去 frontmatter）；文件不存在时退回内存里的 body。"""
        if not entry:
            return ""
        fn = entry.get("file")
        if fn:
            path = os.path.join(config.basedir, "game", "persona", fn)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    text = _strip_card_frontmatter(f.read())
                if text:
                    return text
            except OSError:
                pass
        return str(entry.get("body") or "").strip()

    def _persona_prompt():
        body = _persona_body(HEROINE)
        return body or _PERSONA

    def _personas_prompt():
        """所有非玩家角色卡的正文，女主角排第一；配角整卡也进主提示词。"""
        entries = _persona_entries()
        if HEROINE:
            hid = HEROINE.get("id")
            entries = ([e for e in entries if e.get("id") == hid]
                       + [e for e in entries if e.get("id") != hid])
        parts = []
        for e in entries:
            if is_player_card(e):
                continue
            body = _persona_body(e)
            if not body:
                continue
            parts.append("【人物卡：" + e["name"] + "】" + chr(10) + body)
        if not parts:
            return _persona_prompt()
        return (chr(10) + chr(10)).join(parts)

    def _section_body_bounds(text, title):
        """返回行首 '## title' 正文的 [start, end)，end 停在下一个行首 '## ' 前。"""
        m = re.search(r"(?m)^##\s*" + re.escape(title) + r"\s*$", text)
        if not m:
            return None
        body_start = m.end()
        if body_start < len(text) and text[body_start] == chr(10):
            body_start += 1
        nxt = re.search(r"(?m)^##\s+", text[body_start:])
        body_end = body_start + nxt.start() if nxt else len(text)
        return body_start, body_end

    def read_persona_details():
        path = persona_path()
        if not path:
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError:
            return []
        bounds = _section_body_bounds(text, "剧情设定")
        if not bounds:
            return []
        section = text[bounds[0]:bounds[1]]
        out = []
        for line in section.splitlines():
            line = line.strip()
            if line.startswith("- "):
                out.append(line[2:].strip())
        return out

    def write_persona_details(items):
        path = persona_path()
        if not path:
            return
        clean = []
        for item in items:
            item = str(item).strip()
            if item and item not in clean:
                clean.append(item)
        clean = clean[:PERSONA_MAX]
        if not clean:
            return
        body = chr(10).join("- " + i for i in clean)
        # 读 + 算边界 + 写整体入锁：读在锁外时，别的线程可能正在替换同名段落
        with _PERSONA_LOCK:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read()
            except OSError:
                return
            bounds = _section_body_bounds(text, "剧情设定")
            if bounds:
                prefix = text[:bounds[0]]
                suffix = text[bounds[1]:]
                new_text = prefix + body + chr(10) + chr(10) + suffix
            else:
                new_text = text.rstrip() + chr(10) + chr(10) + "## 剧情设定" + chr(10) + chr(10) + body + chr(10)
            try:
                _atomic_write_text(path, new_text)
            except OSError as exc:
                _debug("人物卡设定写盘失败：%s" % exc)

    def _on_lineage(st, rec):
        """记录是否在当前这条线上：祖先或自身，不含没走过的分支。"""
        rp = list(rec.get("path") or [])
        cur = list(st.get("path") or [])
        return cur[:len(rp)] == rp

    def http_detail(st):
        recs = _history_records(st, DETAIL_INTERVAL)
        body = chr(10).join(
            _line_text(r) for r in recs
        )
        existing = read_persona_details()
        prompt = (
            "已有的长期设定：" + chr(10)
            + (chr(10).join("- " + x for x in existing) if existing else "（无）")
            + chr(10) + chr(10)
            + "最近 %d 拍的剧情：" % len(recs) + chr(10) + body + chr(10) + chr(10)
            + "请输出合并后的完整设定列表：把新剧情里值得长期记住的设定（爱好、习惯、口头禅、关系变化、重要事件）合并进去，"
            "去掉重复和过时的内容，保留最多 %d 条，每条一句话。" % PERSONA_MAX
            + '只输出 JSON：{"details":["...","..."]}。'
        )
        payload = {
            "model": active_model(),
            "messages": [
                {"role": "system", "content": "你负责整理视觉小说的人物设定，只输出 JSON。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.4,
            "max_tokens": 400,
            "response_format": {"type": "json_object"},
        }
        if AI_THINKING > 0:
            payload["enable_thinking"] = True
            payload["thinking_budget"] = AI_THINKING
        else:
            payload["enable_thinking"] = False
        def ask(p):
            data = _post_json(active_endpoint(), p, active_key(), AI_TIMEOUT, request_kind="persona_detail")
            obj = _extract_json(data["choices"][0]["message"]["content"])
            raw = obj.get("details")
            # 模型偶尔把列表写成字符串，逐字符拆开会把垃圾写进人物卡
            if not isinstance(raw, list):
                _debug("detail 返回的 details 不是列表：%r" % type(raw).__name__)
                return []
            return [str(x).strip() for x in raw if str(x).strip()]
        try:
            details = ask(payload)
        except Exception as exc:
            # 思考模型偶尔把 token 全花在 reasoning 上，content 为空；关掉思考重试
            _debug("detail 第一次失败 %s，关掉思考重试" % exc)
            retry = dict(payload)
            retry["enable_thinking"] = False
            retry.pop("thinking_budget", None)
            retry["max_tokens"] = max(600, payload["max_tokens"])
            try:
                details = ask(retry)
            except Exception as exc2:
                _debug("detail 失败 %s" % exc2)
                details = []
        return details[:PERSONA_MAX]

    def ensure_detail(st):
        if gal_mock_mode():
            return
        if harness_available():
            # harness 模式没有文本 API 凭据，旁路请求会 401；交给外层 agent 的批处理
            return
        if st.get("cursor", 0) - st.get("_detail_at", 0) < DETAIL_INTERVAL:
            return
        if getattr(renpy.store, "_detail_box", None) is not None:
            return
        snapshot = json.loads(json.dumps(st))
        box = {"done": False, "result": None, "started": time.time()}

        def run():
            try:
                box["result"] = http_detail(snapshot)
            except Exception:
                box["result"] = None
            finally:
                box["done"] = True

        threading.Thread(target=run, daemon=True).start()
        renpy.store._detail_box = box

    def drain_detail(st):
        box = getattr(renpy.store, "_detail_box", None)
        if not box or not box.get("done"):
            return
        res = box.get("result")
        renpy.store._detail_box = None
        if res:
            write_persona_details(res)
            _debug("detail updated %d" % len(res))
        else:
            _debug("detail empty")
        # 失败也不要每拍重试，等下一个间隔
        st["_detail_at"] = st.get("cursor", 0)

    # 默认场景表（校园题材）。命名规则始终是 <time>_<place>，
    # 时间只用 day / dusk / night，背景图取 game/picture/scene/<time>_<place>.jpg。
    _DEFAULT_SCENES = (
        "day_classroom",
        "dusk_classroom",
        "night_classroom",
        "day_rooftop",
        "dusk_rooftop",
        "night_rooftop",
        "day_gate",
        "dusk_gate",
        "night_gate",
        "dusk_street",
        "night_street",
    )

    def _scan_scenes():
        """场景从 picture/scene/ 的文件名读，不再写在 options 里。
        文件名（去扩展名）就是场景 id，必须长成 <time>_<place>。"""
        found = []
        for base in (PIC_SCENE, os.path.join(config.basedir, "game", "scene")):
            if not os.path.isdir(base):
                continue
            for fn in sorted(os.listdir(base)):
                stem, ext = os.path.splitext(fn)
                if ext.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
                    continue
                # 只认 day / dusk / night 三种时间，其它前缀的图不参与场景
                if "_" not in stem or stem.split("_", 1)[0] not in TIME_NAMES:
                    continue
                if stem not in found:
                    found.append(stem)
        return tuple(found) or _DEFAULT_SCENES

    def _scan_moods():
        """立绘 id 以人物卡「## 立绘」为准；没有卡时扫 standing 目录。"""
        ids = []
        for e in _persona_entries():
            for sid in (e.get("standings") or {}):
                if sid not in ids:
                    ids.append(sid)
        if not ids and os.path.isdir(PIC_STANDING):
            for name in sorted(os.listdir(PIC_STANDING)):
                folder = os.path.join(PIC_STANDING, name)
                if not os.path.isdir(folder):
                    continue
                for fn in sorted(os.listdir(folder)):
                    stem, ext = os.path.splitext(fn)
                    if ext.lower() in (".jpg", ".jpeg", ".png", ".webp") and stem not in ids:
                        ids.append(stem)
        return tuple(ids) or ("1", "2", "3")

    SCENES = _scan_scenes()
    MOODS = _scan_moods()
    DEFAULT_SCENE = SCENES[0]
    DEFAULT_MOOD = MOODS[0]
    DEFAULT_TIME, DEFAULT_PLACE = (DEFAULT_SCENE.split("_", 1) + [DEFAULT_SCENE])[:2]
    TIME_PLACE = tuple(
        (s.split("_", 1)[0], s.split("_", 1)[1]) for s in SCENES if "_" in s
    )
    _TIME_PREFIXES = tuple(
        {t: 0 for t, _p in TIME_PLACE}.keys()
    )

    def _load_time_words():
        """内置中文时间词打底，game/time_words.json 可按 {"day":["早上","清晨"]} 覆盖。"""
        base = {}
        for _t, _words in TIME_WORDS:
            base[_t] = tuple(_words)
        path = os.path.join(config.basedir, "game", "time_words.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        if hasattr(data, "get"):
            for k, v in data.items():
                try:
                    words = tuple(str(x).strip() for x in list(v) if str(x).strip())
                except TypeError:
                    words = ()
                if k and words:
                    base[str(k).strip()] = words
        out = []
        for t in _TIME_PREFIXES:
            out.append((t, base.get(t) or (t,)))
        return tuple(out)

    TIME_WORDS = _load_time_words()
    _PERSONA = (
        "你是一本日式恋爱视觉小说的导演。旁白写所有人的动作和「我」的所见所想，"
        "但不替玩家做决定、不写玩家没做过的事。人物说话必须遵守人物卡，不要自行添加设定。"
    )

    _BEAT_RULE = (
        "每个 beat 最多 %d 句话、最多 %d 行，%d-%d 字。"
        % (BEAT_SENTENCES, BEAT_LINES, BEAT_MIN, BEAT_MAX)
    )
    _SHOT_RULE = (
        "shot 决定人物远近：wide 站得远（人小）、medium 常规、close 走得近（人大）。"
        "远近跟着剧情走，不要一整段都用同一个。"
    ) if SHOT_VARY else ""
    _NL = chr(10)

    def _standing_rule():
        cast_lines = []
        for e in _persona_entries():
            ids = standing_ids(e)
            if not ids:
                # 与 1.3 一致：卡里没有「## 立绘」就不给这个角色列可选 id
                continue
            cast_lines.append(
                e["name"] + "：" + "、".join(ids) + "（衣服/表情/什么时候用见上方人物卡）"
            )
        text = (
            "旁白是所有人的动作、以及「我」的心理，不属于任何角色：character 写「旁白」，"
            "standing 写 null，is_speech 写 false，游戏不显示名字也不加引号。" + _NL
            + "人物说话时 character 写人物卡里的 name，standing 是整数，只能是该角色立绘表里的 id。" + _NL
            + "人物只做动作不说话时，character 写她的名字、is_speech 写 false，standing 照常给，"
            + "这样能换她的立绘，但游戏不显示名字框。「我」只在玩家说出台词时当 character，"
            + "玩家的动作和心理都写成旁白。" + _NL
        )
        if cast_lines:
            text += (
                "可用立绘（每个角色只能选自己名下的 id；按这一拍她穿的衣服和表情挑，不要选别的角色的 id；具体衣服/表情见上方该角色的人物卡）："
                + _NL + (_NL + _NL).join(cast_lines) + _NL
            )
        text += (
            "多个角色同镜且同时说话时，character 写「A&B」，standings 写成 {\"A\":1,\"B\":2}；"
            "三个人就 A&B&C，最多三个。全员同时说同一句时 character 写「全员」，不写 standings。" + _NL
            + "同一件事、同一个场景里服装必须固定，不要换衣服；换装只能由剧情明确交代（比如隔天、换了外套），"
            + "而且要前后说得通。" + _NL
        )
        if PLAYER_SPRITE:
            text += "玩家角色「我」也有立绘：说话或做动作时可以给 standing，值为「我」的立绘 id。" + _NL
        return text

    def _player_prompt():
        for e in _persona_entries():
            if is_player_card(e):
                return e.get("body") or ""
        return ""

    def _player_rule():
        body = _player_prompt()
        if not body:
            return ""
        return (
            "【玩家角色「我」】以下是玩家角色的设定，写旁白和「我」的台词时遵守："
            + _NL + body + _NL + _NL
        )

    def _new_character_rule():
        if not AUTO_CHARACTER:
            return ""
        return (
            "【可以新增角色】剧情需要新人物时，在 JSON 里加 \"new_characters\" 数组，每项："
            '{"id":"英文小写","name":"名字","gender":"female","voice":"声音描述","aliases":["称呼"],"one_line":"一句话人设",'
            '"appearance":["外貌一","外貌二"],"speech":["说话习惯"],"taboo":["雷区"],'
            '"standings":[{"id":1,"clothes":"衣服","action":"动作","expression":"表情","when":"什么时候用"}]}。'
            + "正式角色一次最多 %d 个，id 只能是英文小写字母、数字、下划线，不能和已有角色重复；"
            % AUTO_CHARACTER_MAX
            + "临时配角（同学、店员、路人）写成 {\"temporary\":true,\"name\":\"名字\",\"voice_prompt\":\"声音描述\"}，"
            + "不建立绘、不写人物卡，最多 %d 个；临时配角只要名字和台词，不要给 standings。"
            % TEMP_CAST_MAX
            + "gender 只写 female / male / other，voice 写声音描述，standings 里的 clothes 写这套衣服。" + _NL
            + "临时配角必须给 voice_prompt，否则没有声音。" + _NL
            + "新增的角色从下一批才能出场，不要在同一个 new_characters 里让其他 beat 说她的话。"
            + _NL
        )

    _PERSONA_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,23}$")

    def _words(value, limit=6):
        if isinstance(value, str):
            value = [value]
        out = []
        try:
            raw = list(value or [])
        except TypeError:
            raw = []
        for x in raw:
            s = str(x).strip()
            if s and s not in out:
                out.append(s)
            if len(out) >= limit:
                break
        return out

    def _persona_markdown(info):
        name = info["name"]
        aliases = info.get("aliases") or []
        lines = ["---", "id: " + info["id"], "name: " + name]
        if info.get("gender"):
            lines.append("gender: " + info["gender"])
        if info.get("voice"):
            lines.append("voice: " + info["voice"])
        if info.get("voice_name"):
            lines.append("voice_name: " + info["voice_name"])
        if info.get("romance"):
            lines.append("romance: true")
        if aliases:
            lines.append("aliases: [" + ", ".join(aliases) + "]")
        lines += ["---", "", "# " + name, ""]
        if info.get("one_line"):
            lines += [info["one_line"], ""]
        lines += ["## 角色详细介绍", ""]
        for x in info.get("speech") or []:
            lines.append("- 说话方式：" + x)
        for x in info.get("taboo") or []:
            lines.append("- 雷区：" + x)
        lines += ["", "## 外貌与身体语言", ""]
        for x in info.get("appearance") or []:
            lines.append("- " + x)
        lines += ["", "## 立绘", ""]
        for sid, row in info["standings"].items():
            lines += [
                "### 立绘 " + sid, "",
                "id：" + sid,
                "衣服：" + (row.get("clothes") or ""),
                "动作：" + (row.get("action") or "自然站立"),
                "表情：" + (row.get("expression") or ""),
                "什么时候用：" + (row.get("when") or "默认"),
                "",
            ]
        lines += ["## 剧情设定", "", "- 由模型在剧情中新增。"]
        return chr(10).join(lines) + chr(10)

    _PERSONA_LOCK = threading.Lock()

    def apply_new_characters(batch):
        """模型申请新增角色时落成人物卡并注册，返回新建的 entry 列表。"""
        items = batch.get("new_characters") if hasattr(batch, "get") else None
        if not items:
            return []
        batch["new_characters"] = []
        if not AUTO_CHARACTER:
            _debug("忽略 new_characters（GALGAME_AUTO_CHARACTER=0）")
            return []
        made = []
        temps = []
        for item in list(items):
            if not hasattr(item, "get"):
                continue
            is_temp = str(item.get("temporary", "")).lower() in ("1", "true", "yes")
            name = str(item.get("name") or "").strip()
            if is_temp:
                if not name:
                    continue
                if len(temps) >= TEMP_CAST_MAX:
                    _debug("临时配角超过上限，跳过：%s" % name)
                    continue
                aliases = _words(item.get("aliases"))
                TEMP_CAST.add(name)
                vp = str(item.get("voice_prompt") or item.get("voice") or "").strip()
                if vp:
                    TEMP_CAST_VOICE[name] = vp
                for a in aliases:
                    TEMP_CAST.add(a)
                    if vp:
                        TEMP_CAST_VOICE[a] = vp
                temps.append(name)
                _debug("新增临时配角 %s（不做立绘）" % name)
                continue
            if len(made) >= AUTO_CHARACTER_MAX:
                continue
            pid = str(item.get("id") or "").strip().lower()
            if not _PERSONA_ID_RE.match(pid) or not name:
                _debug("新角色字段不合法：id=%r name=%r" % (pid, name))
                continue
            if resolve_persona(pid) or resolve_persona(name):
                _debug("新角色已存在，跳过：%s/%s" % (pid, name))
                continue
            path = os.path.join(config.basedir, "game", "persona", pid + ".md")
            # 查重、构造、插入 PERSONAS、写文件必须在同一把锁里：
            # 否则两个预取线程可能同时通过查重，或主线程迭代时字典被改
            with _PERSONA_LOCK:
                if resolve_persona(pid) or resolve_persona(name):
                    _debug("新角色已存在，跳过：%s/%s" % (pid, name))
                    continue
                if os.path.exists(path):
                    _debug("人物卡已存在，跳过：%s" % pid)
                    continue
                standings = {}
                for row in item.get("standings") or []:
                    if not hasattr(row, "get"):
                        continue
                    sid = str(row.get("id") or "").strip()
                    if not sid.isdigit() or sid in standings:
                        continue
                    standings[sid] = {
                        "character": name,
                        "clothes": str(row.get("clothes") or "").strip(),
                        "action": str(row.get("action") or "").strip(),
                        "expression": str(row.get("expression") or "").strip(),
                        "when": str(row.get("when") or "").strip(),
                    }
                if not standings:
                    standings["1"] = {"character": name, "action": "", "expression": "", "when": "默认"}
                info = {
                    "id": pid,
                    "name": name,
                    "gender": _gender_en(item.get("gender")),
                    "voice": str(item.get("voice") or "").strip(),
                    "voice_name": str(item.get("voice_name") or "").strip(),
                    "romance": str(item.get("romance", "")).lower() in ("1", "true", "yes"),
                    "aliases": _words(item.get("aliases")),
                    "one_line": str(item.get("one_line") or "").strip(),
                    "appearance": _words(item.get("appearance")),
                    "speech": _words(item.get("speech")),
                    "taboo": _words(item.get("taboo")),
                    "standings": standings,
                }
                try:
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    card_text = _persona_markdown(info)
                    _atomic_write_text(path, card_text)
                except OSError as exc:
                    _debug("新角色写盘失败 %s：%s" % (pid, exc))
                    continue
                entry = {
                    "id": pid,
                    "name": name,
                    "illustration": pid,
                    "aliases": info["aliases"],
                    "gender": info["gender"],
                    "voice": info["voice"],
                    "voice_name": info["voice_name"],
                    "lead": False,
                    "romance": info["romance"],
                    "file": pid + ".md",
                    "dir": pid,
                    "standings": standings,
                    # 同一局立刻要用：写盘后的正文直接进内存，生图和子智能体不用等重启
                    "body": _strip_card_frontmatter(card_text),
                }
                TEMP_CAST.discard(name)
                PERSONAS[name] = entry
                PERSONAS[pid] = entry
                PERSONAS[_pkey(name)] = entry
                PERSONAS[_pkey(pid)] = entry
                for a in info["aliases"]:
                    PERSONAS[a] = entry
                    PERSONAS[_pkey(a)] = entry
            made.append(entry)
            _debug("新增角色 %s(%s)，立绘 %s" % (name, pid, ",".join(standings.keys())))
        if made:
            _queue_new_character_art(made)
        return made

    def _queue_new_character_art(entries):
        if GEN_STANDING not in (1, 2):
            return
        if getattr(renpy.store, "_art_box", None):
            return
        jobs = []
        for e in entries:
            for sid in standing_ids(e):
                if standing_file(e["name"], sid) or standing_file(e["id"], sid):
                    continue
                jobs.append((
                    "standing", e["id"] + "/" + str(sid),
                    art_standing_prompt(e["name"], sid),
                    _cfg("GALGAME_IMAGE_SIZE_PORTRAIT", "960*1440"), GEN_STANDING,
                ))
        if not jobs:
            return
        box = {"done": False, "started": time.time()}
        renpy.store._art_box = box
        t = threading.Thread(target=_guard(lambda: _run_art(jobs), box))
        t.daemon = True
        t.start()
        _debug("新角色立绘排队 %d 张" % len(jobs))

    _BGM_EXAMPLE = BGM_IDS[0] if BGM_IDS else "null"

    def _format_spec(director=False):
        line_id = '"line_id":1,' if director else ""
        # 每次请求现拼：ENDLESS 可在运行中热更，结局规则不能冻结在 init 期
        return (
        "只输出 JSON，不要 Markdown 代码块。格式：" + _NL
        + '{"plan":"这一段想写什么，40字以内",' + _NL
        + ' "chapter":"第一章",' + _NL
        + ' "scene_plan":[{"at":0,"time":"' + DEFAULT_TIME + '","place":"' + DEFAULT_PLACE + '"}],' + _NL
        + ' "beats":[{' + line_id + '"character":"' + HEROINE_NAME + '","standing":1,"bgm":' + _BGM_EXAMPLE + ',"is_speech":true,"text":"' + str(BEAT_MIN) + "-" + str(BEAT_MAX) + '字","time":"' + DEFAULT_TIME + '","place":"' + DEFAULT_PLACE + '"},{"character":"旁白","standing":null,"bgm":null,"is_speech":false,"text":"动作或心理","time":"' + DEFAULT_TIME + '","place":"' + DEFAULT_PLACE + '"}],' + _NL
        + ' "choices":[{"label":"不超过6字","hint":"不超过20字","add":整数,"target":"可攻略角色名字，可省略","flag":"可选英文标记","react":"选完后立刻显示的一句话"}],' + _NL
        + '}' + _NL
        + "背景由时间加地点决定，可用组合只有：" + "、".join(t + "+" + p for t, p in TIME_PLACE) + "。" + _NL
        + "time 只能是 day、dusk、night。镜头、人物表情、说话者或视点变化都沿用当前背景。只有正文明确换了时间或地点时才在 scene_plan 写一项，at 为该拍的零基序号，time/place 必须是可用背景组合。没有转场时 scene_plan 为空数组。只有人物台词明确换了叙事视点才写 viewpoint_changed:true。" + _NL
        + ("BGM 写在 beat 的 bgm 里，只能选上面列出的 id；0 表示停，null 表示沿用上一拍。能沿用就沿用，一批最多换一次，不要每拍都换。" if BGM_IDS else "没有 BGM 文件时 bgm 一律写 null。") + _NL
        + "is_speech 为 true 时 text 只写这个角色此刻说出口的第一人称台词，不要自带引号，游戏会加「」；"
        + "不要写「她看了我一眼」「某某靠在栏杆上」这类第三人称叙述，动作和神态放进旁白拍。"
        + "is_speech 为 false 时不加引号，可以写动作或旁白。" + _NL
        + "每一批至少给一句人物台词（is_speech 为 true），不要整批都是旁白；旁白和台词大致各占一半。" + _NL
        + "人物卡里出现别名时，character 一律写人物卡的 name，不要写别名。只有剧情里确实出现假扮时，才把 character 写成被假扮者的名字；不要为了展示这个机制而主动安排假扮。" + _NL
        + "一次给 %d 个 beats，把这一段连续剧情写完。%s" + _NL
        + "每一批必须推进一个新的具体事实、关系变化或线索；不要把最近发生过的场面换个说法再写一遍，"
        + "上一批已经解决的冲突不要再重复。" + _NL
        + "%s" + _NL
        + "choices 的 add 默认加在女主角身上；要给别的可攻略角色加，写 \"target\":\"她的名字\"；不可攻略角色不要写 target。" + _NL
        + "选择密度：这一块最多 %d 次选择；距离上次选择不足 %d 拍时不要给 choices；整体保持每 %d 拍 %d-%d 次选择。" + _NL
        + ("chapter 是当前章节名，写成「第N章 一个具体意象」。剧情推进到新阶段时更新；故事没有结局，不要写「完」或收束。"
           if ENDLESS else
           "chapter 是当前章节名，写成「第N章 一个具体意象」。故事可以收束：要结束这一部时，给 \"ending\":\"结局标题\"，"
           "并把最后几拍写成收束，不要再开新线。")
        ) % (
            PLAN_AHEAD, _BEAT_RULE, _SHOT_RULE, PER_BLOCK_MAX,
            CHOICE_GAP, CHOICE_WINDOW, CHOICE_MIN, CHOICE_MAX,
        )

    _chars = {}

    NARRATOR = "旁白"

    def is_narrator(name):
        """旁白是一个独立类型：不显示名字，不加引号，不换立绘。
        模型给 null、空串、旁白、narrator 都算旁白。"""
        s = str(name if name is not None else "").strip().lower()
        return s in ("", "null", "none", "旁白", "narrator", "无")

    def gal_literal_text(value):
        return str(value).replace("[", "[[").replace("{", "{{")

    def gal_literal_tags(value):
        return str(value).replace("{", "{{")

    def _who(beat):
        name = beat.get("character") or beat.get("speaker")
        if is_narrator(name):
            who = getattr(renpy.store, "narrator", None)
            if who is not None:
                return who
            if "__narrator__" not in _chars:
                _chars["__narrator__"] = Character(None, who_color="#c9a86a")
            return _chars["__narrator__"]
        name = str(name).strip()
        if name not in _chars:
            _chars[name] = Character(gal_literal_text(name), who_color="#c9a86a")
        return _chars[name]

    def heroine_affection0():
        return int(HEROINE.get("affection", 0)) if HEROINE else 0

    def is_romance(persona):
        if not persona:
            return False
        if persona.get("lead"):
            return bool(persona.get("romance", True))
        return bool(persona.get("romance"))

    def romance_entries():
        return [e for e in _persona_entries() if is_romance(e)]

    def affection_of(st, name):
        cur = st.get("affections") or {}
        if name in cur:
            return int(cur[name])
        p = resolve_persona(name)
        return int(p.get("affection", 0)) if p else 0

    def new_state():
        renpy.store._cur_scene = None
        renpy.store._cur_bgm = None
        return {
            "run_id": uuid.uuid4().hex,
            "turn": 0,
            "affection": heroine_affection0(),
            "affections": {e["name"]: int(e.get("affection", 0)) for e in romance_entries()},
            "flags": [],
            "history": [],
            "scene": DEFAULT_SCENE,
            "mood": DEFAULT_MOOD,
            "bgm": None,
            "_bgm_turn": -99,
            "chapter": _chapter_title(),
            "cursor": 0,
            "path": [],
            "chapter_start": 1,
            "last": None,
            "last_choice_turn": -99,
            "_detail_at": 0,
        }

    def _affection_brief(st):
        """每个可攻略角色单独说初始值和当前值，不可攻略角色明说没有好感度。"""
        lines = []
        for e in romance_entries():
            a = affection_of(st, e["name"])
            lines.append(
                "%s：初始 %d，当前 %d，处于「%s」阶段；这一阶段%s" % (
                    e["name"], int(e.get("affection", 0)), a, _stage(a), _stage_hint(a))
            )
        non = [e["name"] for e in _persona_entries() if not is_romance(e) and not is_player_card(e)]
        text = ""
        if lines:
            text += "可攻略角色与好感度（初始值是起点，已过去；当前值才决定她现在怎么说话）：" + chr(10)
            text += chr(10).join("- " + x for x in lines) + chr(10)
            text += "只按当前值写态度，不要把好感度数字写进正文或选项。" + chr(10)
        if non:
            text += ("不可攻略角色：" + "、".join(non)
                     + "。她们没有好感度，不写恋爱向的心动、试探和暧昧，按人物卡的身份与关系写。" + chr(10))
        return text

    def _stage_hint(a):
        if a >= 80:
            return "允许直接的亲密和依赖，但仍保留她自己的说话方式，不要突然变成另一个人。"
        if a >= 60:
            return "允许靠近、试探和含糊的默许，但不主动说破。"
        if a >= 40:
            return "开始在意对方，会记住细节，被点破会否认。"
        if a >= 20:
            return "能主动搭话、借东西，偶尔说一句没头没尾的观察。"
        return "只回答必要的话，不主动，不接受明显的帮忙。"

    def _stage(a):
        if a >= 80:
            return "恋人"
        if a >= 60:
            return "暧昧"
        if a >= 40:
            return "心动"
        if a >= 20:
            return "熟悉"
        return "陌生"

    # ---------- 显示 ----------

    def standing_dir(persona, name=None):
        """立绘目录名：人物卡的英文 id（picture/standing/<id>/），没有人物卡就用说话人本身。"""
        if persona:
            return persona.get("dir") or persona.get("id") or persona.get("name")
        return name or HEROINE_NAME

    def standing_key(character, sid):
        p = resolve_persona(character)
        return "standing " + str(standing_dir(p, character)) + " " + str(sid)

    def standing_file(character, sid):
        """返回立绘文件的相对路径（相对 game/），找不到返回 None。"""
        alias = {"全员": "all", "我": "me"}
        p = resolve_persona(character)
        dirs = []
        if str(character) in alias:
            dirs.append(alias[str(character)])
        if p:
            dirs.append(p.get("dir") or p.get("name") or p.get("id"))
            if p.get("illustration"):
                dirs.append(p["illustration"])
        if character:
            dirs.append(str(character))
        seen = set()
        for d in dirs:
            if not d or d in seen:
                continue
            seen.add(d)
            for base in ("picture/standing", "illustration"):
                for ext in (".webp", ".png", ".jpg", ".jpeg"):
                    rel = base + "/" + d + "/" + str(sid) + ext
                    if os.path.exists(os.path.join(config.basedir, "game", rel.replace("/", os.sep))):
                        return rel
        return None

    def scene_file(scene):
        for base in ("picture/scene", "scene"):
            for ext in (".jpg", ".jpeg", ".webp", ".png"):
                rel = base + "/" + scene + ext
                if os.path.exists(os.path.join(config.basedir, "game", rel.replace("/", os.sep))):
                    return rel
        return None

    def _hero_at(count, index):
        table = {
            1: (renpy.store.heroine_pos,),
            2: (renpy.store.heroine_left, renpy.store.heroine_right),
            3: (renpy.store.heroine_left3, renpy.store.heroine_center3, renpy.store.heroine_right3),
        }
        row = table.get(count) or table[3]
        return row[min(index, len(row) - 1)]

    def _parse_cast(beat):
        """把 character 拆成角色名列表。支持 A&B、数组、全员。"""
        raw = beat.get("character")
        if raw is None:
            raw = beat.get("speaker")
        if hasattr(raw, "__iter__") and not isinstance(raw, str):
            names = [str(x).strip() for x in raw if str(x).strip()]
        else:
            text = str(raw or "").strip()
            if text in ("全员", "all", "ALL", "全体"):
                return ["全员"], "全员"
            names = [x.strip() for x in re.split(r"[&＆、,，/]", text) if x.strip()]
        return names, "&".join(names)

    def show_beat(beat):
        scene = beat.get("scene")
        if scene in SCENES and scene != getattr(renpy.store, "_cur_scene", None):
            renpy.scene()
            rel = scene_file(scene)
            # 背景走 stage_bg 这个常驻 screen，运行时刚生成的图也能立刻用
            renpy.store._dyn_bg = Image(rel) if rel else None
            if not renpy.get_screen("stage_bg"):
                renpy.show_screen("stage_bg")
            renpy.store._cur_scene = scene
            st["_scene_turn"] = beat.get("turn", 0)
            renpy.store._cur_actor = None
            renpy.transition(Dissolve(0.2))
        cast = {}
        raw_cast = beat.get("standings")
        if hasattr(raw_cast, "get"):
            cast = {str(k): v for k, v in raw_cast.items() if v is not None}
        elif beat.get("standing") is not None:
            ch = beat.get("character") or beat.get("speaker")
            cast = {str(ch): beat.get("standing")}
        if cast:
            names = list(cast.keys())[:3]
            # shot 必须进缓存键：同阵容同立绘换镜头时也要重建舞台
            shot = beat.get("shot", "medium")
            key = str(shot) + "|" + "|".join("%s:%s" % (n, cast[n]) for n in names)
            if getattr(renpy.store, "_cur_actor", None) != key:
                items = []
                meta = []
                need_probe = False
                for i, name in enumerate(names):
                    rel = standing_file(name, cast[name])
                    if not rel:
                        continue
                    if len(names) == 1:
                        hero_map = {
                            "wide": renpy.store.heroine_far,
                            "medium": renpy.store.heroine_pos,
                            "close": renpy.store.heroine_near,
                        }
                        base_at = hero_map.get(shot, renpy.store.heroine_pos)
                    else:
                        base_at = _hero_at(len(names), i)
                    base_x, base_z = frame_base_layout(len(names), i, shot)
                    w, h = frame_image_size(rel)
                    plan = frame_plan_for(name, len(names), i, w, h)
                    at = frame_transform(rel, base_x, base_z, plan) if plan else base_at
                    if plan:
                        _debug("frame cached %s dx=%s dy=%s zoom=%s" % (
                            name, plan.get("dx"), plan.get("dy"), plan.get("zoom"),
                        ))
                    else:
                        need_probe = True
                    items.append((Image(rel), at))
                    meta.append({
                        "id": name, "rel": rel, "slot": i, "count": len(names),
                        "x": base_x, "zoom": base_z, "w": w, "h": h, "at": base_at,
                    })
                renpy.store._dyn_cast = items
                renpy.store._dyn_cast_meta = meta
                # 新角色没有缓存方案时，等这一拍画出来再截图；有方案就直接套用
                if need_probe and frame_check_on():
                    renpy.store._frame_probe = {
                        "cast_key": key, "meta": meta, "ts": time.time(),
                    }
                else:
                    renpy.store._frame_probe = None
                if not renpy.get_screen("stage_hero"):
                    renpy.show_screen("stage_hero")
                renpy.store._cur_actor = key

    def preload_all():
        for name in ("bg " + DEFAULT_SCENE, standing_key(HEROINE_NAME, default_standing(HEROINE))):
            try:
                renpy.cache_pin(renpy.displayable(name))
            except Exception:
                pass

    def opening_records():
        """开局前两拍本地给出，保证第一屏零等待。
        优先用 game/opening.json（作者或技能写的开场），没有就取章节卡的「开头」。"""
        title = _chapter_title()
        begin = _chapter_begin()
        items = _read_opening_file()
        if not items:
            items = [{"text": begin or (HEROINE_NAME + "还没出现。故事从这一天开始。")}]
        out = []
        for i, b in enumerate(items):
            text = (b.get("text") or "").strip()
            if not text:
                continue
            ch = b.get("character") or b.get("speaker")
            if is_narrator(ch):
                ch = NARRATOR
                sid = None
            else:
                ch = str(ch).strip()
                raw = b.get("standing")
                if raw is None:
                    raw = b.get("mood")
                sid = "" if raw is None else str(raw).strip()
                p = resolve_persona(ch)
                if not sid or sid not in standing_ids(p):
                    sid = standing_value(default_standing(p))
                else:
                    sid = standing_value(sid)
            out.append({
                "turn": len(out) + 1,
                "path": [],
                "chapter": title,
                "character": ch,
                "speaker": "" if ch == NARRATOR else ch,
                "is_speech": bool(b.get("is_speech", ch != NARRATOR)),
                "portrait": ch,
                "standing": sid,
                "text": text,
                "scene": b.get("scene") if b.get("scene") in SCENES else DEFAULT_SCENE,
                "mood": sid,
                "bgm": _bgm_norm(b.get("bgm")) if b.get("bgm") not in (None, "") else None,
                "shot": b.get("shot", "medium"),
                "affection": 0,
                "flags": [],
            })
            present = b.get("present_characters")
            if isinstance(present, (builtins.list, list)) and all(isinstance(name, str) for name in present):
                out[-1]["present_characters"] = list(present)
        return out or [
            {
                "turn": 1,
                "path": [],
                "chapter": title,
                "character": NARRATOR,
                "speaker": "",
                "is_speech": False,
                "portrait": NARRATOR,
                "standing": None,
                "text": begin or (HEROINE_NAME + "还没出现。故事从这一天开始。"),
                "scene": DEFAULT_SCENE,
                "mood": None,
                "bgm": None,
                "shot": "medium",
                "affection": 0,
                "flags": [],
            }
        ]

    def _read_opening_file():
        path = os.path.join(config.basedir, "game", "opening.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return []
        items = data.get("beats") if hasattr(data, "get") else data
        try:
            raw = list(items)
        except TypeError:
            return []
        return [x for x in raw if hasattr(x, "get")]

    def _chapter_title():
        if not ENABLE_CHAPTER:
            return ""
        cur = _current_chapter()
        return cur.get("title") or "第一章"

    def _chapter_begin():
        if not ENABLE_CHAPTER:
            return ""
        return (str(_current_chapter().get("begin") or "")).strip()

    _chapter_cache = [None, None, None]

    def _current_chapter():
        data = load_chapters() or {}
        no = data.get("current", 1)
        try:
            mtime = os.path.getmtime(chapters_path())
        except OSError:
            mtime = None
        # 同号下 chapters.json 被改过（title/begin）也要重取
        if _chapter_cache[0] == no and _chapter_cache[1] == mtime and _chapter_cache[2] is not None:
            return _chapter_cache[2]
        cur = chapter_of(data, no) or {}
        _chapter_cache[0] = no
        _chapter_cache[1] = mtime
        _chapter_cache[2] = cur
        return cur

    def play_opening_records(st, count):
        for rec in (st.get("history") or [])[:max(0, int(count))]:
            st["cursor"] = rec.get("turn", st["cursor"])
            play_record(rec, st)
        return st

    def choice_target(choice):
        target = str(choice.get("target") or "").strip()
        return target or HEROINE_NAME

    def apply_choice(st, choice):
        target = choice_target(choice)
        p = resolve_persona(target)
        name = (p or {}).get("name") or target
        add = int(choice.get("add", 0) or 0)
        if p and is_romance(p):
            cur = st.setdefault("affections", {})
            base = int(cur.get(name, p.get("affection", 0)))
            cur[name] = max(0, min(100, base + add))
            if name == HEROINE_NAME:
                st["affection"] = cur[name]
        else:
            _debug("非攻略角色不结算好感：%s" % name)
        flag = choice.get("flag")
        if flag and flag not in st["flags"]:
            st["flags"].append(flag)
        st["last_choice_turn"] = st.get("cursor", 0)
        if choice.get("next"):
            st["last"] = choice["next"]

    def snapshot_choice_state(st):
        """Capture the state fields an option can change, so BACK can undo it."""
        keys = ("affection", "affections", "flags", "last_choice_turn", "last",
                "summary", "summary_until")
        return {
            key: json.loads(json.dumps(st[key]))
            for key in keys
            if key in st
        }

    def restore_choice_state(st, snapshot):
        """Restore option effects while preserving unrelated progress."""
        keys = ("affection", "affections", "flags", "last_choice_turn", "last",
                "summary", "summary_until")
        for key in keys:
            if key in snapshot:
                st[key] = json.loads(json.dumps(snapshot[key]))
            elif key in ("summary", "summary_until"):
                # 老存档没有摘要快照：不要误删当前摘要。
                continue
            else:
                st.pop(key, None)

    # ---------- 语音 ----------

    VOICE_PENDING = set()
    VOICE_PENDING_LOCK = threading.Lock()
    _VOICE_ID_LOCK = threading.RLock()

    def _safe_name(value, prefix="role"):
        """磁盘目录名只允许普通路径段；异常值改成哈希，防止 ../ 越界。"""
        s = str(value or "").strip()
        bad = (
            not s or s in (".", "..")
            or "/" in s or "\\" in s or ":" in s or "\x00" in s
            or os.path.isabs(s) or s.endswith(".") or s.endswith(" ")
        )
        if bad:
            return prefix + "_" + hashlib.md5(s.encode("utf-8")).hexdigest()[:10]
        return s

    def _safe_under(base, rel):
        """把 rel 拼到 base 下；越界返回 None。"""
        base_abs = os.path.abspath(base)
        full = os.path.abspath(os.path.join(base_abs, str(rel or "").replace("/", os.sep)))
        if full != base_abs and not full.startswith(base_abs + os.sep):
            return None
        return full

    def _voice_pending_has(rel):
        with VOICE_PENDING_LOCK:
            return rel in VOICE_PENDING

    def _voice_pending_add(rel):
        with VOICE_PENDING_LOCK:
            VOICE_PENDING.add(rel)

    def _voice_pending_remove(rel):
        with VOICE_PENDING_LOCK:
            VOICE_PENDING.discard(rel)

    def _voice_dir(character):
        p = resolve_persona(character)
        if p:
            return _safe_name(p["id"], "role")
        if character in TEMP_CAST:
            return "temp_" + hashlib.md5(str(character).encode("utf-8")).hexdigest()[:6]
        return "misc_" + hashlib.md5(str(character).encode("utf-8")).hexdigest()[:6]

    def _voice_prompt(character):
        p = resolve_persona(character)
        if p and p.get("voice"):
            return p["voice"]
        return TEMP_CAST_VOICE.get(character, "")

    def _voice_name(character):
        """百炼文生声用固定音色名；人物卡 frontmatter 的 voice_name 优先。"""
        p = resolve_persona(character)
        if p and p.get("voice_name"):
            return p["voice_name"]
        return VOICE_NAME

    gal_voice_reference_cache = {}
    gal_voice_reference_lock = threading.Lock()

    def gal_voice_reference_digest(ref):
        if not ref:
            return ""
        try:
            with gal_voice_reference_lock:
                stat = os.stat(ref)
                stamp = (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
                cached = gal_voice_reference_cache.get(ref)
                if cached and cached[0] == stamp:
                    return cached[1]
                digest = hashlib.sha256()
                with open(ref, "rb") as source:
                    for chunk in iter(lambda: source.read(65536), b""):
                        digest.update(chunk)
                value = digest.hexdigest()
                gal_voice_reference_cache[ref] = (stamp, value)
                return value
        except OSError:
            return "unavailable"

    def _voice_ref(character):
        if not os.path.isdir(VOICE_EXAMPLE_DIR):
            return None
        names = []
        p = resolve_persona(character)
        if p:
            names.append(p["name"])
            names.append(p["id"])
        names.append(str(character))
        for n in names:
            for ext in (".wav", ".mp3", ".m4a", ".ogg"):
                path = _safe_under(VOICE_EXAMPLE_DIR, n + ext)
                if not path or os.path.islink(path):
                    continue
                if os.path.exists(path):
                    return path
        return None

    def _audio_data(v):
        """纯 base64 或 data:audio/...;base64, 都还原成字节。"""
        if not isinstance(v, str) or not v:
            return None
        if v.startswith("data:"):
            v = v.split(",", 1)[-1]
        try:
            return base64.b64decode(v)
        except Exception:
            return None

    def _audio_from(data, trusted_origin="", request_id=""):
        """各家返回结构不同：bytes / url / base64 / data URI 都认。"""
        if not hasattr(data, "get"):
            return None
        for item in data.get("choices") or []:
            if isinstance(item, Mapping) and isinstance(item.get("message"), Mapping):
                got = _audio_from(item["message"], trusted_origin, request_id)
                if got:
                    return got
        for k in ("audio", "b64_json", "data"):
            v = data.get(k)
            if hasattr(v, "get"):
                got = _audio_from(v, trusted_origin, request_id)
                if got:
                    return got
            elif isinstance(v, str):
                if v.startswith("http"):
                    return _read_url(v, trusted_origin=trusted_origin, voice_request_id=request_id)
                got = _audio_data(v)
                if got:
                    return got
        out = data.get("output")
        if hasattr(out, "get"):
            got = _audio_from(out, trusted_origin, request_id)
            if got:
                return got
            for item in (out.get("results") or out.get("choices") or []):
                got = _audio_from(item, trusted_origin, request_id)
                if got:
                    return got
        for k in ("url", "audio_url"):
            v = data.get(k)
            if isinstance(v, str) and v.startswith("http"):
                return _read_url(v, trusted_origin=trusted_origin, voice_request_id=request_id)
        return None

    def _is_audio_bytes(raw, ctype):
        if str(ctype or "").lower().startswith("audio/"):
            return True
        if raw[:4] in (b"RIFF", b"OggS"):
            return True
        if raw[:3] == b"ID3":
            return True
        return raw[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")

    def voice_log_host(url):
        try:
            host = urllib.parse.urlsplit(url).hostname or ""
        except ValueError:
            return "invalid"
        return host if re.fullmatch(r"[A-Za-z0-9.:-]{1,253}", host) else "invalid"

    def dashscope_sse_wav(raw):
        """Decode Qwen3-TTS-Flash HTTP SSE audio into a 24 kHz mono WAV."""
        chunks = []
        finished = False
        for line in raw.splitlines():
            if not line.startswith(b"data:"):
                continue
            value = line[5:].strip()
            if value == b"[DONE]":
                break
            event = json.loads(value)
            code = event.get("code")
            if code:
                safe_code = str(code)
                if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", safe_code):
                    safe_code = "unknown"
                raise RuntimeError("DashScope SSE error_code=" + safe_code)
            output = event.get("output") or {}
            audio = output.get("audio") or {}
            if audio.get("data"):
                chunks.append(base64.b64decode(audio["data"], validate=True))
            finished = finished or output.get("finish_reason") == "stop"
        if not chunks or not finished:
            raise RuntimeError("DashScope SSE 音频缺失或传输未完成")
        pcm = b"".join(chunks)
        if pcm.startswith(b"RIFF") and pcm[8:12] == b"WAVE":
            return _fix_wav_bytes(pcm)
        if len(pcm) % 2:
            raise RuntimeError("DashScope SSE PCM 长度无效")
        import io
        import wave
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as output:
            output.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
            output.writeframes(pcm)
        return buffer.getvalue()

    def _post_audio(url, payload, key, timeout, dashscope_sse=False):
        _check_url(url, allow_private=True)
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), method="POST"
        )
        req.add_header("Content-Type", "application/json")
        if dashscope_sse:
            req.add_header("X-DashScope-SSE", "enable")
        if key:
            req.add_header("Authorization", "Bearer " + key)
        request_id = uuid.uuid4().hex
        gal_request_log("event=voice.request status=start rid=%s endpoint_host=%s model=%s job=%s" %
               (request_id, voice_log_host(url), gal_log_model_name(payload.get("model")), getattr(gal_voice_log_context, "job", "-")))
        started = time.monotonic()
        try:
            with _open_url(req, timeout, allow_private=True) as resp:
                raw = _read_limited(resp, 50 * 1024 * 1024, time.time() + timeout)
                ctype = (resp.headers.get("Content-Type") or "").lower()
                http_code = resp.getcode()
        except urllib.error.HTTPError as exc:
            with exc:
                try:
                    detail = json.loads(exc.read(8192).decode("utf-8", "replace"))
                    detail = detail.get("error", detail)
                    code = str(detail.get("code") or "") if isinstance(detail, Mapping) else ""
                except (OSError, ValueError, AttributeError):
                    code = ""
                code = code if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]{0,63}", code) else ""
                remote_id = exc.headers.get("x-request-id", "") if exc.headers else ""
                remote_id = remote_id if re.fullmatch(r"[A-Za-z0-9_-]{1,96}", remote_id) else ""
                gal_request_log("event=voice.request status=http_error rid=%s http_code=%s error_code=%s server_request_id=%s latency_ms=%d" %
                       (request_id, exc.code, code, remote_id, (time.monotonic() - started) * 1000))
                raise RuntimeError("语音请求失败 HTTP %s %s" % (exc.code, code)) from None
        except Exception as exc:
            gal_request_log("event=voice.request status=error rid=%s error_type=%s latency_ms=%d" %
                            (request_id, type(exc).__name__, (time.monotonic()-started)*1000))
            raise
        gal_request_log("event=voice.request status=response rid=%s http_code=%s latency_ms=%d bytes=%d" %
               (request_id, http_code, (time.monotonic() - started) * 1000, len(raw)))
        if _is_audio_bytes(raw, ctype):
            return raw
        if dashscope_sse and ctype.split(";", 1)[0].strip() == "text/event-stream":
            return dashscope_sse_wav(raw)
        data = json.loads(raw.decode("utf-8"))
        got = _audio_from(data, url, request_id)
        if got:
            return got
        raise RuntimeError("语音接口没有返回音频")

    def _clone_base():
        """声音复刻只能用业务空间专属域名。"""
        if "/api/v1/" in VOICE_ENDPOINT:
            return VOICE_ENDPOINT.split("/api/v1/", 1)[0].rstrip("/")
        if VOICE_CLONE_WS:
            return "https://%s.cn-beijing.maas.aliyuncs.com" % VOICE_CLONE_WS.strip()
        raise RuntimeError("声音复刻需要填 GALGAME_VOICE_CLONE_WORKSPACE")

    def _voice_ids():
        try:
            with open(VOICE_ID_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if hasattr(data, "get") else {}
        except Exception:
            return {}

    def _drop_voice_id(key):
        with _VOICE_ID_LOCK:
            data = _voice_ids()
            if key in data:
                data.pop(key, None)
                try:
                    _atomic_write_text(VOICE_ID_FILE, json.dumps(data, ensure_ascii=False, indent=2))
                except OSError as exc:
                    _debug("voice id drop fail %s" % exc)

    def _save_voice_id(key, vid):
        with _VOICE_ID_LOCK:
            data = _voice_ids()
            data[key] = vid
            try:
                _atomic_write_text(VOICE_ID_FILE, json.dumps(data, ensure_ascii=False, indent=2))
            except OSError as exc:
                _debug("voice id 写入失败 %s" % exc)

    def gal_clone_cache_key(character, ref):
        identity = [_voice_dir(character), gal_voice_reference_digest(ref),
                    _clone_base(), VOICE_CLONE_MODEL, VOICE_CLONE_PREFIX,
                    hashlib.sha256(VOICE_KEY.encode("utf-8")).hexdigest()]
        return "v2:" + hashlib.sha256(json.dumps(identity).encode("utf-8")).hexdigest()

    def _clone_voice(character, ref, key):
        """百炼声音复刻：create_voice 后轮询 query_voice 到 OK，结果缓存在 voice_ids.json。"""
        cached = _voice_ids().get(key)
        if cached:
            return cached
        ext = os.path.splitext(ref)[1].lstrip(".").lower()
        mime = {
            "wav": "audio/wav", "mp3": "audio/mpeg",
            "m4a": "audio/mp4", "ogg": "audio/ogg",
        }.get(ext, "audio/wav")
        with open(ref, "rb") as f:
            audio_uri = "data:%s;base64,%s" % (
                mime, base64.b64encode(f.read()).decode("ascii")
            )
        prefix = "".join(c for c in (VOICE_CLONE_PREFIX + _voice_dir(character)) if c.isalnum())[:10]
        url = _clone_base() + "/api/v1/services/audio/tts/customization"
        data = _post_json(url, {
            "model": "voice-enrollment",
            "input": {
                "action": "create_voice",
                "target_model": VOICE_CLONE_MODEL,
                "prefix": prefix or "galgame",
                "audio": audio_uri,
            },
        }, VOICE_KEY, VOICE_TIMEOUT, request_kind="voice_enrollment")
        out = data.get("output") or {}
        vid = out.get("voice_id")
        if not vid:
            raise RuntimeError("复刻音色创建失败：%s" % str(data)[:300])
        _debug("clone voice created %s=%s" % (key, vid))
        deadline = time.time() + VOICE_TIMEOUT
        while True:
            status = ""
            try:
                q = _post_json(url, {
                    "model": "voice-enrollment",
                    "input": {"action": "query_voice", "voice_id": vid},
                }, VOICE_KEY, VOICE_TIMEOUT, request_kind="voice_enrollment")
                status = str((q.get("output") or {}).get("status") or "").upper()
            except Exception as exc:
                _debug("query voice fail: %s" % exc)
            if status == "OK":
                break
            if status == "UNDEPLOYED":
                raise RuntimeError("复刻音色未通过审核")
            if time.time() >= deadline:
                _debug("voice %s 状态 %s，超时先用" % (vid, status or "unknown"))
                break
            time.sleep(3)
        if status == "OK":
            _save_voice_id(key, vid)
        else:
            _debug("voice %s 状态 %s 未就绪，本次不缓存" % (vid, status or "unknown"))
        return vid

    def _ds_synth(text, voice, base):
        url = base + "/api/v1/services/audio/tts/SpeechSynthesizer"
        payload = {
            "model": VOICE_CLONE_MODEL,
            "input": {
                "text": text,
                "voice": voice,
                "format": "wav",
                "sample_rate": 24000,
            },
        }
        return _post_audio(url, payload, VOICE_KEY, VOICE_TIMEOUT)

    def _voice_bytes(text, character):
        desc = _voice_prompt(character)
        if VOICE_API == "mimo":
            audio = {"format": VOICE_FORMAT}
            if VOICE_MODE == "clone":
                ref = _voice_ref(character)
                if not ref:
                    raise ValueError("MiMo 声音复刻需要 WAV 或 MP3 参考音频")
                ext = os.path.splitext(ref)[1].lower()
                if ext not in (".wav", ".mp3") or os.path.getsize(ref) > 10 * 1024 * 1024:
                    raise ValueError("MiMo 参考音频须为不超过 10 MiB 的 WAV 或 MP3")
                with open(ref, "rb") as stream:
                    sample = base64.b64encode(stream.read()).decode("ascii")
                audio["voice"] = sample
            return _post_audio(VOICE_ENDPOINT, {"model": VOICE_MODEL,
                "messages": [{"role": "assistant", "content": text}],
                "audio": audio, "stream": False}, VOICE_KEY, VOICE_TIMEOUT)
        if VOICE_API == "openai_official":
            voice = _voice_name(character)
            if VOICE_MODE == "clone":
                if not voice.startswith("voice_"):
                    raise ValueError("请为人物填写已授权的 OpenAI 自定义语音 ID")
                voice = {"id": voice}
            elif not voice or voice == "Cherry":
                voice = "alloy"
            return _post_audio(VOICE_ENDPOINT, {"model": VOICE_MODEL, "input": text,
                "voice": voice, "response_format": VOICE_FORMAT}, VOICE_KEY, VOICE_TIMEOUT)
        if VOICE_API == "dashscope":
            # 百炼：文生声走 multimodal-generation，声生声走声音复刻 + SpeechSynthesizer。
            if VOICE_MODE == "clone":
                ref = _voice_ref(character)
                if ref:
                    key = gal_clone_cache_key(character, ref)
                    try:
                        return _ds_synth(text, _clone_voice(character, ref, key), _clone_base())
                    except Exception:
                        _drop_voice_id(key)
                        raise
                if not desc:
                    raise RuntimeError("声生声缺少参考音频和声音描述：%s" % character)
                _debug("voice %s 没有参考音频，退回文生声" % character)
            payload = {
                "model": VOICE_MODEL,
                "input": {
                    "text": text,
                    "voice": _voice_name(character),
                    "language_type": VOICE_LANG,
                },
            }
            return _post_audio(VOICE_ENDPOINT or VOICE_DS_URL, payload, VOICE_KEY, VOICE_TIMEOUT,
                               dashscope_sse=VOICE_MODEL == "qwen3-tts-flash")
        if not VOICE_ENDPOINT:
            raise RuntimeError("没有配置语音接口")
        # OpenAI 兼容 /audio/speech
        payload = {
            "model": VOICE_MODEL,
            "input": text,
            "response_format": VOICE_FORMAT,
        }
        if VOICE_MODE == "clone":
            ref = _voice_ref(character)
            if ref:
                with open(ref, "rb") as f:
                    payload["reference_audio"] = base64.b64encode(f.read()).decode("ascii")
                payload["reference_format"] = os.path.splitext(ref)[1].lstrip(".").lower()
            elif not desc:
                raise RuntimeError("声生声缺少参考音频和声音描述：%s" % character)
            # 没有参考音频（比如临时配角）但有声音描述时，退回文生声
        if desc:
            payload["instructions"] = desc
        return _post_audio(VOICE_ENDPOINT, payload, VOICE_KEY, VOICE_TIMEOUT)

    def _fix_wav_bytes(raw):
        """百炼返回的流式 WAV 把 RIFF/data 长度写成 0x7fffffff，按实际长度改回来，
        否则 Ren'Py 会把它当成几十小时的文件，播放不出声。"""
        try:
            if len(raw) < 44 or raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
                return raw
            off = 12
            while off + 8 <= len(raw):
                cid = raw[off:off + 4]
                sz = struct.unpack("<I", raw[off + 4:off + 8])[0]
                if cid == b"data":
                    actual = len(raw) - off - 8
                    if sz == 0 or sz > actual:
                        b = bytearray(raw)
                        b[4:8] = struct.pack("<I", len(raw) - 8)
                        b[off + 4:off + 8] = struct.pack("<I", actual)
                        return bytes(b)
                    return raw
                if sz == 0 or sz > len(raw):
                    return raw
                off += 8 + sz + (sz & 1)
        except Exception:
            pass
        return raw

    def _fix_wav_file(path):
        try:
            with open(path, "rb") as f:
                raw = f.read()
            fixed = _fix_wav_bytes(raw)
            if fixed != raw:
                _atomic_write_bytes(path, fixed)
                _debug("voice wav header repaired %s" % path)
        except OSError:
            pass

    def _run_voice(jobs):
        import hashlib
        for turn, character, rel, text in jobs:
            job = uuid.uuid4().hex
            gal_voice_log_context.job = job
            try:
                gal_request_log("event=voice.input job=%s turn=%s voice_path=%s text_chars=%d text_sha256=%s" %
                                (job, turn, rel, len(text), hashlib.sha256(text.encode("utf-8")).hexdigest()))
                if rel != gal_voice_path(character, text):
                    gal_request_log("event=voice.file status=stale job=%s turn=%s" % (job, turn))
                    continue
                raw = _voice_bytes(text, character)
                if rel != gal_voice_path(character, text):
                    gal_request_log("event=voice.file status=stale job=%s turn=%s" % (job, turn))
                    continue
                if rel.lower().endswith(".wav"):
                    raw = _fix_wav_bytes(raw)
                full = _safe_under(os.path.join(config.basedir, "game"), rel)
                if not full:
                    raise RuntimeError("语音路径越界：%s" % rel)
                os.makedirs(os.path.dirname(full), exist_ok=True)
                _atomic_write_bytes(full, raw)
                gal_request_log("event=voice.file status=saved job=%s turn=%s voice_path=%s bytes=%d mono_ms=%d" % (job, turn, rel, len(raw), time.monotonic() * 1000))
            except Exception as exc:
                gal_request_log("event=voice.file status=error job=%s turn=%s error_type=%s" % (job, turn, type(exc).__name__))
            finally:
                gal_voice_log_context.job = None
                _voice_pending_remove(rel)
        _voice_cache_trim()

    VOICE_CACHE_MAX = 4000
    VOICE_CACHE_BYTES = 512 * 1024 * 1024
    _voice_trim_at = [0.0]

    def _voice_cache_trim(force=False):
        """按 mtime 清理旧语音：文件名含全部音色配置，改一次配置就换一整套文件。"""
        now = time.time()
        if not force and now - _voice_trim_at[0] < 300:
            return
        _voice_trim_at[0] = now
        try:
            entries = []
            total = 0
            for root, _dirs, files in os.walk(VOICE_DIR):
                for fn in files:
                    if ".tmp-" in fn or fn.endswith(".tmp"):
                        continue
                    full = os.path.join(root, fn)
                    try:
                        stt = os.stat(full)
                    except OSError:
                        continue
                    entries.append((stt.st_mtime, stt.st_size, full))
                    total += stt.st_size
            if len(entries) <= VOICE_CACHE_MAX and total <= VOICE_CACHE_BYTES:
                return
            # 收藏引用的语音不能删，否则点“播放”永久静音
            try:
                favs = {e.get("voice") for e in voice_fav_list() if e.get("voice")}
            except Exception:
                favs = set()
            game_root = os.path.join(config.basedir, "game")
            entries.sort(key=lambda x: x[0])
            count = len(entries)
            removed = 0
            for _mtime, size, full in entries:
                if count <= VOICE_CACHE_MAX and total <= VOICE_CACHE_BYTES:
                    break
                rel = os.path.relpath(full, game_root).replace(os.sep, "/")
                if rel in favs:
                    continue
                try:
                    os.remove(full)
                    total -= size
                    count -= 1
                    removed += 1
                except OSError:
                    pass
            _debug("voice cache trimmed %d files, left %.1fMB" % (removed, total / 1048576.0))
        except Exception as exc:
            _debug("voice cache cleanup fail %s" % exc)

    def gal_voice_path(ch, text):
        identity = [
            str(ch), text, VOICE_MODE, VOICE_MODEL, VOICE_API, VOICE_LANG,
            _voice_name(ch), _voice_prompt(ch), VOICE_ENDPOINT, VOICE_FORMAT,
        ]
        if VOICE_MODE == "clone" and VOICE_API in ("dashscope", "mimo"):
            identity.append(gal_voice_reference_digest(_voice_ref(ch)))
            if VOICE_API == "dashscope":
                identity.extend([VOICE_CLONE_MODEL, VOICE_CLONE_WS, VOICE_CLONE_PREFIX])
        seed = json.dumps(identity, ensure_ascii=False, separators=(",", ":"))
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]
        ext = "wav" if VOICE_API == "dashscope" else VOICE_FORMAT
        return "voice/%s/%s.%s" % (_voice_dir(ch), digest, ext)

    def ensure_voice(st, records):
        if not VOICE_ON:
            return
        if not VOICE_ENDPOINT and VOICE_API != "dashscope":
            return
        if not VOICE_KEY:
            return
        jobs = []
        seen = set()
        game_root = os.path.join(config.basedir, "game")
        for rec in records:
            if "gal_cast_source" in rec or not rec.get("is_speech"):
                continue
            ch = rec.get("character")
            if not ch or ch == NARRATOR:
                continue
            if ch == "我" and not VOICE_PLAYER:
                continue
            text = str(rec.get("text") or "")
            rel = gal_voice_path(ch, text)
            rec["voice"] = rel
            preparing = (getattr(store, "_load_mode", None) == "resume"
                         and not getattr(store, "_load_done", True))
            submitted = store.gal_load_voice_submitted if preparing else None
            if rel in seen or (submitted is not None and rel in submitted):
                continue
            if submitted is not None:
                submitted.add(rel)
            if _voice_pending_has(rel):
                continue
            full = _safe_under(game_root, rel)
            if not full:
                _debug("voice skip unsafe path %s" % rel)
                continue
            try:
                ready = os.path.exists(full) and os.path.getsize(full) > 1024
            except OSError:
                ready = False
            if ready:
                continue
            seen.add(rel)
            _voice_pending_add(rel)
            jobs.append((rec.get("turn"), ch, rel, text))
        if not jobs:
            return
        box = {"done": False, "started": time.time()}
        renpy.store._voice_box = box
        t = threading.Thread(target=_guard(lambda: _run_voice(jobs), box))
        t.daemon = True
        try:
            t.start()
        except Exception:
            for _turn, _character, _rel, _text in jobs:
                _voice_pending_remove(_rel)
            raise
        threads = [x for x in (getattr(renpy.store, "_voice_threads", None) or []) if x.is_alive()]
        threads.append(t)
        renpy.store._voice_threads = threads
        renpy.store._voice_thread = t
        _debug("voice queue %d" % len(jobs))

    def gal_record_voice(rec, st):
        if not VOICE_ON or not rec.get("is_speech") or "gal_cast_source" in rec:
            return None
        expected = gal_voice_path(rec.get("character"), str(rec.get("text") or ""))
        if rec.get("voice") != expected or not _voice_file_ready(expected):
            rec.pop("voice", None)
            ensure_voice(st, [rec])
        return expected if rec.get("voice") == expected else None

    def play_voice(rec, immediate=False):
        if not VOICE_ON:
            return
        rel = rec.get("voice")
        if not rel:
            return
        full = _safe_under(os.path.join(config.basedir, "game"), rel)
        if not full:
            _debug("voice skip unsafe path %s" % rel)
            return
        # Dialogue must advance even if synthesis has not finished.
        if not _voice_file_ready(rel):
            _debug("voice not ready %s" % rel)
            return
        if str(rel).lower().endswith(".wav"):
            _fix_wav_file(full)
        try:
            if immediate:
                # 历史/收藏里点击播放：当前没有下一次 say，直接播
                renpy.sound.play(rel, channel="voice")
            else:
                # 对话里必须先把文件登记给官方 voice 队列：否则下一次交互的
                # voice_interact 会因为 _voice.play 为空而立刻 stop(channel="voice")
                voice(rel, tag=str(rec.get("character") or ""))
            try:
                voice_duck_start()
            except Exception:
                pass
        except Exception as exc:
            _debug("voice play fail: %s" % exc)

    def clear_stage_cast():
        renpy.store._dyn_cast = []
        renpy.store._dyn_cast_meta = []
        renpy.store._frame_probe = None
        renpy.store._frame_probe_busy = False
        renpy.store._cur_actor = None
        renpy.hide_screen("stage_hero")

    def hide_ui_keep_stage():
        """隐藏对话框与功能栏，保留背景和立绘；点一下画面恢复。"""
        old = getattr(renpy.store, "quick_menu", True)
        renpy.store.quick_menu = False
        try:
            # 原生 HideInterface 的行为：隐藏 say 后等一次点击，再返回
            renpy.call_in_new_context("_hide_windows")
        finally:
            renpy.store.quick_menu = old

    def replay_voice():
        """重放当前这句的语音。"""
        rec = getattr(renpy.store, "_last_voice", None)
        if not rec or not rec.get("voice"):
            renpy.notify("还没有可重放的语音")
            return
        play_voice(rec, immediate=True)

    def voice_fav_path():
        return os.path.join(slot_dir(), "voice_fav.json")

    def voice_fav_list():
        try:
            with open(voice_fav_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if type(data).__name__ == "list" else []
        except Exception:
            return []

    def _voice_fav_write(items):
        try:
            path = voice_fav_path()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            _atomic_write_text(path, json.dumps(items, ensure_ascii=False, indent=2))
        except Exception as exc:
            _debug("voice fav write fail: %s" % exc)

    def voice_fav_has(rel):
        return bool(rel) and any(e.get("voice") == rel for e in voice_fav_list())

    def current_voice_faved():
        rec = getattr(renpy.store, "_last_voice", None) or {}
        return voice_fav_has(rec.get("voice"))

    def toggle_voice_fav():
        rec = getattr(renpy.store, "_last_voice", None)
        rel = (rec or {}).get("voice")
        if not rel:
            renpy.notify("当前没有可收藏的语音")
            return
        items = voice_fav_list()
        for i, e in enumerate(items):
            if e.get("voice") == rel:
                items.pop(i)
                _voice_fav_write(items)
                renpy.notify("已取消收藏")
                renpy.restart_interaction()
                return
        items.append({
            "voice": rel,
            "character": rec.get("character", ""),
            "text": rec.get("text", ""),
            "at": time.strftime("%Y-%m-%d %H:%M"),
        })
        _voice_fav_write(items)
        renpy.notify("已收藏")
        renpy.restart_interaction()

    def remove_voice_fav(index):
        items = voice_fav_list()
        if 0 <= index < len(items):
            items.pop(index)
            _voice_fav_write(items)
            renpy.restart_interaction()

    def play_voice_fav(index):
        items = voice_fav_list()
        if 0 <= index < len(items):
            play_voice(items[index], immediate=True)

    # ---------- 历史记录 ----------

    def history_view_records():
        """只取当前分支上已经看过的拍，避免把预取和别的分支也列出来。"""
        st = getattr(renpy.store, "st", None)
        if not st:
            return []
        return _history_records(st)

    def history_avatar(character, standing):
        ch = str(character or "").strip()
        if not ch or is_narrator(ch):
            return None
        if ch in ("我", "me") and not PLAYER_SPRITE:
            return None
        p = resolve_persona(ch)
        sid = standing
        if sid is None and p:
            sid = default_standing(p)
        if sid is None:
            return None
        return standing_file(ch, sid)

    def history_display_text(rec):
        text = str(rec.get("text") or "")
        if rec.get("is_speech"):
            t = text.strip()
            if t and not (t.startswith("「") and t.endswith("」")):
                text = "「" + t + "」"
        return text

    def history_replay(rec):
        rel = gal_record_voice(rec, getattr(store, "st", None))
        if rel and _voice_file_ready(rel):
            play_voice(rec, immediate=True)
        elif rel and _voice_pending_has(rel):
            renpy.notify("正在生成这句的语音，稍后再点一次重播")
        else:
            renpy.notify("这句还没有可用的语音")

    def history_toggle_fav(rec):
        stored = rec.get("voice")
        items = voice_fav_list()
        for i, e in enumerate(items):
            if stored and e.get("voice") == stored and (
                e.get("character") == rec.get("character") and e.get("text") == rec.get("text")
            ):
                items.pop(i)
                _voice_fav_write(items)
                renpy.notify("已取消收藏")
                renpy.restart_interaction()
                return
        rel = gal_record_voice(rec, getattr(store, "st", None))
        if not rel or not _voice_file_ready(rel):
            renpy.notify("这句还没有可收藏的语音")
            return
        if any(item.get("voice") == rel for item in items):
            renpy.restart_interaction()
            return
        items.append({
            "voice": rel,
            "character": rec.get("character", ""),
            "text": rec.get("text", ""),
            "at": time.strftime("%Y-%m-%d %H:%M"),
        })
        _voice_fav_write(items)
        renpy.notify("已收藏")
        renpy.restart_interaction()

    def history_jump(turn, path):
        if getattr(renpy.store, "st", None) is None:
            renpy.notify("当前没有进行中的剧情")
            return
        try:
            target = int(turn)
        except (TypeError, ValueError):
            return
        if target <= 0:
            return
        renpy.store._history_target = {
            "turn": target,
            "path": list(path or []),
        }
        renpy.jump_out_of_context("ai_history_jump")

    def play_bgm(bgm_id):
        """只在 id 变化时动；同一条 BGM 不重播，防止每拍都重启。"""
        cur = getattr(renpy.store, "_cur_bgm", None)
        cur_id = "" if cur in (None, "") else str(cur).strip()
        new_id = "" if bgm_id in (None, "") else str(bgm_id).strip()
        if new_id == "0":
            if cur_id not in ("", "0"):
                renpy.music.stop(channel="music", fadeout=0.8)
                _debug("bgm stop")
            renpy.store._cur_bgm = "0"
            return
        if not BGM_FILES:
            return
        if new_id == cur_id:
            return
        if not new_id:
            return
        path = BGM_FILES.get(new_id)
        if not path:
            return
        renpy.music.play(
            path, channel="music", loop=True, fadein=0.8, fadeout=0.8,
            if_changed=True
        )
        renpy.store._cur_bgm = new_id
        _debug("bgm play %s" % new_id)

    # ---------- 网络 ----------

    gal_debug_lock = threading.Lock()
    gal_voice_log_context = threading.local()

    def gal_request_log(msg):
        gal_write_log("model_requests.log", msg)

    def _debug(msg):
        gal_write_log("ai_debug.log", msg)

    def gal_write_log(filename, msg):
        if not _on("GALGAME_DEBUG", "0"):
            return
        try:
            path = os.path.join(config.basedir, filename)
            with gal_debug_lock:
                if os.path.isfile(path) and os.path.getsize(path) >= 2 * 1024 * 1024:
                    for index in (2, 1):
                        source = path + ".%d" % index
                        if os.path.isfile(source):
                            os.replace(source, path + ".%d" % (index + 1))
                    os.replace(path, path + ".1")
                with open(path, "a", encoding="utf-8") as f:
                    f.write(time.strftime("%Y-%m-%dT%H:%M:%S%z ") + str(msg).replace("\r", " ").replace("\n", " ") + "\n")
        except OSError:
            pass

    def _options_sections():
        # 分组、说明、默认值都在 options_schema.rpy 里；options.txt 只存键值。
        sections = []
        for sec in OPTIONS_SCHEMA:
            if sec.get("player"):
                # 玩家设置走 settings.rpy 的独立界面
                continue
            items = []
            for item in sec["items"]:
                if item["key"] == "GALGAME_FONT":
                    # 字体选择已经挪到「设置 → 文本」
                    continue
                key = item["key"]
                value = str(_FILE_CFG.get(key, OPTIONS_DEFAULTS.get(key, "")))
                items.append({
                    "key": key,
                    "value": value,
                    "comment": item.get("desc", ""),
                    "kind": item.get("kind", "text"),
                    "restart": bool(item.get("restart")),
                })
            sections.append({"title": sec["title"], "items": items})
        return sections

    def load_options_editor():
        sections = _options_sections()
        flat = {}
        for sec in sections:
            for item in sec["items"]:
                flat[item["key"]] = item
        store.ai_opt_sections = sections
        store.ai_opt_flat = flat
        store.ai_opt_lock_ok = True
        store.ai_opt_edit_key = ""
        store.ai_opt_edit_value = ""
        store.ai_show_key = False
        _debug("options editor %d keys" % len(flat))

    def option_value_label(item):
        key = str(item.get("key") or "")
        val = str(item.get("value") or "")
        if "KEY" in key and val:
            return "已填写（点击修改）"
        return val if val else "（空）"

    def option_is_switch(item):
        kind = item.get("kind")
        if kind:
            return kind == "switch"
        return str(item.get("value") or "") in ("0", "1")

    def set_option_value(key, value):
        item = store.ai_opt_flat.get(key)
        if not item:
            return
        value = str(value).strip()
        item["value"] = value
        for sec in store.ai_opt_sections:
            for row in sec.get("items") or []:
                if row.get("key") == key:
                    row["value"] = value
        store.ai_opt_dirty = True

    def toggle_option(key):
        item = store.ai_opt_flat.get(key)
        if not item:
            return
        set_option_value(key, "0" if str(item.get("value") or "") == "1" else "1")

    def font_choices():
        folder = os.path.join(config.basedir, "game", "fonts")
        try:
            names = [n for n in os.listdir(folder) if n.lower().endswith(FONT_EXTS)]
        except OSError:
            names = []
        return sorted(names)

    def cycle_font(key):
        choices = font_choices()
        item = store.ai_opt_flat.get(key)
        if not choices or not item:
            return
        cur = str(item.get("value") or "")
        try:
            idx = choices.index(cur)
        except ValueError:
            idx = -1
        set_option_value(key, choices[(idx + 1) % len(choices)])

    def edit_option(key):
        item = store.ai_opt_flat.get(key)
        if not item:
            return
        store.ai_opt_edit_key = key
        store.ai_opt_edit_value = str(item.get("value") or "")
        store.ai_show_key = False
        reset_text_state("ai_opt_edit_value")
        set_text_focus("ai_opt_edit_value")
        renpy.show_screen("ai_option_edit")

    def apply_option_edit():
        set_option_value(store.ai_opt_edit_key, store.ai_opt_edit_value)
        store.ai_show_key = False
        renpy.hide_screen("ai_option_edit")

    def _clip_scrap():
        try:
            import pygame
        except Exception:
            return None
        raw = None
        try:
            raw = pygame.scrap.get(pygame.scrap.SCRAP_TEXT)
        except Exception:
            raw = None
        if raw is None:
            try:
                pygame.scrap.init()
                raw = pygame.scrap.get(pygame.scrap.SCRAP_TEXT)
            except Exception:
                raw = None
        return raw

    def clipboard_get():
        text = ""
        # 新版 Ren'Py 有官方 API 就用；8.5.3 没有，退回 pygame.scrap
        getter = getattr(renpy, "get_clipboard_text", None)
        if getter is not None:
            try:
                text = getter() or ""
            except Exception:
                text = ""
        if not text:
            raw = _clip_scrap()
            if raw:
                try:
                    text = raw.decode("utf-8", "ignore") if isinstance(raw, bytes) else str(raw)
                except Exception:
                    text = ""
        if not text:
            _debug("clipboard get empty")
            return ""
        text = text.replace(chr(0xfeff), "")
        return "".join(c for c in text if ord(c) >= 32)

    def clipboard_set(text):
        text = str(text)
        putter = getattr(renpy, "put_clipboard_text", None)
        if putter is not None:
            try:
                putter(text)
                return True
            except Exception:
                pass
        try:
            import pygame
            data = text.encode("utf-8")
            try:
                pygame.scrap.put(pygame.scrap.SCRAP_TEXT, data)
            except Exception:
                pygame.scrap.init()
                pygame.scrap.put(pygame.scrap.SCRAP_TEXT, data)
            return True
        except Exception as exc:
            _debug("clipboard set fail %s" % exc)
            return False

    def paste_to_var(name):
        text = clipboard_get()
        if not text:
            renpy.notify("剪贴板是空的")
            return
        setattr(renpy.store, name, text)
        renpy.restart_interaction()

    def copy_from_var(name):
        text = str(getattr(renpy.store, name, "") or "")
        if not text:
            renpy.notify("这一栏是空的")
            return
        if clipboard_set(text):
            renpy.notify("已复制")

    def toggle_show_key():
        renpy.store.ai_show_key = not bool(getattr(renpy.store, "ai_show_key", False))
        renpy.restart_interaction()

    def reset_show_key():
        renpy.store.ai_show_key = False

    OPTION_RESTART_KEYS = (
        "GALGAME_DEVELOPER",
        "GALGAME_TITLE_MUSIC",
        "GALGAME_HEROINE",
        "GALGAME_HEROINE_AUTO",
        "GALGAME_SAVE_DIR",
        "GALGAME_AUTOSTART",
        "GALGAME_IMAGE_ENDPOINT",
        "GALGAME_IMAGE_KEY",
        "GALGAME_IMAGE_MODEL",
        "GALGAME_IMAGE_SIZE",
        "GALGAME_IMAGE_SIZE_PORTRAIT",
        "GALGAME_PLAN_AHEAD",
        "GALGAME_BEAT_MIN",
        "GALGAME_BEAT_MAX",
        "GALGAME_BEAT_SENTENCES",
        "GALGAME_BEAT_LINES",
        "GALGAME_SHOT_VARY",
        "GALGAME_CHOICE_WINDOW",
        "GALGAME_CHOICE_MIN",
        "GALGAME_CHOICE_MAX",
        "GALGAME_CHOICE_GAP",
    )
    OPTION_RESTART_LABELS = {
        "GALGAME_HEROINE": "指定女主角",
        "GALGAME_HEROINE_AUTO": "自动选择女主角",
        "GALGAME_SAVE_DIR": "Ren'Py 存档目录名",
        "GALGAME_AUTOSTART": "启动后自动进游戏",
        "GALGAME_IMAGE_ENDPOINT": "生图接口",
        "GALGAME_IMAGE_KEY": "生图密钥",
        "GALGAME_IMAGE_MODEL": "生图模型",
        "GALGAME_IMAGE_SIZE": "背景出图尺寸",
        "GALGAME_IMAGE_SIZE_PORTRAIT": "立绘出图尺寸",
        "GALGAME_PLAN_AHEAD": "预生成拍数",
        "GALGAME_BEAT_MIN": "每拍最少字数",
        "GALGAME_BEAT_MAX": "每拍最多字数",
        "GALGAME_BEAT_SENTENCES": "每拍最多句数",
        "GALGAME_BEAT_LINES": "每拍最多行数",
        "GALGAME_SHOT_VARY": "变化镜头远近",
        "GALGAME_CHOICE_WINDOW": "选择密度窗口",
        "GALGAME_CHOICE_MIN": "窗口内最少选择",
        "GALGAME_CHOICE_MAX": "窗口内最多选择",
        "GALGAME_CHOICE_GAP": "选择最小间隔",
    }

    def option_restart_label(key):
        return OPTION_RESTART_LABELS.get(key, key)

    def option_restart_changes(updates):
        """返回本次修改里需要重启才能生效的项。"""
        return [
            key for key in OPTION_RESTART_KEYS
            if str(updates.get(key, "")) != str(_FILE_CFG.get(key, OPTIONS_DEFAULTS.get(key, "")))
        ]

    def apply_live_options():
        """保存设置后热更新：以内存配置为准，不再回头读文件。"""
        def num(name, default, low=None):
            try:
                v = int(float(_cfg(name, str(default)) or default))
            except (TypeError, ValueError):
                v = int(default)
            return max(low, v) if low is not None else v

        def flt(name, default, low=None):
            try:
                v = float(_cfg(name, str(default)) or default)
            except (TypeError, ValueError):
                v = float(default)
            return max(low, v) if low is not None else v

        s = renpy.store
        old_model = s.AI_MODEL
        old_endpoint = s.AI_ENDPOINT
        old_key = s.AI_KEY

        s.AI_ENDPOINT = _cfg("GALGAME_ENDPOINT", "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions")
        s.AI_KEY = _cfg("GALGAME_KEY")
        s.AI_MODEL = _cfg("GALGAME_MODEL", "qwen3.8-flash")
        s.AI_TIMEOUT = flt("GALGAME_TIMEOUT", 60, 5)
        s.AI_THINKING = num("GALGAME_THINKING", 1)
        s.AI_FALLBACK_MODEL = _cfg("GALGAME_FALLBACK_MODEL")
        s.AI_FALLBACK_ENDPOINT = _cfg("GALGAME_FALLBACK_ENDPOINT")
        s.AI_FALLBACK_KEY = _cfg("GALGAME_FALLBACK_KEY")
        s.AI_MOCK = not s.AI_KEY

        s.DOCTOR_ON = _on("GALGAME_DOCTOR", "0")
        s.DOCTOR_MODEL = _cfg("GALGAME_DOCTOR_MODEL")
        s.DOCTOR_ENDPOINT = _cfg("GALGAME_DOCTOR_ENDPOINT")
        s.DOCTOR_KEY = _cfg("GALGAME_DOCTOR_KEY")
        s.DOCTOR_INTERVAL = num("GALGAME_DOCTOR_INTERVAL", 15, 5)
        s.DOCTOR_STALL = num("GALGAME_DOCTOR_STALL", 90, 20)
        s.DOCTOR_MAX = num("GALGAME_DOCTOR_MAX", 3, 1)
        s.DOCTOR_FRAME = _on("GALGAME_DOCTOR_FRAME", "1")
        s.DOCTOR_VISION_MODEL = _cfg("GALGAME_DOCTOR_VISION_MODEL")
        s.DOCTOR_FRAME_MAX = num("GALGAME_DOCTOR_FRAME_MAX", 8, 1)
        s.HARNESS_SELF_HEAL = _on("GALGAME_HARNESS_SELF_HEAL", "1")

        s.CONTEXT_LIMIT = num("GALGAME_CONTEXT_LIMIT", 32000, 4000)
        s.CONTEXT_RATIO = flt("GALGAME_CONTEXT_RATIO", 0.75, 0.1)
        s.SUMMARY_KEEP = num("GALGAME_SUMMARY_KEEP", 20, 4)
        s.SCENE_MIN_STAY = num("GALGAME_SCENE_MIN_STAY", 5, 1)
        s.SCENE_LOCK = _on("GALGAME_SCENE_LOCK", "1")
        s.CHAPTER_LENGTH = num("GALGAME_CHAPTER_LENGTH", 40, 10)
        s.ENABLE_CHAPTER = _on("GALGAME_ENABLE_CHAPTER", "1")
        s.ENDLESS = _on("GALGAME_ENDLESS", "1")
        s.PLAYER_SPRITE = _on("GALGAME_PLAYER_SPRITE", "0")
        s.HEROINE_AUTO = _on("GALGAME_HEROINE_AUTO", "1")
        s.GENRE = _cfg("GALGAME_GENRE", "校园恋爱")

        s.PLAN_AHEAD = num("GALGAME_PLAN_AHEAD", 10, 1)
        s.BEAT_MIN = num("GALGAME_BEAT_MIN", 20, 1)
        s.BEAT_MAX = max(s.BEAT_MIN, num("GALGAME_BEAT_MAX", 50, 1))
        s.BEAT_SENTENCES = num("GALGAME_BEAT_SENTENCES", 2, 1)
        s.BEAT_LINES = num("GALGAME_BEAT_LINES", 2, 1)
        s.SHOT_VARY = _on("GALGAME_SHOT_VARY", "1")
        s.CHOICE_WINDOW = num("GALGAME_CHOICE_WINDOW", 30, 1)
        s.CHOICE_MIN = num("GALGAME_CHOICE_MIN", 1, 0)
        s.CHOICE_MAX = max(s.CHOICE_MIN, num("GALGAME_CHOICE_MAX", 2, 0))
        s.CHOICE_GAP = num("GALGAME_CHOICE_GAP", 12, 1)
        s.PER_BLOCK_MAX = max(1, s.PLAN_AHEAD * s.CHOICE_MAX // s.CHOICE_WINDOW)

        s.TEXT_CPS = text_cps_value(_cfg("GALGAME_TEXT_CPS"))
        config.default_text_cps = s.TEXT_CPS
        try:
            preferences.text_cps = s.TEXT_CPS
        except Exception:
            pass
        s.FONT_FILE = font_pick(_cfg("GALGAME_FONT", FONT_DEFAULT))
        s.FONT_PATH = "fonts/" + s.FONT_FILE
        apply_font_path(s.FONT_PATH)
        s.HISTORY_FEED = num("GALGAME_HISTORY_FEED", 8, 2)
        s.DETAIL_INTERVAL = num("GALGAME_DETAIL_INTERVAL", 50, 10)
        s.PERSONA_MAX = num("GALGAME_PERSONA_MAX", 20, 5)
        s.REINJECT_EVERY = num("GALGAME_REINJECT_EVERY", 40, 5)

        s.SUBAGENTS = _on("GALGAME_SUBAGENTS", "0")
        s.SUBAGENT_LINES = num("GALGAME_SUBAGENT_LINES", 2, 1)
        s.SUBAGENT_MODEL = _cfg("GALGAME_SUBAGENT_MODEL")
        s.DIARY_EVERY = num("GALGAME_DIARY_EVERY", 50, 10)
        s.AUTO_CHARACTER = _on("GALGAME_AUTO_CHARACTER", "0")
        s.AUTO_CHARACTER_MAX = num("GALGAME_AUTO_CHARACTER_MAX", 1, 1)
        s.TEMP_CAST_MAX = num("GALGAME_TEMP_CAST_MAX", 2, 1)

        s.USING_HARNESS = _on("GALGAME_USING_HARNESS", "0")
        s.HOST = _cfg("GALGAME_HOST", "")
        s.HARNESS_TIMEOUT = num("GALGAME_HARNESS_TIMEOUT", 45, 5)

        s.GEN_SCENE = num("GALGAME_GEN_SCENE", 0, 0)
        s.GEN_STANDING = num("GALGAME_GEN_STANDING", 0, 0)
        s.GEN_UI_CHOICE = num("GALGAME_GEN_UI_CHOICE", 0, 0)
        s.GEN_UI_DIALOGUE = num("GALGAME_GEN_UI_DIALOGUE", 0, 0)
        s.GEN_UI_TITLE = num("GALGAME_GEN_UI_TITLE", 0, 0)

        s.VOICE_ON = _on("GALGAME_VOICE", "0")
        s.VOICE_MODE = (_cfg("GALGAME_VOICE_MODE", "tts") or "tts").strip().lower()
        s.VOICE_ENDPOINT = _cfg("GALGAME_VOICE_ENDPOINT")
        s.VOICE_KEY = _cfg("GALGAME_VOICE_KEY") or s.AI_KEY
        api = (_cfg("GALGAME_VOICE_API", "") or "").strip().lower()
        if api not in ("openai", "dashscope", "mimo", "openai_official", "other"):
            api = "dashscope" if ("dashscope" in s.VOICE_ENDPOINT or "aliyuncs.com" in s.VOICE_ENDPOINT) else "openai"
        s.VOICE_API = api
        s.VOICE_ENDPOINT = voice_provider_endpoint(api, s.VOICE_ENDPOINT)
        if api in ("mimo", "openai_official"):
            s.VOICE_KEY = _cfg("GALGAME_VOICE_KEY")
        voice_default = "qwen3-tts-flash" if api == "dashscope" else "mimo-v2.5-tts" if api == "mimo" else "tts-1"
        s.VOICE_MODEL = _cfg("GALGAME_VOICE_MODEL") or voice_default
        if api == "openai" and not s.VOICE_ENDPOINT:
            # OpenAI 兼容：没填语音端点时从对话端点推导 /audio/speech
            chat = s.AI_ENDPOINT or ""
            if "/chat/completions" in chat:
                s.VOICE_ENDPOINT = chat.replace("/chat/completions", "/audio/speech")
            elif chat:
                s.VOICE_ENDPOINT = chat.rstrip("/") + "/audio/speech"
        s.VOICE_NAME = _cfg("GALGAME_VOICE_NAME", "Cherry")
        s.VOICE_LANG = _cfg("GALGAME_VOICE_LANG", "Chinese")
        s.VOICE_CLONE_WS = _cfg("GALGAME_VOICE_CLONE_WORKSPACE")
        s.VOICE_CLONE_MODEL = _cfg("GALGAME_VOICE_CLONE_MODEL", "qwen-audio-3.1-tts-plus")
        s.VOICE_CLONE_PREFIX = _cfg("GALGAME_VOICE_CLONE_PREFIX", "galgame")
        s.VOICE_FORMAT = (_cfg("GALGAME_VOICE_FORMAT", "wav") or "wav").strip().lower()
        s.VOICE_PLAYER = _on("GALGAME_VOICE_PLAYER", "0")
        s.VOICE_TIMEOUT = num("GALGAME_VOICE_TIMEOUT", 60, 10)
        s.BGM_MIN_STAY = num("GALGAME_BGM_MIN_STAY", 5, 1)

        if (s.AI_MODEL, s.AI_ENDPOINT, s.AI_KEY) != (old_model, old_endpoint, old_key):
            # 换了模型/接口/密钥：清掉降级覆盖，下一批请求直接用新配置
            s._model_override = None
            s._endpoint_override = None
            s._key_override = None
        if not getattr(s, "main_menu", False) and getattr(s, "st", None) is not None:
            s.start_doctor()

    def _commit_options(updates):
        # 高级设置只提交自己那一份；其余键（玩家设置、密钥）从内存补齐，
        # 避免整份写盘时把别的页面的值冲回默认。
        values = options_current_values(_FILE_CFG)
        values.update({k: str(v) for k, v in updates.items()})
        ok = options_write(values, OPTIONS_UNKNOWN, OPTIONS_KEY_EXTRA)
        if ok:
            # 内存就是唯一真相，写成功后同步，热更新从内存读。
            for key, value in values.items():
                _FILE_CFG[key] = str(value)
            apply_live_options()
            load_options_editor()
        return ok

    def _options_save_on_quit():
        """退出时再整写一次：外部修改会被内存值覆盖。"""
        try:
            stop_doctor()
        except Exception:
            pass
        try:
            options_write(
                options_current_values(
                    store._settings_open_values if renpy.get_screen("player_settings")
                    and settings_restart_changes() else _FILE_CFG
                ),
                OPTIONS_UNKNOWN,
                OPTIONS_KEY_EXTRA,
            )
        except Exception as exc:
            options_log("quit save fail: %s" % exc)

    renpy.config.quit_callbacks.append(_options_save_on_quit)

    def save_options_editor():
        if not getattr(store, "ai_opt_flat", None):
            load_options_editor()
        updates = {
            key: str(item.get("value") or "")
            for key, item in store.ai_opt_flat.items()
        }
        restart_keys = option_restart_changes(updates)
        if restart_keys:
            # 有需要重启的项：先不写盘，等玩家确认
            store._pending_option_updates = updates
            store._pending_option_restart_keys = restart_keys
            renpy.show_screen("options_restart_confirm", keys=restart_keys)
            return
        ok = _commit_options(updates)
        if ok:
            renpy.notify("设置已保存并立即生效")
        else:
            renpy.notify("写入 options.txt 失败，请检查目录权限")

    def cancel_options_restart():
        store._pending_option_updates = None
        store._pending_option_restart_keys = ()
        snap = getattr(store, "_pending_settings_snapshot", None)
        store._pending_settings_snapshot = None
        if snap is not None:
            _FILE_CFG.clear()
            _FILE_CFG.update(snap)
            store.settings_dirty = False
            store._settings_open_values = dict(snap)
            try:
                apply_live_options()
                apply_display_settings()
                apply_audio_settings()
                apply_game_settings()
                apply_keymap_settings()
                apply_font_live()
                apply_player_preferences()
                settings_load_sliders()
                settings_load_color()
                settings_make_picker()
            except Exception as exc:
                _debug("cancel settings rollback fail: %s" % exc)
            renpy.notify("已取消保存，本次修改全部丢弃")
            return
        load_options_editor()
        renpy.notify("已取消保存，本次修改全部丢弃")

    def confirm_options_restart():
        updates = getattr(store, "_pending_option_updates", None)
        store._pending_option_updates = None
        store._pending_option_restart_keys = ()
        if not updates:
            return
        if not _commit_options(updates):
            renpy.notify("写入 options.txt 失败，未重启")
            return
        try:
            if not getattr(store, "main_menu", False) and getattr(store, "st", None) is not None:
                save_state("auto", quiet=True, use_pending=False, thumb=False)
        except Exception:
            pass
        # 重新拉起一个干净进程，确保所有 init 期设置都重新读取
        renpy.quit(relaunch=True)

    def save_ai_config(endpoint, model, key):
        """设置页保存：写内存和 options.txt/key.txt。返回是否写成。"""
        endpoint = str(endpoint or "").strip()
        model = str(model or "").strip()
        key = str(key or "").strip()
        values = options_current_values(_FILE_CFG)
        values["GALGAME_ENDPOINT"] = endpoint or AI_ENDPOINT
        values["GALGAME_MODEL"] = model or AI_MODEL
        values["GALGAME_KEY"] = key
        ok = options_write(values, OPTIONS_UNKNOWN, OPTIONS_KEY_EXTRA)
        if not ok:
            return False
        _FILE_CFG["GALGAME_ENDPOINT"] = values["GALGAME_ENDPOINT"]
        _FILE_CFG["GALGAME_MODEL"] = values["GALGAME_MODEL"]
        _FILE_CFG["GALGAME_KEY"] = key
        store.AI_ENDPOINT = values["GALGAME_ENDPOINT"]
        store.AI_MODEL = values["GALGAME_MODEL"]
        store.AI_KEY = key
        store.AI_MOCK = not key
        # 玩家主动换模型后，旧的降级/自愈覆盖必须失效，否则 active_* 仍走旧模型。
        store._model_override = None
        store._endpoint_override = None
        store._key_override = None
        try:
            DOCTOR_EVENTS[:] = []
        except Exception:
            pass
        _debug("模型设置已保存 keylen=%d model=%s" % (len(key), store.AI_MODEL))
        return True

    def open_ai_settings():
        renpy.store.ai_show_key = False
        for _f in ("ai_cfg_endpoint", "ai_cfg_model", "ai_cfg_key"):
            reset_text_state(_f)
        set_text_focus("ai_cfg_endpoint")
        renpy.show_screen("ai_settings")

    def apply_ai_settings():
        renpy.store.ai_show_key = False
        ok = save_ai_config(ai_cfg_endpoint, ai_cfg_model, ai_cfg_key)
        if ok:
            renpy.notify("已保存，下一批生效")
        else:
            renpy.notify("写入 options.txt 失败，请检查目录权限")

    def gal_fallback_route():
        return (AI_FALLBACK_MODEL, _chat_url(AI_FALLBACK_ENDPOINT or AI_ENDPOINT), AI_FALLBACK_KEY or AI_KEY)

    def gal_select_fallback():
        route = gal_fallback_route()
        store._model_override, store._endpoint_override, store._key_override = route
        return route

    def active_model():
        return getattr(renpy.store, "_model_override", None) or AI_MODEL

    def role_model():
        """子智能体用的模型：不跟主模型的降级走。"""
        return SUBAGENT_MODEL or AI_MODEL

    def _chat_url(url):
        url = (url or "").rstrip("/")
        # 允许只填 .../compatible-mode/v1 这种基址
        if url and not url.endswith("/chat/completions"):
            url += "/chat/completions"
        return url

    def active_endpoint():
        return _chat_url(
            getattr(renpy.store, "_endpoint_override", None) or AI_ENDPOINT
        )

    def doctor_on():
        # 开关打开且填了模型：用 option 里的自愈模型，harness 下也优先用它
        return bool(DOCTOR_ON and DOCTOR_MODEL and not gal_mock_mode())

    def doctor_harness_on():
        # 开关关着，或者开着但没填模型时，harness 模式用 harness 的模型自愈
        return bool(harness_available() and not doctor_on() and HARNESS_SELF_HEAL)

    def harness_doctor_meta():
        """告诉 harness 这次要不要它自己修，以及谁负责自愈。"""
        if doctor_on():
            mode = "option"
        elif doctor_harness_on():
            mode = "harness"
        else:
            mode = "off"
        return {
            "self_heal": doctor_harness_on(),
            "doctor": mode,
            "doctor_mode": "subagent" if mode == "harness" else mode,
            "doctor_hint": (
                "self_heal 为 true 时，请在回包前用子代理校验 beats 和 choices，"
                "坏 JSON 修好再返回，不要再向引擎发 doctor 请求。"
            ) if mode == "harness" else "",
        }

    def doctor_watch_on():
        # 巡检线程和本地自愈不跟开关绑定：harness 模式始终保留
        return bool(harness_available() or doctor_on())

    def doctor_model():
        return DOCTOR_MODEL or AI_FALLBACK_MODEL or AI_MODEL

    def doctor_endpoint():
        return _chat_url(
            DOCTOR_ENDPOINT or AI_FALLBACK_ENDPOINT or AI_ENDPOINT
        )

    def doctor_key():
        return DOCTOR_KEY or AI_FALLBACK_KEY or AI_KEY

    # ---------- 立绘构图自愈 ----------
    # 思路：新人上场时截一张当前画面，交给视觉模型看“头顶有没有切、两人有没有叠、
    # 对话框上方有没有露出下半身”，把 dx/dy/zoom 回写到引擎；结果按角色缓存，
    # 下次同一角色上场直接套用，不再重复请求。

    FRAME_BODY_RATIO = 0.38   # 立绘两侧透明留白约三成，几何兜底只按人物本体算宽度
    FRAME_CONF_MIN = 0.4      # 视觉模型置信度低于这个值就不采用

    def frame_check_on():
        if not (DOCTOR_ON and DOCTOR_FRAME):
            return False
        if not (DOCTOR_VISION_MODEL or DOCTOR_MODEL):
            return False
        endpoint = doctor_endpoint() or ""
        return bool(doctor_key() or "127.0.0.1" in endpoint or "localhost" in endpoint)

    def frame_vision_model():
        return DOCTOR_VISION_MODEL or doctor_model()

    def frame_plan_key(character, count, slot):
        return "frame:%s|%d|%d" % (character, int(count), int(slot))

    def _frame_plans():
        p = renpy.game.persistent
        plans = getattr(p, "galgame_frame_plans", None)
        if not hasattr(plans, "get"):
            plans = {}
            p.galgame_frame_plans = plans
        return plans

    def _frame_plan_ok(plan, w, h):
        if not hasattr(plan, "get"):
            return False
        try:
            if "w" in plan and abs(int(plan["w"]) - int(w)) > 2:
                return False
            if "h" in plan and abs(int(plan["h"]) - int(h)) > 2:
                return False
        except (TypeError, ValueError):
            return False
        return True

    def frame_plan_for(character, count, slot, w, h):
        plans = _frame_plans()
        for key in (frame_plan_key(character, count, slot), "frame:" + str(character)):
            plan = plans.get(key)
            if _frame_plan_ok(plan, w, h):
                return dict(plan)
        return None

    def frame_image_size(rel):
        try:
            w, h = renpy.image_size(Image(rel))
            if w and h:
                return int(w), int(h)
        except Exception:
            pass
        return 920, 1380

    def frame_base_layout(count, slot, shot="medium"):
        """与 script.rpy 的 transform 数值保持一致。"""
        if count <= 1:
            zoom = {"wide": 1.35, "medium": 1.45, "close": 1.6}.get(shot, 1.45)
            return 0.5, zoom
        if count == 2:
            return (0.28, 0.72)[min(slot, 1)], 1.35
        return (0.2, 0.5, 0.8)[min(slot, 2)], 1.0

    def frame_transform(rel, base_x, base_z, plan):
        plan = plan or {}
        try:
            dx = float(plan.get("dx", 0) or 0)
            dy = float(plan.get("dy", 0) or 0)
            zm = float(plan.get("zoom", 1.0) or 1.0)
        except (TypeError, ValueError):
            dx = dy = 0.0
            zm = 1.0
        sw = float(getattr(config, "screen_width", 1280) or 1280)
        x = max(0.03, min(0.97, base_x + dx / sw))
        return Transform(
            child=Image(rel),
            xpos=x,
            xanchor=0.5,
            yalign=0.0,
            yoffset=max(-240.0, min(240.0, dy)),
            zoom=max(0.5, min(2.5, base_z * zm)),
        )

    def _frame_boxes(meta, plans=None):
        sw = float(getattr(config, "screen_width", 1280) or 1280)
        rows = []
        for m in meta:
            plan = (plans or {}).get(m["id"]) or {}
            dx = float(plan.get("dx", 0) or 0)
            zm = float(plan.get("zoom", 1.0) or 1.0)
            w = float(m["w"]) * float(m["zoom"]) * zm
            h = float(m["h"]) * float(m["zoom"]) * zm
            body = w * FRAME_BODY_RATIO
            cx = float(m["x"]) * sw + dx
            top = float(plan.get("dy", 0) or 0)
            rows.append({
                "id": m["id"],
                "slot": m["slot"] + 1,
                "cx": round(cx),
                "left": round(cx - body / 2),
                "right": round(cx + body / 2),
                "top": round(top),
                "bottom": round(top + h),
                "full_left": round(cx - w / 2),
                "full_right": round(cx + w / 2),
            })
        return rows

    def _frame_prompt(probe):
        boxes = _frame_boxes(probe.get("meta") or [])
        info = []
        for row in boxes:
            info.append(
                "id=%s slot=%s 人物左右=%s..%s 头顶y=%s 下沿y=%s 整图左右=%s..%s"
                % (row["id"], row.get("slot", "?"), row["left"], row["right"],
                   row["top"], row["bottom"], row["full_left"], row["full_right"])
            )
        return (
            "你在检查视觉小说截图里的立绘构图。画面 %d×%d，底部约 185px 是对话框，"
            "立绘从画面顶端向下摆放，底下被对话框挡住是正常的。\n"
            "判断标准：\n"
            "1. 每个角色只露出胸部以上；头顶不能贴边或被切，也不能只露出一个头，"
            "更不能在对话框上方露出腰或大腿。\n"
            "2. 单人应居中；两人左右对称；三人均匀分布，人物本体不能互相重叠。\n"
            "3. 人物不能超出画面左右边界；立绘两侧的透明留白不算人物宽度。\n"
            "4. 只调整明显不对的角色；单人已经居中、头顶和胸部完整时，"
            "必须保持 dx=0、dy=0、zoom=1，不要为了个人偏好移动。\n"
            "5. 只有出现切头、出界、重叠、露出下半身或明显偏心时，才给非零值。\n"
            "6. 对话框、按钮、文字都是界面，不要当成人物。\n\n"
            "引擎当前数据（坐标按 %d×%d 计算）：\n%s\n\n"
            "只输出 JSON，不要解释：\n"
            '{"ok":false,"sprites":[{"id":"角色id","dx":0,"dy":0,"zoom":1.0,"why":"..."}],"confidence":0.8}\n'
            "dx/dy 是屏幕像素，范围 -180..180 / -120..120；zoom 是倍数，范围 0.85..1.2；"
            "没问题就 dx=0、dy=0、zoom=1。"
            % (config.screen_width, config.screen_height,
               config.screen_width, config.screen_height,
               chr(10).join(info))
        )

    def _frame_vision_call(probe, png):
        b64 = base64.b64encode(png).decode("ascii")
        messages = [
            {"role": "system", "content": "你是视觉小说引擎的立绘构图自愈模型。只输出合法 JSON，不要解释。"},
            {"role": "user", "content": [
                {"type": "text", "text": _frame_prompt(probe)},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}},
            ]},
        ]
        payload = {
            "model": frame_vision_model(),
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 700,
            "response_format": {"type": "json_object"},
            "enable_thinking": False,
            "stream": False,
        }
        try:
            data = _post_json(doctor_endpoint(), payload, doctor_key(), AI_TIMEOUT, request_kind="vision")
        except Exception as exc:
            text = str(exc).lower()
            if "response_format" not in text and "enable_thinking" not in text:
                raise
            payload.pop("response_format", None)
            payload.pop("enable_thinking", None)
            data = _post_json(doctor_endpoint(), payload, doctor_key(), AI_TIMEOUT, request_kind="vision")
        content = data["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(
                str(x.get("text", "")) for x in content if hasattr(x, "get")
            )
        return _extract_json(content)

    def _frame_sanitize(obj, probe):
        valid = {m["id"]: m for m in (probe.get("meta") or [])}
        try:
            conf = float(obj.get("confidence", 1) or 0)
        except (TypeError, ValueError):
            conf = 1.0
        if conf < FRAME_CONF_MIN:
            _debug("frame low confidence %.2f" % conf)
            return None
        out = {}
        for row in obj.get("sprites") or []:
            if not hasattr(row, "get"):
                continue
            cid = str(row.get("id") or "").strip()
            if cid not in valid:
                continue
            try:
                dx = float(row.get("dx", 0) or 0)
                dy = float(row.get("dy", 0) or 0)
                zm = float(row.get("zoom", 1) or 1)
            except (TypeError, ValueError):
                continue
            out[cid] = {
                "dx": round(max(-180.0, min(180.0, dx)), 1),
                "dy": round(max(-120.0, min(120.0, dy)), 1),
                "zoom": round(max(0.85, min(1.2, zm)), 3),
                "why": str(row.get("why") or "")[:80],
            }
        if not out:
            if not obj.get("ok"):
                return None
            out = {cid: {"dx": 0.0, "dy": 0.0, "zoom": 1.0, "why": ""} for cid in valid}
        for cid in valid:
            out.setdefault(cid, {"dx": 0.0, "dy": 0.0, "zoom": 1.0, "why": ""})
        return out

    def _frame_geometry_plans(probe):
        """视觉模型不可用时的兜底：只处理出界和明显重叠，不猜胸部位置。"""
        meta = probe.get("meta") or []
        if not meta:
            return None
        sw = float(getattr(config, "screen_width", 1280) or 1280)
        plans = {m["id"]: {"dx": 0.0, "dy": 0.0, "zoom": 1.0} for m in meta}

        def clamp(v):
            return max(-180.0, min(180.0, v))

        for m in meta:
            w = float(m["w"]) * float(m["zoom"]) * FRAME_BODY_RATIO
            cx = float(m["x"]) * sw
            left = cx - w / 2
            right = cx + w / 2
            dx = 0.0
            if left < 8:
                dx += 8 - left
            if right > sw - 8:
                dx -= right - (sw - 8)
            plans[m["id"]]["dx"] = clamp(dx)

        for i in range(len(meta)):
            for j in range(i + 1, len(meta)):
                a = meta[i]
                b = meta[j]
                wa = float(a["w"]) * float(a["zoom"]) * FRAME_BODY_RATIO
                wb = float(b["w"]) * float(b["zoom"]) * FRAME_BODY_RATIO
                ax = float(a["x"]) * sw + plans[a["id"]]["dx"]
                bx = float(b["x"]) * sw + plans[b["id"]]["dx"]
                overlap = (wa + wb) / 2 - abs(bx - ax)
                if overlap <= 0:
                    continue
                push = overlap / 2 + 10
                if ax <= bx:
                    plans[a["id"]]["dx"] = clamp(plans[a["id"]]["dx"] - push)
                    plans[b["id"]]["dx"] = clamp(plans[b["id"]]["dx"] + push)
                else:
                    plans[a["id"]]["dx"] = clamp(plans[a["id"]]["dx"] + push)
                    plans[b["id"]]["dx"] = clamp(plans[b["id"]]["dx"] - push)

        changed = any(
            abs(p["dx"]) > 0.5 or abs(p["dy"]) > 0.5 or abs(p["zoom"] - 1.0) > 0.001
            for p in plans.values()
        )
        return plans if changed else None

    def _frame_store_plans(probe, plans):
        meta = probe.get("meta") or []
        if not meta:
            return
        store_plans = _frame_plans()
        now = int(time.time())
        for m in meta:
            plan = plans.get(m["id"])
            if not hasattr(plan, "get"):
                continue
            row = {
                "dx": float(plan.get("dx", 0) or 0),
                "dy": float(plan.get("dy", 0) or 0),
                "zoom": float(plan.get("zoom", 1) or 1),
                "w": int(m["w"]),
                "h": int(m["h"]),
                "why": str(plan.get("why") or "")[:80],
                "ts": now,
            }
            store_plans[frame_plan_key(m["id"], m["count"], m["slot"])] = row
            fallback = "frame:" + m["id"]
            moved = (
                abs(row["dx"]) > 0.5 or abs(row["dy"]) > 0.5
                or abs(row["zoom"] - 1.0) > 0.001
            )
            # 只让真正调整过的角色覆盖通用方案，避免把之前调好的方案冲成 0
            if moved or fallback not in store_plans:
                store_plans[fallback] = dict(row)
        renpy.game.persistent.galgame_frame_plans = store_plans

    def frame_plan_poll():
        ready = getattr(renpy.store, "_frame_plan_ready", None)
        if not ready:
            return
        renpy.store._frame_plan_ready = None
        renpy.store._frame_probe_busy = False
        probe = ready.get("probe") or {}
        plans = ready.get("plans") or {}
        if plans:
            _frame_store_plans(probe, plans)
            try:
                renpy.save_persistent()
            except Exception as exc:
                _debug("frame save persistent fail %s" % exc)
        if ready.get("cast_key") != getattr(renpy.store, "_cur_actor", None):
            _debug("frame plan stale %s" % ready.get("cast_key"))
            return
        meta = getattr(renpy.store, "_dyn_cast_meta", None) or []
        if not meta or not plans:
            return
        changed = False
        items = []
        for m in meta:
            plan = plans.get(m["id"]) or frame_plan_for(
                m["id"], m["count"], m["slot"], m["w"], m["h"]
            )
            if plan:
                at = frame_transform(m["rel"], m["x"], m["zoom"], plan)
                if (abs(float(plan.get("dx", 0) or 0)) > 0.5
                        or abs(float(plan.get("dy", 0) or 0)) > 0.5
                        or abs(float(plan.get("zoom", 1) or 1) - 1.0) > 0.001):
                    changed = True
            else:
                at = m.get("at")
            items.append((Image(m["rel"]), at))
        if changed:
            renpy.store._dyn_cast = items
            renpy.restart_interaction()
            _debug("frame apply %s %s" % (
                ready.get("source", "vision"), str(plans)[:300],
            ))

    def frame_probe_worker(probe, png):
        try:
            plans = None
            source = "vision"
            try:
                plans = _frame_sanitize(_frame_vision_call(probe, png), probe)
            except Exception as exc:
                _debug("frame vision fail %s" % exc)
            if not plans:
                try:
                    plans = _frame_geometry_plans(probe)
                    source = "geometry"
                except Exception as exc:
                    _debug("frame geometry fail %s" % exc)
            if plans:
                renpy.store._frame_plan_ready = {
                    "cast_key": probe.get("cast_key"),
                    "probe": probe,
                    "plans": plans,
                    "source": source,
                }
                _debug("frame check ok %s %d sprites" % (source, len(plans)))
            else:
                _debug("frame check no plan")
        except Exception as exc:
            _debug("frame worker fail %s" % exc)
        finally:
            # 任何出口都要复位，否则一次异常就让整局构图自愈失效
            renpy.store._frame_probe_busy = False

    def frame_probe_capture():
        probe = getattr(renpy.store, "_frame_probe", None)
        if not probe:
            return
        if not frame_check_on():
            renpy.store._frame_probe = None
            return
        if probe.get("cast_key") != getattr(renpy.store, "_cur_actor", None):
            renpy.store._frame_probe = None
            _debug("frame probe stale")
            return
        if int(DOCTOR_STATE.get("frames", 0)) >= DOCTOR_FRAME_MAX:
            renpy.store._frame_probe = None
            _debug("frame check skipped: limit %d" % DOCTOR_FRAME_MAX)
            return
        renpy.store._frame_probe = None
        try:
            png = renpy.screenshot_to_bytes(
                (int(config.screen_width), int(config.screen_height))
            )
        except Exception as exc:
            _debug("frame screenshot fail %s" % exc)
            return
        if not png:
            _debug("frame screenshot empty")
            return
        DOCTOR_STATE["frames"] = int(DOCTOR_STATE.get("frames", 0)) + 1
        renpy.store._frame_probe_busy = True
        _debug("frame check start cast=%s bytes=%d" % (probe.get("cast_key"), len(png)))
        t = threading.Thread(target=frame_probe_worker, args=(probe, png), daemon=True)
        try:
            t.start()
        except Exception as exc:
            renpy.store._frame_probe_busy = False
            _debug("frame thread start fail %s" % exc)

    def frame_tick():
        frame_plan_poll()
        probe = getattr(renpy.store, "_frame_probe", None)
        if not probe or getattr(renpy.store, "_frame_probe_busy", False):
            return
        # 等对话框和台词一起画出来再截，构图判断要看到立绘与对话栏的关系
        if not renpy.get_screen("say"):
            return
        if time.time() - float(probe.get("ts") or 0) < 0.45:
            return
        frame_probe_capture()

    def active_key():
        return getattr(renpy.store, "_key_override", None) or AI_KEY

    def should_fallback(exc):
        if not AI_FALLBACK_MODEL:
            return False
        if getattr(exc, "code", 0) in (400, 413):
            return True
        text = str(exc).lower()
        return any(k in text for k in ("context", "maximum", "too long", "length", "token"))

    def _url_parts(url):
        try:
            p = urllib.parse.urlsplit(str(url or "").strip())
        except Exception:
            return None
        if p.scheme.lower() not in ("http", "https") or not p.hostname:
            return None
        return p

    def _same_origin(a, b):
        pa, pb = _url_parts(a), _url_parts(b)
        if not pa or not pb:
            return False
        if pa.scheme.lower() != pb.scheme.lower():
            return False
        if (pa.hostname or "").lower() != (pb.hostname or "").lower():
            return False
        try:
            port_a = pa.port or (443 if pa.scheme.lower() == "https" else 80)
            port_b = pb.port or (443 if pb.scheme.lower() == "https" else 80)
        except Exception:
            return False
        return port_a == port_b

    def _host_is_private(host):
        try:
            infos = socket.getaddrinfo(host, None)
        except Exception:
            return True
        if not infos:
            return True
        for info in infos:
            ip = info[4][0]
            try:
                addr = ipaddress.ip_address(ip)
            except ValueError:
                continue
            if (addr.is_private or addr.is_loopback or addr.is_link_local
                    or addr.is_multicast or addr.is_reserved or addr.is_unspecified):
                return True
        return False

    def _check_url(url, allow_private=False, trusted_origin=""):
        """只允许 http/https；默认拒绝本机/内网，下载地址需与可信端点同源或公网。"""
        p = _url_parts(url)
        if not p:
            raise RuntimeError("不安全的地址：只允许 http/https")
        if not allow_private and not (trusted_origin and _same_origin(url, trusted_origin)):
            if _host_is_private(p.hostname):
                raise RuntimeError("不安全的地址：不能访问本机或内网")
        return p

    class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
        """POST 不允许跨域重定向；GET 跨域时去掉 Authorization。"""

        def __init__(self, allow_private=False, trusted_origin=""):
            self.allow_private = allow_private
            self.trusted_origin = trusted_origin

        def redirect_request(self, req, fp, code, msg, headers, newurl):
            _check_url(newurl, self.allow_private, self.trusted_origin)
            same = _same_origin(newurl, req.full_url)
            if req.get_method() == "POST" and not same:
                raise urllib.error.HTTPError(newurl, code, "拒绝跨域重定向", headers, fp)
            new_req = urllib.request.HTTPRedirectHandler.redirect_request(
                self, req, fp, code, msg, headers, newurl
            )
            if new_req is not None and not same:
                try:
                    new_req.remove_header("Authorization")
                except Exception:
                    pass
            return new_req

    def _open_url(req, timeout, allow_private=False, trusted_origin=""):
        _check_url(req.full_url, allow_private, trusted_origin)
        handlers = [_SafeRedirectHandler(allow_private, trusted_origin)]
        if _CA_FILE:
            handlers.insert(0, urllib.request.HTTPSHandler(
                context=ssl.create_default_context(cafile=_CA_FILE)
            ))
        opener = urllib.request.build_opener(*handlers)
        return opener.open(req, timeout=timeout)

    def _read_limited(resp, limit, deadline=None):
        chunks = []
        total = 0
        while True:
            if deadline is not None and time.time() > deadline:
                raise RuntimeError("响应超时")
            part = resp.read(65536)
            if not part:
                break
            total += len(part)
            if total > limit:
                raise RuntimeError("响应超过上限 %d 字节" % limit)
            chunks.append(part)
        return b"".join(chunks)

    def gal_log_model_name(value):
        name = str(value or "-")
        return name if re.fullmatch(r"[A-Za-z0-9_.:/-]{1,140}", name) else "(custom)"

    def _post_json(url, payload, key, timeout, extra_headers=None, request_kind="json"):
        _check_url(url, allow_private=True)
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
        )
        req.add_header("Content-Type", "application/json")
        if key:
            req.add_header("Authorization", "Bearer " + key)
        for hk, hv in (extra_headers or {}).items():
            req.add_header(hk, hv)

        rid = uuid.uuid4().hex
        model = gal_log_model_name(payload.get("model"))
        started = time.monotonic()
        gal_request_log("event=model.request status=start rid=%s kind=%s model=%s endpoint_host=%s" %
                        (rid, request_kind, model, voice_log_host(url)))
        try:
            with _open_url(req, timeout, allow_private=True) as resp:
                raw = _read_limited(resp, 20 * 1024 * 1024, time.time() + timeout)
                code = resp.getcode()
            result = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            gal_request_log("event=model.request status=error rid=%s error_type=%s http_code=%s latency_ms=%d" %
                            (rid, type(exc).__name__, getattr(exc, "code", "-"), (time.monotonic()-started)*1000))
            raise
        gal_request_log("event=model.request status=response rid=%s http_code=%s bytes=%d latency_ms=%d" %
                        (rid, code, len(raw), (time.monotonic()-started)*1000))
        return result

    def _repair_quotes(raw):
        """模型常在台词里直接写英文双引号，把 JSON 截断。
        逐字符扫，字符串内部不属于结构的裸引号替换成中文引号，结构保持完整。"""
        out = []
        in_str = False
        esc = False
        n = len(raw)
        for i, ch in enumerate(raw):
            if esc:
                out.append(ch)
                esc = False
                continue
            if ch == "\\":
                out.append(ch)
                esc = True
                continue
            if ch == '"':
                if not in_str:
                    in_str = True
                    out.append(ch)
                    continue
                j = i + 1
                while j < n and raw[j] in " \t\r\n":
                    j += 1
                nxt = raw[j] if j < n else ""
                if nxt in (",", "}", "]", ":", ""):
                    in_str = False
                    out.append(ch)
                else:
                    out.append("“")
                continue
            out.append(ch)
        return "".join(out)

    def _extract_json(text):
        text = text.strip()
        if text.startswith("```"):
            first = text.find("\n")
            if first >= 0:
                text = text[first + 1:]
            if text.rstrip().endswith("```"):
                text = text.rstrip()[:-3]
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("no json object in response: %r" % text[:160])
        raw = text[start:end + 1]
        # 先原样解析：尾逗号清理会改到字符串字面量里的 ", }"，不能无条件执行
        try:
            return json.loads(raw, strict=False)
        except ValueError as exc:
            # 模型偶尔在字符串里塞未转义的换行或控制字符，清一遍再试
            clean = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", raw)
            try:
                return json.loads(clean, strict=False)
            except ValueError:
                tidy = re.sub(r",\s*([}\]])", r"\1", clean)
                try:
                    return json.loads(tidy, strict=False)
                except ValueError:
                    fixed = _repair_quotes(tidy)
                    try:
                        return json.loads(fixed, strict=False)
                    except ValueError:
                        pos = getattr(exc, "pos", 0) or 0
                        raise ValueError(
                            "bad json at %d: ...%s..." % (pos, raw[max(0, pos - 60):pos + 60])
                        )

    def _doctor_note(kind, detail=""):
        DOCTOR_STATE["errors"] = int(DOCTOR_STATE.get("errors", 0)) + 1
        DOCTOR_EVENTS.append((time.time(), kind, str(detail)[:200]))
        if len(DOCTOR_EVENTS) > 30:
            del DOCTOR_EVENTS[:-30]
        _debug("doctor event %s %s" % (kind, str(detail)[:160]))

    def doctor_repair(raw, st, kind="batch"):
        """坏 JSON 修复：开关开了用 option 模型，关着且走 harness 就用 harness 模型。"""
        if not raw:
            return None
        use_option = doctor_on()
        use_harness = (not use_option) and doctor_harness_on()
        if not (use_option or use_harness):
            return None
        if int(DOCTOR_STATE.get("fixes", 0)) >= DOCTOR_MAX:
            _debug("doctor repair skipped: limit %d" % DOCTOR_MAX)
            return None
        if use_harness:
            # bat 请求里已经让 harness 派子代理修，引擎不再单独发 doctor 请求
            _debug("doctor harness repair %s delegated to batch" % kind)
            return None
        DOCTOR_STATE["fixes"] = int(DOCTOR_STATE.get("fixes", 0)) + 1
        if kind in ("batch", "director"):
            schema = _format_spec(director=kind == "director")
            if kind == "director":
                schema += chr(10) + "保留发言拍中已有的 line_id 和原说话人；旁白省略 line_id。"
            max_tokens = 2200
            need = "beats"
        else:
            schema = '{"lines":[{"order":1,"text":"台词"}]}'
            max_tokens = 600
            need = "lines"
        system = (
            "你是视觉小说引擎的自愈模型。只输出合法 JSON，不要解释，不要改剧情，"
            "把下面这段坏掉的输出修成可用格式。"
        )
        user = (
            "格式：" + chr(10) + schema + chr(10) + chr(10)
            + "坏掉的输出：" + chr(10) + str(raw)[:12000]
        )
        payload = {
            "model": doctor_model(),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "enable_thinking": False,
            "stream": False,
        }
        try:
            data = _post_json(doctor_endpoint(), payload, doctor_key(), AI_TIMEOUT, request_kind="doctor_repair")
            obj = _extract_json(data["choices"][0]["message"]["content"])
            if not obj.get(need):
                raise ValueError("doctor empty " + need)
            _debug("doctor repair %s ok" % kind)
            return obj
        except Exception as exc:
            _debug("doctor repair %s fail %s" % (kind, exc))
            return None

    def doctor_safe_batch(st, detail=""):
        """主模型连续失败时补一段安全剧情；harness 关开关时交给 harness。"""
        if not (doctor_on() or doctor_harness_on()):
            return None
        if int(DOCTOR_STATE.get("fixes", 0)) >= DOCTOR_MAX:
            _debug("doctor safe skipped: limit %d" % DOCTOR_MAX)
            return None
        if doctor_harness_on():
            _debug("doctor harness safe delegated to batch")
            return None
        DOCTOR_STATE["fixes"] = int(DOCTOR_STATE.get("fixes", 0)) + 1
        recent = _history_text(st, min(HISTORY_FEED, 6))
        system = (
            _system_prompt(st, False, 4) + chr(10) + chr(10)
            + "你是自愈模型。主模型刚才失败了，请写 4 拍安全过渡："
            "不新增角色，不给 choices，不写结局，台词简短，接着最近发生的事往下走。"
        )
        user = (
            _scene_brief(st) + chr(10)
            + "最近发生：" + chr(10) + recent + chr(10) + chr(10)
            + ("错误：" + str(detail)[:200] + chr(10) if detail else "")
            + "只给 4 个 beats。"
        )
        payload = {
            "model": doctor_model(),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.5,
            "max_tokens": 900,
            "response_format": {"type": "json_object"},
            "enable_thinking": False,
            "stream": False,
        }
        try:
            data = _post_json(doctor_endpoint(), payload, doctor_key(), AI_TIMEOUT, request_kind="doctor_safe")
            batch = _extract_json(data["choices"][0]["message"]["content"])
            if not batch.get("beats"):
                raise ValueError("doctor safe empty")
            _debug("doctor safe batch %d beats" % len(batch.get("beats") or []))
            return batch
        except Exception as exc:
            _debug("doctor safe fail %s" % exc)
            return None

    def _doctor_switch(reason):
        if harness_available():
            _debug("doctor switch skipped: harness mode")
            return
        if getattr(renpy.store, "_doctor_override", False):
            return
        renpy.store._doctor_override = True
        if AI_FALLBACK_MODEL:
            gal_select_fallback()
        else:
            renpy.store._model_override = doctor_model()
            renpy.store._endpoint_override = doctor_endpoint()
            renpy.store._key_override = doctor_key()
        DOCTOR_STATE["switches"] = int(DOCTOR_STATE.get("switches", 0)) + 1
        _debug("doctor switch model=%s reason=%s" % (
            AI_FALLBACK_MODEL or doctor_model(), reason,
        ))

    def _doctor_tick(gen=None):
        if gen is not None and getattr(renpy.store, "_doctor_gen", 0) != gen:
            return
        if not doctor_watch_on():
            return
        now = time.time()
        box = getattr(renpy.store, "_prefetch_box", None)
        if box and not box.get("done"):
            started = float(box.get("started") or now)
            if now - started > DOCTOR_STALL:
                _debug("doctor stall %.0fs" % (now - started))
                invalidate_prefetch()
                if harness_available():
                    _debug("doctor harness stall cleared")
                else:
                    _doctor_switch("stall")
        if harness_available():
            return
        recent = [e for e in DOCTOR_EVENTS if now - e[0] <= max(DOCTOR_INTERVAL * 2, 20)]
        if len(recent) >= 2:
            _doctor_switch("errors=%d" % len(recent))

    def _doctor_loop(gen):
        last_voice_error = ""
        while getattr(renpy.store, "_doctor_gen", 0) == gen:
            time.sleep(DOCTOR_INTERVAL)
            if getattr(renpy.store, "_doctor_gen", 0) != gen:
                return
            try:
                _doctor_tick(gen)
                path = os.path.join(config.basedir, "model_requests.log")
                if not os.path.isfile(path):
                    continue
                with gal_debug_lock, open(path, "rb") as stream:
                    stream.seek(max(0, os.fstat(stream.fileno()).st_size - 32768))
                    tail = stream.read(32768).decode("utf-8", "replace")
                errors = [line for line in tail.splitlines()
                          if " event=voice.request status=http_error " in line]
                if errors and errors[-1] != last_voice_error:
                    last_voice_error = errors[-1]
                    _debug("event=doctor.suggestion kind=voice 建议核对语音供应商、模型权限和音色配置")
            except Exception as exc:
                _debug("doctor tick fail %s" % exc)

    def stop_doctor():
        renpy.store._doctor_gen = int(getattr(renpy.store, "_doctor_gen", 0)) + 1
        renpy.store._doctor_thread = None

    def start_doctor():
        if not doctor_watch_on():
            _debug("doctor off: no model and no harness")
            return
        # 换模型/新开局时让旧巡检线程自然退出，避免旧线程继续改 store。
        gen = int(getattr(renpy.store, "_doctor_gen", 0)) + 1
        renpy.store._doctor_gen = gen
        t = threading.Thread(target=_doctor_loop, args=(gen,), daemon=True)
        t.start()
        renpy.store._doctor_thread = t
        _debug("doctor start model=%s interval=%ds stall=%ds" % (
            doctor_model(), DOCTOR_INTERVAL, DOCTOR_STALL,
        ))

    WATCHED_BOXES = (
        "_art_box", "_compress_box", "_diary_box", "_chapter_box",
        "_voice_box", "_detail_box",
    )

    def _box_watchdog():
        now = time.time()
        for name in WATCHED_BOXES:
            box = getattr(renpy.store, name, None)
            if not box or box.get("done"):
                continue
            started = float(box.get("started") or now)
            if now - started > 300:
                _debug("box stalled %s %.0fs" % (name, now - started))
                setattr(renpy.store, name, None)

    def _line_text(rec):
        who = rec.get("character") or rec.get("speaker")
        text = rec.get("text", "")
        if is_narrator(who):
            return text
        return str(who).strip() + "：" + text

    def _history_text(st, limit=8):
        rows = []
        for item in _history_records(st, limit):
            who = item.get("character") or item.get("speaker") or "旁白"
            rows.append(who + "：" + item.get("text", ""))
        return "\n".join(rows) if rows else "（故事刚开始）"

    def estimate_tokens(text):
        return int(len(text) / 1.5)

    def estimate_request(st):
        base = _personas_prompt() + _format_spec() + st.get("summary", "")
        base += _history_text(st, HISTORY_FEED)
        return estimate_tokens(base)

    def http_compress(st):
        cursor = st.get("cursor", 0)
        upto = cursor - SUMMARY_KEEP
        since = st.get("summary_until", 0)
        if upto <= since:
            return None
        old = [
            r for r in _history_records(st)
            if since < r.get("turn", 0) <= upto
        ]
        if not old:
            return None
        body = chr(10).join(
            _line_text(r) for r in old[-80:]
        )
        prev = st.get("summary", "")
        prompt = (
            (("已有摘要：" + chr(10) + prev + chr(10) + chr(10)) if prev else "")
            + "请把下面这段剧情合并进摘要，控制在 300 字以内，保留人物关系变化、关键事件、长期设定。只输出摘要正文。"
            + chr(10) + chr(10) + body
        )
        payload = {
            "model": active_model(),
            "messages": [
                {"role": "system", "content": "你负责把视觉小说剧情压缩成长期摘要，只输出摘要正文。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 600,
        }
        data = _post_json(active_endpoint(), payload, active_key(), AI_TIMEOUT, request_kind="compress")
        return data["choices"][0]["message"]["content"].strip(), upto

    def ensure_compress(st):
        if gal_mock_mode():
            return
        if harness_available():
            # 上下文由外层 agent 管理，引擎不再单独调压缩 API
            return
        if estimate_request(st) < CONTEXT_LIMIT * CONTEXT_RATIO * 0.9:
            return
        if getattr(renpy.store, "_compress_box", None) is not None:
            return
        snapshot = json.loads(json.dumps(st))
        box = {"done": False, "result": None, "started": time.time()}

        def run():
            try:
                box["result"] = http_compress(snapshot)
            except Exception:
                box["result"] = None
            finally:
                box["done"] = True

        threading.Thread(target=run, daemon=True).start()
        renpy.store._compress_box = box
        if AI_FALLBACK_MODEL and getattr(renpy.store, "_model_override", None) is None:
            gal_select_fallback()
            _debug("context compress: switch to %s" % AI_FALLBACK_MODEL)

    def drain_compress(st):
        box = getattr(renpy.store, "_compress_box", None)
        if not box or not box.get("done"):
            return
        res = box.get("result")
        renpy.store._compress_box = None
        if res:
            summary, upto = res
            st["summary"] = summary
            st["summary_until"] = upto
            _debug("compressed until %d" % upto)

    def fit_feed(st):
        """返回压到预算内的历史条数；超预算时切备用模型。"""
        budget = CONTEXT_LIMIT * CONTEXT_RATIO
        base = _personas_prompt() + _format_spec() + st.get("summary", "")
        feed = HISTORY_FEED
        while feed > 2:
            sample = _history_text(st, feed)
            if estimate_tokens(base + sample) <= budget:
                break
            feed = max(2, feed // 2)
        if feed < HISTORY_FEED and AI_FALLBACK_MODEL:
            if getattr(renpy.store, "_model_override", None) is None:
                gal_select_fallback()
                _debug("context budget: switch to %s, feed=%d" % (AI_FALLBACK_MODEL, feed))
        return feed

    # ---------- 日记 ----------

    def diary_dir():
        base = os.path.join(slot_dir(), "diary")
        try:
            os.makedirs(base, exist_ok=True)
        except OSError:
            pass
        return base

    def diary_path(name):
        safe = "".join(c for c in str(name) if c not in '\\/:*?"<>|')
        return os.path.join(diary_dir(), (safe or "unknown") + ".json")

    def read_diary(name):
        try:
            with open(diary_path(name), "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if hasattr(data, "get") else {}
        except (OSError, ValueError):
            return {}

    def write_diary(name, data):
        try:
            _atomic_write_text(diary_path(name), json.dumps(data, ensure_ascii=False, indent=2))
        except OSError:
            pass

    def diary_brief(name):
        data = read_diary(name)
        events = [str(x) for x in (data.get("events") or [])][-6:]
        imps = data.get("impressions") or {}
        parts = []
        if events:
            parts.append("我做过：" + "；".join(events))
        if imps:
            parts.append("我对别人的印象：" + "；".join(
                "%s：%s" % (k, v) for k, v in list(imps.items())[:4]
            ))
        return chr(10).join(parts)

    def http_diary(name, st):
        recs = _history_records(st, DIARY_EVERY)
        if harness_available():
            # harness 模式没有独立的日记 API：只写本地摘要，不发 401 请求
            old = read_diary(name)
            old_events = [str(x) for x in (old.get("events") or [])]
            old_imps = old.get("impressions") or {}
            mine = [
                r.get("text", "") for r in recs
                if (r.get("character") or r.get("speaker")) == name
            ]
            events = (old_events + [x for x in mine if x])[-8:]
            if events:
                return {"events": events, "impressions": old_imps, "at": st.get("cursor", 0)}
            return
        body = chr(10).join(
            _line_text(r)
            for r in recs
        )
        old = read_diary(name)
        prompt = (
            "你是「%s」的日记。已有日记：" % name + chr(10)
            + json.dumps(old, ensure_ascii=False)[:1200] + chr(10) + chr(10)
            + "最近发生：" + chr(10) + body + chr(10) + chr(10)
            + "用这个角色的口吻更新日记：events 只留最近 8 条，每条一句话，写她自己做过的事；"
            + "impressions 是字典，键是别的角色名字，值是此刻对他的印象，一句话。"
            + '只输出 JSON：{"events":["..."],"impressions":{"角色名":"..."}}'
        )
        payload = {
            "model": role_model(),
            "messages": [
                {"role": "system", "content": _world_prompt(False) + chr(10) + "你是「%s」，写自己的日记，只输出 JSON。" % name},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.6,
            "max_tokens": 500,
            "response_format": {"type": "json_object"},
            "stream": False,
        }
        old_events = [str(x) for x in (old.get("events") or [])]
        old_imps = old.get("impressions") or {}
        try:
            data = _post_json(_chat_url(AI_ENDPOINT), payload, AI_KEY, AI_TIMEOUT, request_kind="diary")
            out = _extract_json(data["choices"][0]["message"]["content"])
            if not hasattr(out, "get"):
                raise ValueError("empty diary")
            events = [str(x) for x in (out.get("events") or [])][-8:]
            imps = out.get("impressions") or old_imps
        except Exception as exc:
            # 模型偶尔吐坏 JSON，退回本地摘要，日记文件必须有
            _debug("diary %s 解析失败，退回本地摘要：%s" % (name, exc))
            mine = [
                r.get("text", "") for r in _history_records(st)
                if (r.get("character") or r.get("speaker")) == name
            ][-DIARY_EVERY:]
            events = (old_events + [x for x in mine if x])[-8:]
            imps = old_imps
        if not events:
            return
        return {"events": events, "impressions": imps, "at": st.get("cursor", 0)}

    def ensure_diary(st):
        if gal_mock_mode():
            return
        if not DIARY_EVERY:
            return
        if st.get("cursor", 0) - st.get("_diary_at", 0) < DIARY_EVERY:
            return
        if getattr(renpy.store, "_diary_box", None):
            return
        roles = cast_roles(st)
        if not roles:
            return
        names = ["我"] + roles
        st["_diary_at"] = st.get("cursor", 0)
        snap = json.loads(json.dumps(st))

        results = {}

        def work():
            threads = []
            for n in names:
                t = threading.Thread(target=_diary_one, args=(n, snap, results))
                t.daemon = True
                t.start()
                threads.append(t)
            for t in threads:
                t.join(max(20, AI_TIMEOUT + 10))

        box = {"done": False, "result": results, "started": time.time()}
        t = threading.Thread(target=_guard(work, box))
        t.daemon = True
        t.start()
        renpy.store._diary_box = box
        _debug("diary start at turn %d roles=%s" % (st.get("cursor", 0), ",".join(names)))

    def _diary_one(name, snap, results):
        try:
            results[name] = http_diary(name, snap)
        except Exception as exc:
            _debug("diary %s fail %s" % (name, exc))

    def drain_diary():
        box = getattr(renpy.store, "_diary_box", None)
        if box and box.get("done"):
            renpy.store._diary_box = None
            for name, data in box["result"].copy().items():
                if data:
                    try:
                        write_diary(name, data)
                    except OSError as exc:
                        _debug("diary write failed: %s" % exc)

    def _guard(fn, box):
        def run():
            try:
                fn()
            except Exception as exc:
                _debug("background fail %s" % exc)
            finally:
                box["done"] = True
        return run

    # ---------- 多智能体 ----------

    def gal_present_roles(st):
        # Only explicit state limits the roster. Portrait visibility is not presence.
        if not st:
            return None
        for record in reversed(_history_records(st)):
            if record.get("scene") != st.get("scene"):
                break
            known = record.get("present_characters")
            if isinstance(known, (builtins.list, list)):
                present = set()
                for value in known:
                    if isinstance(value, str):
                        persona = resolve_persona(value)
                        present.add(persona["name"] if persona else value)
                return present
        return None

    def cast_roles(st=None):
        present = gal_present_roles(st)
        names = []
        for e in _persona_entries():
            if is_player_card(e):
                continue
            if e.get("name") and e["name"] not in names and (present is None or e["name"] in present):
                names.append(e["name"])
        return names

    def _role_persona(role):
        p = resolve_persona(role)
        if not p:
            return ""
        return _persona_body(p)

    def _read_rule_file(name):
        path = os.path.join(config.basedir, "game", name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read().strip()
            return text
        except OSError:
            return ""

    def _subagent_rules():
        """game/agent.md：一份子规则，注入所有子角色请求。"""
        return _read_rule_file("agent.md") or SUBAGENT_RULES_DEFAULT

    def _director_rules():
        """game/director.md：父合成规则。"""
        return _read_rule_file("director.md") or DIRECTOR_RULES_DEFAULT

    def _role_affection_brief(st, role):
        """子角色只知道自己这一份好感度，不拿别人的。"""
        e = resolve_persona(role)
        if not e:
            return ""
        if is_romance(e):
            a = affection_of(st, e["name"])
            return (
                "你的好感度：初始 %d，当前 %d，处于「%s」阶段；这一阶段%s"
                % (int(e.get("affection", 0)), a, _stage(a), _stage_hint(a))
                + chr(10)
                + "只按当前值写态度，不要把好感度数字写进台词。" + chr(10)
            )
        return "你没有好感度系统，不写恋爱向的心动、试探和暧昧，按人物卡的身份与关系写。" + chr(10)

    def _role_lines_from(raw):
        """把子智能体的输出尽量拆成 (order, 台词)：对象、数组、纯文本都认。"""
        text = str(raw or "").strip()
        if not text:
            return None
        text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
        data = None
        try:
            data = json.loads(text, strict=False)
        except ValueError:
            data = None
        if data is None:
            a, b = text.find("["), text.rfind("]")
            if a >= 0 and b > a:
                try:
                    data = json.loads(text[a:b + 1], strict=False)
                except ValueError:
                    data = None
        if data is None:
            try:
                data = _extract_json(text)
            except Exception:
                data = None
        items = None
        # Ren'Py store 里的 list 不是 builtin list，isinstance 会误判
        if type(data).__name__ == "list":
            items = data
        elif hasattr(data, "get"):
            if type(data.get("lines")).__name__ == "list":
                items = data["lines"]
            elif data.get("text"):
                items = [data]
        if items is None:
            return None
        out = []
        for item in items:
            if hasattr(item, "get"):
                txt = str(item.get("text") or item.get("line") or "").strip()
                try:
                    order = int(item.get("order", len(out) + 1))
                except Exception:
                    order = len(out) + 1
            elif type(item).__name__ in ("str", "unicode"):
                txt = item.strip()
                order = len(out) + 1
            else:
                continue
            txt = txt.strip().strip("「」\"'").strip()
            if txt:
                out.append((order, txt))
        return sorted(out, key=lambda item: item[0])[:SUBAGENT_LINES] if out or not items else None

    def gal_story_chat(endpoint, payload, key, kind, turn, role=None):
        if not harness_available():
            return _post_json(endpoint, payload, key, AI_TIMEOUT, request_kind=kind)
        request = {"stage": kind, "turn": turn, "messages": payload["messages"],
                   "output_format": "json_object" if payload.get("response_format") else "text",
                   **harness_doctor_meta()}
        if role is not None:
            request["role"] = role
        rid = harness_post("story_chat", request)
        gal_request_log("event=harness.request status=start rid=%s kind=%s turn=%s" % (rid, kind, turn))
        response = harness_wait(rid)
        content = response.get("content") if response else None
        if not isinstance(content, str):
            gal_request_log("event=harness.request status=%s rid=%s kind=%s" %
                            ("invalid" if response else "timeout", rid, kind))
            raise RuntimeError("harness 宿主未返回 %s 的文本响应，请检查 story_chat 支持" % kind)
        gal_request_log("event=harness.request status=response rid=%s kind=%s" % (rid, kind))
        return {"choices": [{"message": {"content": content}}]}

    def gal_parse_event_cue(value, phase):
        if not isinstance(value, Mapping) or phase not in ("open", "play", "close"):
            return None
        cause = value.get("cause")
        ending = value.get("ending")
        if not isinstance(cause, str) or not cause.strip():
            return None
        if phase == "close" and (not isinstance(ending, str) or not ending.strip()):
            return None
        return {"phase": phase, "cause": cause.strip()[:600],
                "ending": ending.strip()[:600] if phase == "close" else ""}

    def gal_event_cue(st, count, full):
        for row in reversed(_history_records(st)):
            cue = row.get("gal_next_event")
            if isinstance(cue, Mapping):
                return gal_parse_event_cue(cue, cue.get("phase"))
        payload = {
            "model": active_model(),
            "messages": [
                {"role": "system", "content": chr(10).join((
                    _world_prompt(full), _writing_prompt(st, count),
                    _director_rules(), _personas_prompt(),
                    "你负责下一件事件的开场。只输出 JSON："
                    '{"cause":"一个可立即演出的具体起因"}。不要写台词，不要提前写结局。',
                ))},
                {"role": "user", "content": _scene_brief(st) + chr(10) + _history_text(st, HISTORY_FEED)},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 500,
            "enable_thinking": False,
            "stream": False,
        }
        try:
            result = gal_story_chat(active_endpoint(), payload, active_key(), "director", st.get("cursor", 0))
            return gal_parse_event_cue(_extract_json(result["choices"][0]["message"]["content"]), "open")
        except Exception as exc:
            _debug("event=director.plan status=failed error_type=%s" % type(exc).__name__)
            return None

    def gal_event_instruction(cue):
        if not cue:
            return ""
        phase = cue["phase"]
        instruction = {"open": "从起因开始演出", "play": "继续当前事件，不要开启下一件事",
                       "close": "即将收笔；在本轮自然收束到指定末尾，不要提前开启下一件事"}[phase]
        result = "【导演指令】" + instruction + "。" + chr(10) + "事件起因：" + cue["cause"] + chr(10)
        if phase == "close":
            result += "指定末尾：" + cue["ending"] + chr(10)
        return result + chr(10)

    def http_role_lines(role, st, full=False, event_cue=None):
        recent = _history_text(st, max(1, HISTORY_FEED))
        base = (
            _subagent_rules() + chr(10) + chr(10)
            + gal_event_instruction(event_cue)
            + _world_prompt(full) + chr(10) + chr(10)
            + "你现在只扮演「%s」一个人。" % role + chr(10) + chr(10)
            + _role_persona(role) + chr(10) + chr(10)
            + _role_affection_brief(st, role)
            + (("你的日记摘要：" + diary_brief(role) + chr(10)) if diary_brief(role) else "")
        )
        if full:
            base += "【重新注入】以上设定是当前唯一有效的版本，此前所有与它冲突的描写都作废。" + chr(10)
        user = "最近发生：" + chr(10) + recent + chr(10) + chr(10) + "接下来你会说什么。"
        json_system = (
            base
            + "只输出 JSON：{\"lines\":[{\"order\":1,\"text\":\"台词\"}]}，"
            + "可写 0 到 %d 句；沉默时输出 {\"lines\":[]}。按你说话的先后排 order，text 只写台词本身不要引号。" % SUBAGENT_LINES
        )
        payload = {
            "model": role_model(),
            "messages": [
                {"role": "system", "content": json_system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.8,
            "max_tokens": 500,
            "response_format": {"type": "json_object"},
            "stream": False,
        }
        if AI_THINKING > 0:
            payload["enable_thinking"] = True
            payload["thinking_budget"] = AI_THINKING
        attempts = [payload]
        retry = dict(payload)
        retry["enable_thinking"] = False
        retry.pop("thinking_budget", None)
        retry["max_tokens"] = max(600, payload["max_tokens"])
        attempts.append(retry)
        last_content = ""
        for idx, p in enumerate(attempts):
            try:
                data = gal_story_chat(_chat_url(AI_ENDPOINT), p, AI_KEY, "subagent", st.get("cursor", 0), role)
                last_content = str(data["choices"][0]["message"].get("content") or "")
                items = _role_lines_from(last_content)
            except Exception as exc:
                _debug("subagent %s 第%d次失败：%s" % (role, idx + 1, exc))
                items = None
            if items is not None:
                lines = [
                    {"order": order, "character": role, "text": text}
                    for order, text in items
                ]
                lines.sort(key=lambda x: x["order"])
                _debug("subagent %s lines=%d" % (role, len(lines)))
                return lines
        fixed = doctor_repair(last_content, st, "role") if last_content else None
        if fixed:
            items = _role_lines_from(json.dumps(fixed, ensure_ascii=False))
            if items is not None:
                lines = [
                    {"order": order, "character": role, "text": text}
                    for order, text in items
                ]
                lines.sort(key=lambda x: x["order"])
                _debug("subagent %s doctor lines=%d" % (role, len(lines)))
                return lines
        # 最后兜底：不要 JSON，按行收台词，宁可格式松一点也不能丢角色
        plain_system = (
            base
            + "只写「%s」接下来要说的台词，每行一句；"
            "不要 JSON、不要编号、不要引号、不要解释。" % role
        )
        plain = {
            "model": role_model(),
            "messages": [
                {"role": "system", "content": plain_system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.8,
            "max_tokens": 300,
            "stream": False,
        }
        data = gal_story_chat(_chat_url(AI_ENDPOINT), plain, AI_KEY, "subagent", st.get("cursor", 0), role)
        content = str(data["choices"][0]["message"].get("content") or "")
        lines = []
        for raw_line in content.splitlines():
            txt = re.sub(r"^\s*(?:[-*•]|\d+[.、)])\s*", "", raw_line).strip()
            txt = txt.strip("「」\"'").strip()
            if not txt or txt.startswith(("{", "[")):
                continue
            lines.append({"order": len(lines) + 1, "character": role, "text": txt})
            if len(lines) >= SUBAGENT_LINES:
                break
        _debug("subagent %s plain lines=%d" % (role, len(lines)))
        return lines

    def subagent_lines(st, full=False, status=None, event_cue=None, roles=None):
        if roles is None:
            roles = cast_roles(st)
        if not roles:
            return []
        results = {}
        errors = []

        def work(role):
            try:
                results[role] = http_role_lines(role, st, full, event_cue)
            except Exception as exc:
                errors.append("%s:%s" % (role, exc))

        threads = []
        for role in roles:
            t = threading.Thread(target=work, args=(role,))
            t.daemon = True
            t.start()
            threads.append(t)
        for t in threads:
            # 子角色可能重试两次再走纯文本兜底，别在第一轮超时就把台词丢掉
            t.join(max(20, AI_TIMEOUT * 2))
        if errors:
            _debug("subagent errors %s" % "; ".join(errors))
        lines = []
        for role in roles:
            lines.extend(results.get(role) or [])
        if status is not None:
            status["answered"] = bool(results)
        if not lines:
            return []
        # 按 order 排序，同序号按角色出场顺序交错
        lines.sort(key=lambda x: (x["order"], roles.index(x["character"])))
        return lines

    def gal_bind_director_lines(beats, lines, reject=None):
        def invalid(reason):
            if reject is not None:
                reject.append(reason)
            return False

        if not beats or not isinstance(beats, (builtins.list, list)):
            return invalid("missing_or_invalid_beats")
        used = set()
        last = {}
        bound = []
        for position, beat in enumerate(beats, 1):
            if not isinstance(beat, Mapping):
                return invalid("invalid_beat:%d" % position)
            character = beat.get("character") or beat.get("speaker")
            if is_narrator(character):
                if "line_id" in beat or beat.get("is_speech") is True:
                    return invalid("invalid_narration:%d" % position)
                continue
            index = beat.get("line_id")
            if index is None:
                return invalid("missing_line_id:%d" % position)
            if type(index) is not int or not 1 <= index <= len(lines):
                return invalid("invalid_line_id:%d" % position)
            if index in used:
                return invalid("duplicate_line_id:%d" % index)
            line = lines[index - 1]
            persona = resolve_persona(character)
            name = persona["name"] if persona else character
            if name != line["character"]:
                return invalid("speaker_mismatch:%d" % index)
            if index <= last.get(name, 0):
                return invalid("speaker_order:%d" % index)
            if beat.get("is_speech") is False:
                return invalid("speech_flag:%d" % index)
            used.add(index)
            last[name] = index
            bound.append((beat, line))
        if len(used) != len(lines):
            return invalid("missing_line_references:%d" % (len(lines) - len(used)))
        for beat, line in bound:
            beat["character"] = line["character"]
            beat["text"] = line["text"]
            beat["is_speech"] = True
            beat.pop("line_id")
        return True

    def gal_director_retry_reason(reason, lines):
        if lines:
            references = "合法编号为 1 到 %d；每个编号必须且只能引用一次。" % len(lines)
        else:
            references = "本轮没有台词编号，所有拍都必须是旁白。"
        return (
            "上次导演整合未通过（%s；冒号后的拍位置从 1 开始，line_id 类重复和角色错误指原句编号）。"
            "请按本轮原始台词清单重新输出完整 JSON。%s "
            "不要补写无编号发言；旁白写 character=旁白、is_speech=false、standing=null，省略 line_id。"
            % (reason, references)
        )

    def subagent_batch(st, count=None):
        full = need_reinject(st)
        present = gal_present_roles(st)
        roles = cast_roles(st)
        if not roles and present is None:
            return harness_batch(st, count) if harness_available() else api_batch(st, count)
        status = {"answered": not roles}
        event_cue = gal_event_cue(st, count, full)
        lines = subagent_lines(st, full, status, event_cue, roles)
        if not lines and not status.get("answered") and present is None:
            _debug("subagent 全部失败，回退单模型")
            return harness_batch(st, count) if harness_available() else api_batch(st, count)
        script = chr(10).join(
            "line_id=%d %s：%s" % (i + 1, ln["character"], ln["text"]) for i, ln in enumerate(lines)
        )
        _cdata = load_chapters() if ENABLE_CHAPTER else {}
        _ccur = chapter_of(_cdata, _cdata.get("current", 1)) if ENABLE_CHAPTER else None
        _write = _writing_prompt(st, count, director=True)
        system = (
            _world_prompt(full) + chr(10) + chr(10)
            + ("【重新注入】以上设定是当前唯一有效的版本，此前所有与它冲突的描写都作废。" + chr(10) + chr(10) if full else "")
            + (_write + chr(10) + chr(10) if _write else "")
            + _director_rules() + chr(10) + chr(10)
            + _personas_prompt() + chr(10) + chr(10)
            + (_bgm_prompt() + chr(10) + chr(10) if _bgm_prompt() else "")
            + _format_spec(director=True)
        )
        if event_cue and event_cue["phase"] == "close":
            event_rule = (
                '本轮必须收束当前事件。仅在最终一拍确实达到指定末尾时，附加 '
                '"event_control":{"next_cause":"下一件事件的具体起因"}；本轮不得演出该新事件。'
                '若尚未达到，省略 event_control，下轮继续收束。'
            )
        else:
            event_rule = (
                '导演判断当前事件是否进入收尾。准备收尾时附加 '
                '"event_control":{"ending":"下一轮收笔时应达成的具体末尾"}。'
                '当前还需推进就省略 event_control。本轮不要提前演完指定末尾。'
            )
        user = (
            gal_event_instruction(event_cue) + event_rule + chr(10)
            + _scene_brief(st) + chr(10)
            + (("当前章节：" + _ccur.get("title", "") + chr(10)) if _ccur else "")
        ) + (
            "最近发生：" + chr(10) + _history_text(st, fit_feed(st)) + chr(10) + chr(10)
            + _affection_brief(st)
            + "本轮整合规则：发言拍恰好 %d 个，来自下列清单。整合轮没有固定总拍数。"
            "有可观察的动作、环境变化或衔接需要时，写成独立旁白拍。" % len(lines) + chr(10)
            + "各角色已经说出的内容（按顺序）：" + chr(10) + (script or "（没有角色发言）") + chr(10) + chr(10)
            + "每条原句各用一个发言拍，写整数 line_id、原说话人和立绘；同一角色维持原顺序。"
            "短句也保持原样。旁白写 character=旁白、is_speech=false、standing=null，省略 line_id。"
            + chr(10)
            + "最后给出 choices，选择和密度规则同前。"
        )
        payload = {
            "model": active_model(),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.7,
            # 合成只做排拍，输出长 JSON；开思考会把 token 全花在 reasoning 上，
            # 实测 content 为空、finish_reason=length，所以这里固定关思考
            "max_tokens": max(3000, (count or PLAN_AHEAD) * BEAT_MAX * 4),
            "response_format": {"type": "json_object"},
            "enable_thinking": False,
            "stream": False,
        }

        def _merge_meta(d):
            try:
                c = d["choices"][0]
                m = c.get("message") or {}
                return "finish=%s content=%d reasoning=%d" % (
                    c.get("finish_reason"),
                    len(m.get("content") or ""),
                    len(m.get("reasoning_content") or ""),
                )
            except Exception:
                return "no-response"

        batch = None
        content = ""
        for attempt in range(2):
            data = None
            content = ""
            failure = "request"
            try:
                data = gal_story_chat(active_endpoint(), payload, active_key(), "director", st.get("cursor", 0))
                content = data["choices"][0]["message"]["content"]
                failure = "json"
                candidate = _extract_json(content)
                reasons = []
                if not gal_bind_director_lines(candidate.get("beats"), lines, reasons):
                    failure = reasons[0]
                    raise ValueError("director line references invalid")
                batch = candidate
                break
            except Exception as exc:
                _debug("director merge attempt=%d reason=%s error=%s %s" %
                       (attempt + 1, failure, type(exc).__name__, _merge_meta(data)))
                if isinstance(exc, TimeoutError) or (
                    isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, TimeoutError)
                ):
                    break
                if attempt == 0:
                    payload["messages"] = [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user + chr(10) + gal_director_retry_reason(failure, lines)},
                    ]
                    if _merge_meta(data).startswith("finish=length "):
                        payload["max_tokens"] += 600
        if batch is None and content:
            fixed = doctor_repair(content, st, "director")
            if fixed and gal_bind_director_lines(fixed.get("beats"), lines):
                batch = fixed
        if batch is None:
            if not lines:
                raise ValueError("director returned no usable narration")
            _debug("director merge fallback: original lines")
            batch = {"beats": [], "choices": []}
            for line in lines:
                name = line["character"]
                batch["beats"].append({
                    "character": name,
                    "standing": standing_value(default_standing(resolve_persona(name))),
                    "is_speech": True,
                    "text": line["text"],
                })
        beats = batch["beats"]
        control = batch.pop("event_control", None)
        batch.pop("gal_next_event", None)
        if event_cue:
            if event_cue["phase"] == "close":
                next_cue = gal_parse_event_cue(
                    {"cause": control.get("next_cause")}, "open"
                ) if isinstance(control, Mapping) else None
                batch["gal_next_event"] = next_cue or event_cue
                if next_cue:
                    batch["_gal_close_cue"] = event_cue
            else:
                ending = control.get("ending") if isinstance(control, Mapping) else None
                batch["gal_next_event"] = gal_parse_event_cue(
                    {"cause": event_cue["cause"], "ending": ending}, "close"
                ) or gal_parse_event_cue(event_cue, "play")

        _debug("subagent merged lines=%d beats=%d" % (len(lines), len(beats)))
        if full:
            batch["_full_inject"] = True
            mark_injected(st)
            _debug("reinject full turn=%d model=%s" % (st.get("cursor", 0), active_model()))
        batch["subagent_lines"] = len(lines)
        return batch

    # ---------- harness 桥接 ----------

    def gal_mock_mode():
        return AI_MOCK and not harness_available()

    def harness_available():
        return USING_HARNESS and HOST == "harness"

    def harness_dir():
        base = os.path.join(config.basedir, "savedata", "harness")
        try:
            os.makedirs(base, exist_ok=True)
        except OSError:
            pass
        return base

    def harness_post(kind, payload):
        rid = "%d-%d-%s" % (
            int(time.time() * 1000), payload.get("turn", 0), uuid.uuid4().hex[:10]
        )
        data = dict(payload)
        data["id"] = rid
        data["kind"] = kind
        # 每个请求一个文件，多个预取线程同时发也不会互相覆盖
        path = os.path.join(harness_dir(), "request-%s.json" % rid)
        try:
            _atomic_write_text(path, json.dumps(data, ensure_ascii=False))
        except OSError as exc:
            raise RuntimeError("写 harness 请求失败：%s" % exc)
        return rid

    def harness_wait(rid, timeout=None):
        limit = timeout or HARNESS_TIMEOUT
        started = time.time()
        path = os.path.join(harness_dir(), "response-%s.json" % rid)
        while time.time() - started < limit:
            time.sleep(0.2)
            if not os.path.exists(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                continue
            if not hasattr(data, "get"):
                continue
            if data.get("id") and data.get("id") != rid:
                _debug("harness response id 不匹配：%s != %s" % (data.get("id"), rid))
                continue
            try:
                os.remove(path)
            except OSError:
                pass
            return data
        return None

    def harness_batch(st, count=None):
        _full = need_reinject(st)
        last_error = ""
        for _try in range(2):
            rid = harness_post("batch", {
                "turn": st.get("cursor", 0),
                "affection": st.get("affection", 0),
                "affections": dict(st.get("affections") or {}),
                "flags": list(st.get("flags", [])),
                "count": count or PLAN_AHEAD,
                "system": _system_prompt(st, _full, count),
                "history": _history_records(st, HISTORY_FEED),
                "path": list(st.get("path") or []),
                "summary": st.get("summary", ""),
                "summary_until": st.get("summary_until", 0),
                "scene": st.get("scene"),
                "chapter": st.get("chapter"),
                "instruction": (
                    "根据 system 里的人物卡和世界观，接着 history 写 %d 拍。"
                    "每一批必须推进一个新的具体事实、关系变化或线索，不要重复最近发生的场面，"
                    "不要把上一批已经解决的冲突换个说法再写一遍。输出指定 JSON 骨架。"
                    % (count or PLAN_AHEAD)
                ),
                **harness_doctor_meta(),
            })
            gal_request_log("event=harness.request status=start rid=%s kind=batch turn=%d attempt=%d" % (rid, st.get("cursor", 0), _try + 1))
            data = harness_wait(rid)
            gal_request_log("event=harness.request status=%s rid=%s kind=batch" % ("response" if data else "timeout", rid))
            if not data:
                last_error = "未收到 harness 宿主响应（%d 秒），请检查宿主连接" % HARNESS_TIMEOUT
                _doctor_note("harness_timeout", rid)
                continue
            batch = data.get("batch") or data.get("result") or {}
            if not batch.get("beats"):
                last_error = "no beats"
                _doctor_note("harness_empty", rid)
                continue
            if _full:
                batch["_full_inject"] = True
                mark_injected(st)
                _debug("reinject full turn=%d model=%s" % (st.get("cursor", 0), active_model()))
            return batch
        raise RuntimeError("harness 失败两次：%s" % last_error)

    def harness_art(kind, name, prompt, size):
        """模式 1：把生图任务交给 harness，由外层 agent 生成并落盘。"""
        if not harness_available():
            _debug("生图模式 1 需要 harness 启动，当前回退为不生成：%s/%s" % (kind, name))
            return
        try:
            rid = harness_post("art", {"asset_kind": kind, "name": name, "prompt": prompt, "size": size})
            gal_request_log("event=harness.request status=queued rid=%s kind=art asset_kind=%s" % (rid, kind))
        except Exception as exc:
            _debug("harness art fail %s" % exc)

    # ---------- 运行期生图 ----------

    def _read_url(url, key="", timeout=90, trusted_origin="", voice_request_id=""):
        rid = voice_request_id or uuid.uuid4().hex
        event = "voice.download" if voice_request_id else "model.resource"
        started = time.monotonic()
        gal_request_log("event=%s status=start rid=%s endpoint_host=%s" % (event, rid, voice_log_host(url)))
        try:
            _check_url(url, allow_private=False, trusted_origin=trusted_origin)
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "galgame/1.0")
            if key and trusted_origin and _same_origin(url, trusted_origin):
                req.add_header("Authorization", "Bearer " + key)
            with _open_url(req, timeout, allow_private=False, trusted_origin=trusted_origin) as resp:
                data = _read_limited(resp, 50 * 1024 * 1024, time.time() + timeout)
                http_code = resp.getcode()
        except Exception as exc:
            gal_request_log("event=%s status=error rid=%s error_type=%s http_code=%s" %
                            (event, rid, type(exc).__name__, getattr(exc, "code", "-")))
            raise
        gal_request_log("event=%s status=response rid=%s http_code=%s bytes=%d latency_ms=%d" %
                        (event, rid, http_code, len(data), (time.monotonic()-started)*1000))
        return data

    def image_generate(prompt, size, negative=""):
        """调生图模型，返回图片字节。原生异步接口与 OpenAI 兼容接口都支持。"""
        endpoint = _cfg("GALGAME_IMAGE_ENDPOINT")
        key = _cfg("GALGAME_IMAGE_KEY") or AI_KEY
        model = _cfg("GALGAME_IMAGE_MODEL", "wanx2.1-t2i-turbo")
        if not endpoint or not key:
            raise RuntimeError("没有生图端点或密钥")
        if "compatible-mode" in endpoint or "images/generations" in endpoint:
            endpoint = endpoint.rstrip("/")
            if not endpoint.endswith("/images/generations"):
                endpoint += "/images/generations"
            payload = {"model": model, "prompt": prompt, "n": 1, "size": size.replace("*", "x")}
            if negative:
                payload["negative_prompt"] = negative
            data = _post_json(endpoint, payload, key, 180, request_kind="image")
            items = data.get("data") or (data.get("output") or {}).get("results") or []
            for item in items:
                if item.get("url"):
                    return _read_url(item["url"], trusted_origin=endpoint)
                if item.get("b64_json"):
                    return base64.b64decode(item["b64_json"])
            raise RuntimeError("兼容接口没有返回图片")
        payload = {
            "model": model,
            "input": {"prompt": prompt},
            "parameters": {"size": size, "n": 1, "prompt_extend": False, "watermark": False},
        }
        if negative:
            payload["input"]["negative_prompt"] = negative
        data = _post_json(endpoint, payload, key, 120, {"X-DashScope-Async": "enable"}, request_kind="image")
        task = (data.get("output") or {}).get("task_id")
        if not task:
            raise RuntimeError("提交图像任务失败")
        parts = urllib.parse.urlsplit(endpoint)
        poll = "%s://%s/api/v1/tasks/%s" % (parts.scheme, parts.netloc, task)
        started = time.time()
        while time.time() - started < 180:
            time.sleep(5)
            raw = _read_url(poll, key, 60, trusted_origin=endpoint)
            state = json.loads(raw.decode("utf-8"))
            out = state.get("output") or {}
            if out.get("task_status") == "SUCCEEDED":
                for item in out.get("results") or []:
                    if item.get("url"):
                        return _read_url(item["url"], trusted_origin=endpoint)
                raise RuntimeError("任务成功但没有图片")
            if out.get("task_status") in ("FAILED", "CANCELED", "UNKNOWN"):
                raise RuntimeError("图像任务失败：%s" % out.get("task_status"))
        raise RuntimeError("等待图像任务超时")

    def save_image_bytes(raw, kind, name):
        base = {"scene": PIC_SCENE, "ui": PIC_UI}.get(kind, PIC_STANDING)
        if kind == "standing" and "/" in name:
            sub, stem = name.split("/", 1)
        else:
            sub, stem = "", name
        ext = ".png"
        if raw[:3] == b"\xff\xd8\xff":
            ext = ".jpg"
        rel = (str(sub) + "/" if sub else "") + str(stem) + ext
        path = _safe_under(base, rel)
        if not path:
            _debug("art skip unsafe path %s/%s" % (kind, name))
            return None
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
        except OSError:
            pass
        _atomic_write_bytes(path, raw)
        _debug("art saved %s" % path)
        return path

    def art_scene_prompt(scene):
        t, place = (scene.split("_", 1) + ["scene"])[:2]
        lights = {
            "day": "白天，自然光，光线均匀",
            "dusk": "黄昏，橙红斜光，影子拉长",
            "night": "夜里，冷色灯光加少量暖色点光",
        }
        return (
            "日系恋爱视觉小说背景插画。%s。时段：%s，%s。"
            "手绘赛璐璐上色，柔和景深，构图留出角色站位和文字框区域。"
            "画面里不得出现任何可辨认的文字、字母、数字或标志，不要人物不要水印。"
            % (place.replace("_", " "), t, lights.get(t, ""))
        )

    def _persona_look(entry):
        """生图用的外貌描述：优先「## 外貌与身体语言」，没有才退回开头段。"""
        body = _persona_body(entry)
        marker = "## 外貌与身体语言"
        if marker in body:
            part = body.split(marker, 1)[1]
            if chr(10) + "## " in part:
                part = part.split(chr(10) + "## ", 1)[0]
            lines = []
            for raw in part.splitlines():
                line = raw.strip().lstrip("-").strip()
                if line:
                    lines.append(line)
            if lines:
                return "；".join(lines)[:240]
        for block in body.split(chr(10) + chr(10)):
            line = " ".join(block.split())
            if line and not line.startswith("#") and not line.startswith("-"):
                return line[:120]
        return (entry or {}).get("name", "")

    def art_standing_prompt(character, sid):
        p = resolve_persona(character)
        note = ((p or {}).get("standings") or {}).get(sid) or {}
        look = _persona_look(p)
        clothes = str(note.get("clothes") or "").strip()
        action = str(note.get("action") or "自然站立").strip()
        expression = str(note.get("expression") or sid).strip()
        if clothes:
            detail = "这一张的衣服：%s；动作：%s；表情：%s" % (clothes, action, expression)
        else:
            detail = "这一张的动作：%s；表情：%s" % (action, expression)
        return (
            "日系恋爱视觉小说角色立绘，全身，站姿。固定设定：%s。"
            "%s。背景是均匀的纯白，无渐变、无投影、无地面、无道具，"
            "人物完整不裁切，居中竖构图，赛璐璐厚涂边缘干净，画面里不要任何文字。"
            % (look or (p or {}).get("name", character), detail)
        )

    def _run_art(jobs):
        for item in jobs:
            kind, name, prompt, size, mode = item
            try:
                if mode == 1:
                    harness_art(kind, name, prompt, size)
                elif mode == 2:
                    raw = image_generate(prompt, size, "文字, 水印, logo, 多个人物")
                    save_image_bytes(raw, kind, name)
            except Exception as exc:
                _debug("art %s/%s fail %s" % (kind, name, exc))

    def ensure_art(batch=None):
        if gal_mock_mode():
            return
        if getattr(renpy.store, "_art_box", None):
            return
        api_ok = bool(_cfg("GALGAME_IMAGE_ENDPOINT") and (_cfg("GALGAME_IMAGE_KEY") or AI_KEY))
        jobs = []
        if batch and GEN_SCENE in (1, 2):
            if GEN_SCENE == 2 and not api_ok:
                pass
            else:
                for sc in batch.get("scenes") or []:
                    if sc and not scene_file(sc):
                        jobs.append(("scene", sc, art_scene_prompt(sc), _cfg("GALGAME_IMAGE_SIZE", "1280*720"), GEN_SCENE))
        if batch and GEN_STANDING in (1, 2):
            if GEN_STANDING == 2 and not api_ok:
                pass
            else:
                seen = set()
                for b in batch.get("beats") or []:
                    sid = b.get("standing")
                    ch = b.get("character")
                    if not sid or is_narrator(ch):
                        continue
                    k = (str(ch), str(sid))
                    if k in seen or standing_file(ch, sid):
                        continue
                    seen.add(k)
                    jobs.append((
                        "standing", "%s/%s" % (standing_dir(resolve_persona(ch), ch), sid),
                        art_standing_prompt(ch, sid),
                        _cfg("GALGAME_IMAGE_SIZE_PORTRAIT", "960*1440"), GEN_STANDING,
                    ))
        if not jobs:
            return
        box = {"done": False, "started": time.time()}
        renpy.store._art_box = box
        t = threading.Thread(target=_guard(lambda: _run_art(jobs), box))
        t.daemon = True
        t.start()
        _debug("art queue %d 项" % len(jobs))

    def drain_art():
        box = getattr(renpy.store, "_art_box", None)
        if box and box.get("done"):
            renpy.store._art_box = None

    def ensure_ui_art():
        if gal_mock_mode():
            return
        """界面装饰缺图时按配置生成：choice / dialogue / title。"""
        if getattr(renpy.store, "_art_box", None):
            return
        api_ok = bool(_cfg("GALGAME_IMAGE_ENDPOINT") and (_cfg("GALGAME_IMAGE_KEY") or AI_KEY))
        todo = [
            ("choice", UI_CHOICE, GEN_UI_CHOICE, "选项按钮的底纹，横向长条，深色半透明，边缘柔和，无文字"),
            ("dialogue", UI_DIALOGUE, GEN_UI_DIALOGUE, "视觉小说对话栏底纹，横向长条，深色半透明，上下留白，无文字"),
            ("title", UI_TITLE, GEN_UI_TITLE, "视觉小说首页背景插画，空镜头，黄昏教室，无人物无文字"),
        ]
        jobs = []
        for name, path, mode, prompt in todo:
            if os.path.exists(path) or mode not in (1, 2):
                continue
            if mode == 2 and not api_ok:
                continue
            jobs.append(("ui", name, prompt, _cfg("GALGAME_IMAGE_SIZE", "1280*720"), mode))
        if not jobs:
            return
        box = {"done": False, "started": time.time()}
        renpy.store._art_box = box
        t = threading.Thread(target=_guard(lambda: _run_art(jobs), box))
        t.daemon = True
        t.start()
        _debug("ui art queue %d 项" % len(jobs))

    def _scene_brief(st):
        return (
            "当前场景：" + str(st.get("scene", DEFAULT_SCENE))
            + "。time 只能从 day、dusk、night 里选：day 是白天，dusk 是黄昏，night 是夜晚。"
            + "按剧情选，正文要和选择一致；一批里最多换一次场，换场那一拍把 scene_plan 的 at 写成它的序号（0 开始）。"
        )

    def http_batch(st, count=None):
        """Select the generation workflow independently of its transport."""
        if SUBAGENTS:
            return subagent_batch(st, count)
        return harness_batch(st, count) if harness_available() else api_batch(st, count)

    def api_batch(st, count=None):
        _full = need_reinject(st)
        _summary = st.get("summary", "")
        _cdata = load_chapters() if ENABLE_CHAPTER else {}
        _cno = _cdata.get("current", 1)
        _ccur = chapter_of(_cdata, _cno) if ENABLE_CHAPTER else None
        _cnext = chapter_of(_cdata, _cno + 1) if ENABLE_CHAPTER else None
        _ctext = ""
        if _ccur:
            _ctext = (
                "当前章节：" + _ccur.get("title", "") + chr(10)
                + "本章开头：" + _ccur.get("begin", "") + chr(10)
                + "本章发展：" + _ccur.get("develop", "") + chr(10)
                + "本章结尾：" + _ccur.get("end", "") + chr(10)
            )
        if _cnext:
            _ctext += "下一章开头：" + _cnext.get("begin", "") + chr(10)
        _head = _ctext + (("长期摘要：" + chr(10) + _summary + chr(10) + chr(10)) if _summary else "")
        prompt = _head + _affection_brief(st) + _scene_brief(st) + chr(10) + ((
            "标记 %s，第 %d 回合，上次选择在第 %d 回合。" + chr(10)
            + "最近发生：" + chr(10) + "%s" + chr(10) + chr(10)
            + "接着规划并写 %d 拍。每拍 %d-%d 字，最多 %d 句 %d 行。"
            + "距离上次选择不足 %d 拍时不要给 choices；整段保持每 %d 拍 %d-%d 次选择。"
        ) % (
            ",".join(st["flags"]) or "无",
            st.get("cursor", 0),
            st.get("last_choice_turn", -99),
            _history_text(st, fit_feed(st)),
            PLAN_AHEAD,
            BEAT_MIN,
            BEAT_MAX,
            BEAT_SENTENCES,
            BEAT_LINES,
            CHOICE_GAP,
            CHOICE_WINDOW,
            CHOICE_MIN,
            CHOICE_MAX,
        ))
        if count and count != PLAN_AHEAD:
            prompt += "这次只给 %d 个 beats。" % count
        if CHOICE_MAX > 0 and st.get("cursor", 0) - st.get("last_choice_turn", -99) >= CHOICE_WINDOW:
            prompt += "这一块给 choices，单次 %d–%d 个选项。" % gal_menu_option_limits()
        payload = {
            "model": active_model(),
            "messages": [
                {"role": "system", "content": _system_prompt(st, _full, count)},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.75,
            "max_tokens": max(300, (count or PLAN_AHEAD) * BEAT_MAX * 2),
            "response_format": {"type": "json_object"},
            "stream": False,
        }
        if AI_THINKING > 0:
            payload["enable_thinking"] = True
            payload["thinking_budget"] = AI_THINKING
        else:
            payload["enable_thinking"] = False

        endpoint, key = active_endpoint(), active_key()
        gal_request_log("event=story.context turn=%d last_choice=%d" % (st.get("cursor", 0), st.get("last_choice_turn", -99)))
        try:
            data = _post_json(endpoint, payload, key, AI_TIMEOUT, request_kind="story")
        except Exception as exc:
            _doctor_note("http", exc)
            fixed = doctor_safe_batch(st, exc)
            if fixed:
                return fixed
            if not should_fallback(exc):
                raise
            payload["model"], endpoint, key = gal_fallback_route()
            try:
                data = _post_json(endpoint, payload, key, AI_TIMEOUT, request_kind="story")
            except Exception as exc2:
                _doctor_note("http2", exc2)
                fixed = doctor_safe_batch(st, exc2)
                if fixed:
                    return fixed
                raise
            gal_select_fallback()
            _debug("fallback to %s" % AI_FALLBACK_MODEL)
        content = data["choices"][0]["message"]["content"]
        try:
            batch = _extract_json(content)
        except ValueError as exc:
            gal_request_log("event=story.parse status=retry error_type=%s" % type(exc).__name__)
            data = _post_json(endpoint, payload, key, AI_TIMEOUT, request_kind="story")
            content = data["choices"][0]["message"]["content"]
            try:
                batch = _extract_json(content)
            except ValueError as exc2:
                gal_request_log("event=story.parse status=error error_type=%s" % type(exc2).__name__)
                _doctor_note("json", exc2)
                fixed = doctor_repair(content, st, "batch")
                if not fixed:
                    raise
                batch = fixed
        if not batch.get("beats"):
            _doctor_note("empty", "no beats")
            fixed = doctor_repair(content, st, "batch")
            if not fixed:
                fixed = doctor_safe_batch(st, "empty beats")
                if fixed:
                    return fixed
                raise ValueError("empty beats")
            batch = fixed
        _debug(
            "ok model=%s beats=%d choices=%d scenes=%s cast=%s"
            % (
                AI_MODEL,
                len(batch.get("beats") or []),
                len(batch.get("choices") or []),
                ",".join(batch.get("scenes") or []),
                ",".join(batch.get("cast") or []),
            )
        )
        if _full:
            batch["_full_inject"] = True
            mark_injected(st)
            _debug("reinject full turn=%d model=%s" % (st.get("cursor", 0), active_model()))
        return batch

    # ---------- 预取 ----------

    def gal_normalize_beat_cast(b):
        names, display = _parse_cast(b)
        if not names:
            names, display = [NARRATOR], NARRATOR
        if display == "全员":
            sid = b.get("standing")
            raw_map = b.get("standings")
            if hasattr(raw_map, "get") and raw_map.get("全员") is not None:
                sid = raw_map.get("全员")
            if sid is None:
                sid = 1
            sid = standing_value(sid)
            if not isinstance(sid, int):
                sid = 1
            b["character"] = "全员"
            b["characters"] = ["全员"]
            b["speaker"] = "全员"
            b["portrait"] = "全员"
            b["standings"] = {"全员": sid}
            b["standing"] = sid
            b["mood"] = sid
        elif len(names) == 1 and is_narrator(names[0]):
            # 旁白不显示名字、不加引号、不换立绘
            b["character"] = NARRATOR
            b["characters"] = []
            b["speaker"] = ""
            b["portrait"] = NARRATOR
            b["standings"] = {}
            b["standing"] = None
            b["mood"] = None
            b["is_speech"] = False
        else:
            given = {}
            given_ci = {}
            raw_map = b.get("standings")
            if hasattr(raw_map, "get"):
                for k, v in raw_map.items():
                    given[str(k).strip()] = v
                    given_ci[_pkey(k)] = v
            norm = []
            cast = {}
            for n in names:
                p = resolve_persona(n)
                name = p["name"] if p else n
                if name not in norm:
                    norm.append(name)
                sid = given.get(n)
                if sid is None:
                    sid = given_ci.get(_pkey(n))
                if sid is None:
                    sid = given.get(name)
                if sid is None:
                    sid = given_ci.get(_pkey(name))
                if sid is None and len(names) == 1:
                    sid = b.get("standing")
                    if sid is None:
                        sid = b.get("mood")
                if p is None or (name == "我" and not PLAYER_SPRITE):
                    cast[name] = None
                    continue
                allowed = standing_ids(p)
                val = "" if sid is None else str(sid).strip()
                if val not in allowed:
                    val = default_standing(p)
                cast[name] = standing_value(val)
            cast = {k: v for k, v in cast.items() if v is not None}
            display = "&".join(norm)
            b["character"] = display
            b["characters"] = norm
            b["speaker"] = display
            b["portrait"] = display
            b["standings"] = cast
            b["standing"] = cast.get(norm[0]) if norm else None
            b["mood"] = b["standing"]

    def gal_menu_option_limits():
        upper = max(1, settings_int("GALGAME_MENU_OPTIONS_MAX", CHOICE_MAX or 2))
        lower = min(upper, max(1, settings_int("GALGAME_MENU_OPTIONS_MIN", CHOICE_MIN or 1)))
        return lower, upper

    def sanitize_batch(batch, st, start_turn=None):
        # 先去掉和最近历史重复的拍，再分场景：被丢掉的复述不能影响换场
        _recent = {}
        for _r in st.get("history", []):
            _t = re.sub(r"\s+", "", str(_r.get("text") or ""))
            if len(_t) >= 12:
                _recent[_t] = True
        _kept = []
        original_beats = batch.get("beats", [])
        source_indices = []
        for source_index, _b in enumerate(original_beats):
            _k = re.sub(r"\s+", "", str(_b.get("text") or ""))
            if len(_k) >= 12 and _k in _recent:
                _debug("跳过重复拍：%s" % str(_b.get("text") or "")[:24])
                continue
            if len(_k) >= 12:
                _recent[_k] = True
            _kept.append(_b)
            source_indices.append(source_index)
        batch["beats"] = _kept
        close_cue = batch.pop("_gal_close_cue", None)
        if close_cue and (not source_indices or source_indices[-1] != len(original_beats) - 1):
            batch["gal_next_event"] = close_cue
        valid = set(TIME_PLACE)
        prev = st.get("scene", DEFAULT_SCENE)
        if "_" in prev:
            _pt, _pp = prev.split("_", 1)
            current = (_pt, _pp) if (_pt, _pp) in valid else (DEFAULT_TIME, DEFAULT_PLACE)
        else:
            current = (DEFAULT_TIME, DEFAULT_PLACE)
        _cursor = start_turn if start_turn is not None else st.get("cursor", 0)
        _last_switch = st.get("_scene_turn", -99)
        _bgm = st.get("bgm")
        _bgm_turn = st.get("_bgm_turn", -99)
        _batch_bgm = _bgm_norm(batch.get("bgm"))
        _plan = {}
        for _item in batch.get("scene_plan") or []:
            try:
                _at = int(_item["at"])
            except (KeyError, TypeError, ValueError):
                continue
            _tp = (_item.get("time"), _item.get("place"))
            if _tp in valid:
                _plan[_at] = _tp
        _changed = False
        for _i, b in enumerate(batch.get("beats", [])):
            # Online batches change the stage only at an explicit valid plan entry.
            _cand = _plan.get(source_indices[_i], current)
            if SCENE_LOCK:
                _turn = _cursor + _i
                # 模型可以选，但一批最多换一次，且要等够最短停留
                if _cand != current and not _changed and _turn - _last_switch >= SCENE_MIN_STAY:
                    _old = current
                    current = _cand
                    _last_switch = _turn
                    _changed = True
                    _debug("scene model turn=%d %s -> %s" % (
                        _turn, _old[0] + "_" + _old[1], current[0] + "_" + current[1],
                    ))
                elif _cand != current:
                    _debug("scene hold turn=%d %s -> %s" % (
                        _turn, current[0] + "_" + current[1], _cand[0] + "_" + _cand[1],
                    ))
            else:
                if _cand != current:
                    current = _cand
                    _last_switch = _cursor + _i
            b["scene"] = current[0] + "_" + current[1]

            _raw_bgm = b.get("bgm", _batch_bgm)
            _cand_bgm = _bgm_norm(_raw_bgm) if _raw_bgm not in (None, "") else _bgm
            if _cand_bgm is None:
                _cand_bgm = _bgm
            if _cand_bgm != _bgm:
                _turn = _cursor + _i
                if _turn - _bgm_turn < BGM_MIN_STAY:
                    _debug("bgm hold turn=%d %s -> %s" % (
                        _turn, _bgm, _cand_bgm,
                    ))
                    _cand_bgm = _bgm
                else:
                    _bgm = _cand_bgm
                    _bgm_turn = _turn
                    _debug("bgm change turn=%d -> %s" % (_turn, _bgm))
            b["bgm"] = _bgm

            if AUTO_CHARACTER and batch.get("new_characters"):
                b["gal_cast_source"] = {key: b[key] for key in ("character", "speaker", "standing", "standings", "mood", "is_speech") if key in b}
            gal_normalize_beat_cast(b)
        cast = []
        for b in batch.get("beats", []):
            sid = b.get("standing")
            if sid is not None and sid not in cast:
                cast.append(sid)
        batch["cast"] = cast[:4] or [standing_value(default_standing(HEROINE))]
        batch["scenes"] = sorted({b["scene"] for b in batch.get("beats", [])})
        batch["_bgm_turn"] = _bgm_turn
        clean_choices = []
        for _c in batch.get("choices") or []:
            if not hasattr(_c, "get"):
                continue
            _item = dict(_c)
            _label = str(_item.get("label") or _item.get("hint") or "").strip()
            if not _label:
                continue
            _item["label"] = _label
            _item["hint"] = str(_item.get("hint") or "").strip()
            try:
                _item["add"] = int(_item.get("add") or 0)
            except (TypeError, ValueError):
                _item["add"] = 0
            _item["target"] = str(_item.get("target") or "").strip()
            _item["react"] = str(_item.get("react") or "").strip()
            clean_choices.append(_item)
        menu_min, menu_max = gal_menu_option_limits()
        if len(clean_choices) > menu_max:
            _debug("choices 超限 %d -> %d" % (len(clean_choices), menu_max))
            clean_choices = clean_choices[:menu_max]
        if clean_choices and len(clean_choices) < menu_min:
            _debug("choices 不足 %d，本批不给选项" % len(clean_choices))
            clean_choices = []
        batch["choices"] = clean_choices
        gap = st.get("cursor", 0) - st.get("last_choice_turn", -99)
        lineage = _history_records(st, CHOICE_WINDOW)
        recent_choices = sum(rec.get("chosen") is not None for rec in lineage)
        if CHOICE_MAX <= 0 or recent_choices >= CHOICE_MAX:
            batch["choices"] = []
        elif batch.get("choices") and gap < CHOICE_GAP:
            batch["choices"] = []
        batch["_sanitized"] = True
        return batch

    def error_batch(exc):
        return {
            "beats": [{
                "character": NARRATOR,
                "speaker": "",
                "is_speech": False,
                "portrait": NARRATOR,
                "standing": None,
                "text": "模型调用失败：" + str(exc)[:90],
                "time": DEFAULT_TIME,
                "place": DEFAULT_PLACE,
                "mood": None,
            }],
            "choices": [],
            # 错误拍不能被重复文本去重吃掉，否则主循环会在同一拍空转
            "_sanitized": True,
        }

    def ai_batch(st, count=None):
        if gal_mock_mode():
            # 没有 Key 且没有 harness 时才走内置离线剧情。
            return mock_batch(st)
        last = None
        for attempt in range(1):
            try:
                batch = sanitize_batch(http_batch(st, count), st, start_turn=len(st.get("history", [])) + 1)
                if not batch.get("beats"):
                    raise RuntimeError("模型没有返回可用剧情")
                return batch
            except Exception as exc:
                last = exc
                _debug("fail attempt=%d %s" % (attempt + 1, str(exc)[:200]))
                time.sleep(0.6)
        renpy.store._ai_error = str(last)
        return error_batch(last)

    def invalidate_prefetch():
        renpy.store._prefetch_epoch = int(getattr(renpy.store, "_prefetch_epoch", 0)) + 1
        renpy.store._prefetch_box = None
        renpy.store._prefetch_busy_box = None

    def invalidate_background_boxes(keep_prefetch=None):
        if keep_prefetch is not None:
            keep_prefetch["epoch"] = int(getattr(renpy.store, "_prefetch_epoch", 0)) + 1
        invalidate_prefetch()
        if keep_prefetch is not None:
            renpy.store._prefetch_box = keep_prefetch
            if not keep_prefetch.get("done"):
                renpy.store._prefetch_busy_box = keep_prefetch
        update_batch_prediction(())
        # 换局时旧预取线程可能还在跑；不阻塞新局，旧结果会因 epoch 被丢弃
        renpy.store._branch_boxes = None
        for name in WATCHED_BOXES:
            try:
                setattr(renpy.store, name, None)
            except Exception:
                pass

    def start_prefetch(st, count=None, current=False):
        epoch = int(getattr(renpy.store, "_prefetch_epoch", 0))
        if current:
            existing = getattr(renpy.store, "_prefetch_box", None)
            if existing and not existing.get("consumed") and existing.get("epoch") == epoch:
                return existing
        box = {"done": False, "result": None, "started": time.time(), "epoch": epoch}
        # current=True 时先占住 _prefetch_box 再起线程，避免线程启动窗口里再起一份
        if current:
            renpy.store._prefetch_box = box
            renpy.store._prefetch_busy_box = box
            box["main"] = True

        snapshot = json.loads(json.dumps(st))
        if current:
            box["input"] = prefetch_input_key(snapshot)
            _debug("prefetch request id=%s tail=%s" % (box["input"][:12], snapshot.get("cursor")))
        def run():
            try:
                res = ai_batch(snapshot, count)
                if (not box.get("consumed") and
                        (int(getattr(renpy.store, "_prefetch_epoch", 0)) == epoch
                         or (box.get("main") and box.get("epoch") == getattr(renpy.store, "_prefetch_epoch", 0)))):
                    box["result"] = res
                else:
                    _debug("prefetch stale dropped epoch=%d" % epoch)
            except Exception as exc:
                box["error"] = str(exc)
            finally:
                box["done"] = True
                if getattr(renpy.store, "_prefetch_busy_box", None) is box:
                    renpy.store._prefetch_busy_box = None

        threading.Thread(target=run, daemon=True).start()
        return box

    def start_branches(st, choices):
        boxes = []
        for c in choices:
            st2 = json.loads(json.dumps(st))
            apply_choice(st2, c)
            boxes.append(start_prefetch(st2))
        return boxes

    def wait_prefetch(box, timeout=None):
        """Wait without consuming: branch merging may inspect the result later."""
        if not box or box.get("consumed"):
            return False
        if timeout is None:
            timeout = max(45.0, AI_TIMEOUT + 15.0)
            if harness_available():
                timeout = max(timeout, HARNESS_TIMEOUT * 2.0 + 15.0)
        limit = time.time() + timeout
        while not box["done"] and time.time() < limit:
            renpy.pause(0.05, hard=False)
        if not box["done"]:
            _debug("prefetch wait timeout %.0fs" % timeout)
        return bool(box["done"]) and box.get("epoch") == int(getattr(renpy.store, "_prefetch_epoch", 0))

    def take_prefetch(box, timeout=None):
        """Consume once, including timeout; late workers cannot reinsert a result."""
        if not box or box.get("consumed"):
            return None
        ready = wait_prefetch(box, timeout)
        box["consumed"] = True
        for name in ("_prefetch_box", "_prefetch_busy_box"):
            if getattr(renpy.store, name, None) is box:
                setattr(renpy.store, name, None)
        result = box.get("result") if ready else None
        box["result"] = None
        return result

    def chapters_path():
        return os.path.join(slot_dir(), "chapters.json")

    def normalize_chapters(data):
        out = {"current": 1, "chapters": []}
        try:
            out["current"] = max(1, int(data.get("current", 1)))
        except (TypeError, ValueError):
            out["current"] = 1
        seen = set()
        if not hasattr(data, "get"):
            return None
        raw = data.get("chapters", [])
        try:
            items = list(raw)
        except TypeError:
            items = []
        for item in items:
            if not hasattr(item, "get"):
                continue
            try:
                no = int(item.get("no", len(out["chapters"]) + 1))
            except (TypeError, ValueError):
                continue
            if no in seen:
                continue
            seen.add(no)
            out["chapters"].append({
                "no": no,
                "title": str(item.get("title") or ("第%d章" % no)).strip(),
                "begin": str(item.get("begin") or "").strip(),
                "develop": str(item.get("develop") or "").strip(),
                "end": str(item.get("end") or "").strip(),
            })
        out["chapters"].sort(key=lambda c: c["no"])
        if not out["chapters"]:
            return None
        last = out["chapters"][-1]["no"]
        if out["current"] > last:
            out["current"] = last
        return out

    _chapters_file_cache = [None, None, None]
    _chapters_missing_at = [0.0]

    def load_chapters(require_file=False):
        path = chapters_path()
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = None
        if mtime is not None and _chapters_file_cache[0] == path and _chapters_file_cache[1] == mtime:
            return json.loads(json.dumps(_chapters_file_cache[2]))
        if mtime is None and require_file:
            return None
        if mtime is None:
            # 文件不存在时不要每拍打一条；60 秒提示一次即可
            now = time.time()
            if now - _chapters_missing_at[0] > 60:
                _chapters_missing_at[0] = now
                _debug("chapters missing %s" % path)
            return normalize_chapters({
                "current": 1,
                "chapters": [{
                    "no": 1,
                    "title": "第一章",
                    "begin": "%s第一次正式登场，与「我」产生一个具体的接触点。" % HEROINE_NAME,
                    "develop": "围绕日常小事反复相处，误会和帮忙交替出现，好感度缓慢上升。",
                    "end": "两人关系稳定在能说上话的程度，故事自然推进到下一阶段。",
                }],
            })
        _debug("chapters load %s exists=True" % path)
        if mtime is not None:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                norm = normalize_chapters(data)
                if norm:
                    _debug("chapters parsed current=%d titles=%s" % (norm["current"], ",".join(c["title"] for c in norm["chapters"])))
                    _chapters_file_cache[0], _chapters_file_cache[1], _chapters_file_cache[2] = path, mtime, norm
                    return json.loads(json.dumps(norm))
                _debug("chapters normalize returned None")
            except Exception as exc:
                _debug("chapters read fail %s: %s" % (type(exc).__name__, exc))
        if require_file:
            return None
        return normalize_chapters({
            "current": 1,
            "chapters": [
                {
                    "no": 1,
                    "title": "第一章",
                    "begin": "%s第一次正式登场，与「我」产生一个具体的接触点。" % HEROINE_NAME,
                    "develop": "围绕日常小事反复相处，误会和帮忙交替出现，好感度缓慢上升。",
                    "end": "两人关系稳定在能说上话的程度，故事自然推进到下一阶段。",
                }
            ],
        })

    def save_chapters(data):
        _chapter_cache[0] = None
        _chapter_cache[1] = None
        _chapters_file_cache[0] = None
        _chapters_file_cache[1] = None
        try:
            _atomic_write_text(chapters_path(), json.dumps(data, ensure_ascii=False, indent=2))
        except OSError:
            pass

    def chapter_of(data, no):
        for c in data.get("chapters", []):
            if c.get("no") == no:
                return c
        return None

    def http_chapter(no, prev_end):
        prompt = (
            "这部%s视觉小说的女主角是「%s」，人设见下方人物卡。规划第 %d 章。上一章结尾：%s"
            % (GENRE, HEROINE_NAME, no, prev_end)
            + chr(10)
            + _persona_prompt() + chr(10)
            + "给出这一章的大致内容，只输出 JSON："
            + '{"title":"第%d章 标题","begin":"开头30字","develop":"发展40字","end":"结尾30字"}。' % no
            + (("故事没有结局，这一章结尾要留一个能自然接下一章的变化。"
                if ENDLESS else
                "故事可以收束；这一章结尾要留一个能自然接下一章的变化，最后一章可以收束。"))
        )
        payload = {
            "model": active_model(),
            "messages": [
                {"role": "system", "content": "你负责规划视觉小说的章节大纲，只输出 JSON。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 400,
            "response_format": {"type": "json_object"},
        }
        data = _post_json(active_endpoint(), payload, active_key(), AI_TIMEOUT, request_kind="chapter")
        obj = _extract_json(data["choices"][0]["message"]["content"])
        obj["no"] = no
        return obj

    def ensure_chapter(st):
        if gal_mock_mode():
            return
        if not ENABLE_CHAPTER:
            return
        if harness_available():
            # harness 模式不走章节 API，章节名由批处理返回
            return
        data = load_chapters()
        cur_no = data.get("current", 1)
        cur = chapter_of(data, cur_no)
        nxt = chapter_of(data, cur_no + 1)
        if nxt:
            return
        start = st.get("chapter_start", 1)
        used = st.get("cursor", 0) - start
        if used < int(CHAPTER_LENGTH * 0.6):
            return
        if getattr(renpy.store, "_chapter_box", None) is not None:
            return
        prev_end = (cur or {}).get("end", "")
        box = {"done": False, "result": None, "no": cur_no + 1, "started": time.time()}

        def run():
            try:
                box["result"] = http_chapter(cur_no + 1, prev_end)
            except Exception:
                box["result"] = None
            finally:
                box["done"] = True

        threading.Thread(target=run, daemon=True).start()
        renpy.store._chapter_box = box

    def drain_chapter(st):
        if not ENABLE_CHAPTER:
            return
        box = getattr(renpy.store, "_chapter_box", None)
        if not box or not box.get("done"):
            return
        renpy.store._chapter_box = None
        res = box.get("result")
        if res and res.get("title"):
            data = load_chapters()
            if not chapter_of(data, res["no"]):
                data.setdefault("chapters", []).append(res)
                save_chapters(data)
                _debug("chapter planned %s" % res["title"])

    def roll_chapter(st):
        if not ENABLE_CHAPTER:
            return
        data = load_chapters()
        cur_no = data.get("current", 1)
        start = st.get("chapter_start", 1)
        if st.get("cursor", 0) - start < CHAPTER_LENGTH:
            return
        nxt = chapter_of(data, cur_no + 1)
        if not nxt:
            return
        data["current"] = cur_no + 1
        save_chapters(data)
        st["chapter_start"] = st.get("cursor", 0)
        st["chapter"] = nxt.get("title", "第%d章" % (cur_no + 1))
        _debug("chapter roll to %s" % st["chapter"])

    def history_path():
        return os.path.join(slot_dir(), "history.json")

    _HISTORY_PROJECTION_CACHE = {}
    _HISTORY_PROJECTION_LOCK = threading.RLock()

    def _history_projection_stat(path):
        try:
            item = os.stat(path)
            return (item.st_dev, item.st_ino, item.st_size,
                    item.st_mtime_ns, item.st_ctime_ns)
        except OSError:
            return None

    def save_history(st):
        try:
            path = history_path()
            payload = json.dumps({
                "cursor": st.get("cursor", 0),
                "path": st.get("path", []),
                "chapter": st.get("chapter", ""),
                "chapter_start": st.get("chapter_start", 1),
                "bgm": st.get("bgm"),
                "_bgm_turn": st.get("_bgm_turn", -99),
                "records": st.get("history", []),
            }, ensure_ascii=False)
            key = os.path.realpath(path)
            with _HISTORY_PROJECTION_LOCK:
                signature = _history_projection_stat(path)
                if signature is not None and _HISTORY_PROJECTION_CACHE.get(key) == (payload, signature):
                    return
                _atomic_write_text(path, payload)
                _HISTORY_PROJECTION_CACHE[key] = (payload, _history_projection_stat(path))
        except Exception as exc:
            _debug("save_history fail %s" % exc)

    gal_batch_prediction = {}

    def update_batch_prediction(paths):
        """Keep explicit prediction scoped to the latest batch's unique assets."""
        wanted = dict.fromkeys(paths)
        for path in list(gal_batch_prediction):
            if path not in wanted:
                renpy.stop_predict(gal_batch_prediction.pop(path))
        for path in wanted:
            if path not in gal_batch_prediction:
                image = Image(path)
                renpy.start_predict(image)
                gal_batch_prediction[path] = image

    def append_batch(st, batch, path=None):
        beats = batch.get("beats") or []
        path = list(path if path is not None else st.get("path", []))
        start = len(st.get("history", [])) + 1
        already_sanitized = bool(batch.get("_sanitized"))
        recent = {}
        if not already_sanitized:
            for _r in st.get("history", []):
                _t = re.sub(r"\s+", "", str(_r.get("text") or ""))
                if len(_t) >= 12:
                    recent[_t] = True
        new_recs = []
        for i, b in enumerate(beats):
            _text = str(b.get("text") or "")
            _key = re.sub(r"\s+", "", _text)
            # 开场已经播过的长句不要再演一遍（模型偶尔会复述最近发生）
            if not already_sanitized and len(_key) >= 12 and _key in recent:
                _debug("跳过重复拍：%s" % _text[:24])
                continue
            if not already_sanitized and len(_key) >= 12:
                recent[_key] = True
            _ch = b.get("character") or b.get("speaker")
            if is_narrator(_ch):
                _ch = NARRATOR
            else:
                _ch = str(_ch).strip()
            rec = {
                "turn": start + len(new_recs),
                "path": path,
                "character": _ch,
                "characters": list(b.get("characters") or []),
                "speaker": "" if _ch == NARRATOR else _ch,
                "standings": dict(b.get("standings") or {}),
                "is_speech": bool(b.get("is_speech", _ch != NARRATOR)),
                "portrait": b.get("portrait") or _ch,
                "standing": b.get("standing"),
                "text": b.get("text", ""),
                "viewpoint_changed": b.get("viewpoint_changed") is True,
                "scene": b.get("scene", st.get("scene", DEFAULT_SCENE)),
                "mood": b.get("standing") or b.get("mood") or st.get("mood", DEFAULT_MOOD),
                "shot": b.get("shot", "medium"),
                "bgm": b.get("bgm"),
                "affection": st.get("affection", 0),
                "flags": list(st.get("flags", [])),
            }
            if "gal_cast_source" in b:
                rec["gal_cast_source"] = b["gal_cast_source"]
            present = b.get("present_characters")
            if isinstance(present, (builtins.list, list)) and all(isinstance(name, str) for name in present):
                rec["present_characters"] = list(present)
            st.setdefault("history", []).append(rec)
            new_recs.append(rec)
        if new_recs and SUBAGENTS:
            cue = batch.get("gal_next_event")
            if isinstance(cue, Mapping):
                normalized = gal_parse_event_cue(cue, cue.get("phase"))
                if normalized:
                    new_recs[-1]["gal_next_event"] = normalized
        if new_recs and AUTO_CHARACTER and batch.get("new_characters"):
            new_recs[0]["new_characters"] = batch["new_characters"]
        # Cached future beats must not overwrite the currently audible BGM.
        st["_bgm_turn"] = batch.get("_bgm_turn", st.get("_bgm_turn", -99))
        DOCTOR_STATE["last_progress"] = time.time()
        if path == list(st.get("path", [])) and getattr(renpy.store, "_doctor_override", False):
            renpy.store._doctor_override = False
            renpy.store._model_override = None
            renpy.store._endpoint_override = None
            renpy.store._key_override = None
            DOCTOR_EVENTS[:] = []
            _debug("doctor recovered")
        ensure_voice(st, new_recs)
        if new_recs and not ENDLESS and batch.get("ending"):
            new_recs[-1]["ending"] = str(batch["ending"])
        if batch.get("_full_inject"):
            mark_injected(st)
        if ENABLE_CHAPTER:
            _cdata = load_chapters(require_file=harness_available()) or {}
            _ccur = chapter_of(_cdata, _cdata.get("current", 1))
            _chapter = (_ccur or {}).get("title") or batch.get("chapter") or st.get("chapter", "第一章")
        else:
            _chapter = ""
        if path == list(st.get("path", [])):
            st["chapter"] = _chapter
        for _r in new_recs:
            _r["chapter"] = _chapter
        if batch.get("choices") and new_recs and not new_recs[-1].get("ending"):
            new_recs[-1]["choices"] = batch["choices"]
            # 主线上出现选项时，提前预热每个选项后面的几拍；
            # 只预热这一小段，没选的分支之后不再继续预取
            if list(path) == list(st.get("path", [])):
                try:
                    renpy.store._branch_boxes = (
                        list(new_recs[-1].get("path") or []),
                        start_branch_prefetch(
                            st, batch["choices"],
                            new_recs[-1].get("path", []), count=6,
                        ),
                        new_recs[-1]["turn"],
                    )
                except Exception as exc:
                    _debug("branch preheat fail %s" % exc)
        try:
            prediction_paths = []
            for sc in batch.get("scenes", []):
                _rel = scene_file(sc)
                if _rel:
                    prediction_paths.append(_rel)
            for b in batch.get("beats", []):
                sid = b.get("standing")
                if sid:
                    _rel = standing_file(b.get("character") or b.get("speaker"), sid)
                    if _rel:
                        prediction_paths.append(_rel)
            update_batch_prediction(prediction_paths)
        except Exception:
            pass
        if GEN_SCENE in (1, 2) or GEN_STANDING in (1, 2):
            ensure_art(batch)
        save_history(st)
        return len(new_recs)

    # ---------- 进入游戏前的加载 ----------
    LOAD_TEXT_TIMEOUT = 240
    LOAD_VOICE_TIMEOUT = 180

    def load_begin(title, text, mode, progress=0.05, resume_record=None):
        s = renpy.store
        s._load_title = title
        s._load_text = text
        s._load_progress = max(0.0, min(1.0, progress))
        s._load_mode = mode
        s._load_stage = 0
        s._load_started = time.time()
        s._load_phase_start = time.time()
        s._load_box = None
        s._load_rows = []
        s.gal_loading_resume_record = resume_record
        s._load_finish_at = 0.0
        s._load_done = False
        s._load_voice_logged = False
        s.gal_load_voice_submitted = set()
        _debug("load begin %s" % title)

    def _load_set(text, progress):
        s = renpy.store
        s._load_text = text
        s._load_progress = max(0.0, min(1.0, progress))

    def _load_time_progress(low, high, elapsed, timeout):
        frac = min(0.92, elapsed / max(1.0, timeout * 0.7))
        return low + (high - low) * frac

    def _voice_file_ready(rel):
        full = _safe_under(os.path.join(config.basedir, "game"), rel)
        if not full:
            return False
        try:
            return os.path.exists(full) and os.path.getsize(full) > 1024
        except OSError:
            return False

    def upcoming_records(st, limit=3):
        cur = int(st.get("cursor", 0) or 0)
        path = list(st.get("path") or [])
        rows = []
        for rec in st.get("history") or []:
            if not hasattr(rec, "get"):
                continue
            if list(rec.get("path") or []) != path:
                continue
            try:
                turn = int(rec.get("turn", 0) or 0)
            except (TypeError, ValueError):
                continue
            if turn > cur:
                rows.append(rec)
        rows.sort(key=lambda r: int(r.get("turn", 0) or 0))
        return rows[:max(1, int(limit))]

    def load_tick():
        try:
            _load_tick()
        except Exception as exc:
            _debug("load tick fail %s" % exc)
            renpy.store._load_done = True

    def _load_tick():
        s = renpy.store
        if s._load_done:
            return
        st = getattr(s, "st", None)
        if st is None:
            s._load_done = True
            return
        stage = int(getattr(s, "_load_stage", 0) or 0)
        now = time.time()

        if stage == 0:
            if s._load_mode == "start":
                box = getattr(s, "_load_box", None)
                if box is None:
                    box = start_prefetch(st, PLAN_AHEAD)
                    _debug("load prefetch begin mode=start count=%d" % PLAN_AHEAD)
                    s._load_box = box
                    s._load_phase_start = now
                if not box.get("done"):
                    if now - s._load_phase_start < LOAD_TEXT_TIMEOUT:
                        _load_set("正在生成剧情…", _load_time_progress(0.05, 0.5, now - s._load_phase_start, LOAD_TEXT_TIMEOUT))
                        return
                    _debug("load text timeout")
                res = take_prefetch(box, 0)
                append_batch(st, res if res else error_batch("未收到 harness 宿主响应，请检查宿主连接" if harness_available() else "首块生成失败，请重新开始"))
                s._load_rows = list(st.get("history") or [])
                s._load_stage = 1
                s._load_phase_start = now
                return

            current = s.gal_loading_resume_record
            rows = upcoming_records(st, 3)
            box = ensure_prefetch(st, current_record=current)
            if box is not None:
                if not rows and not box.get("done"):
                    if now - s._load_phase_start < LOAD_TEXT_TIMEOUT:
                        _load_set("正在生成后续剧情…", _load_time_progress(
                            0.05, 0.5, now - s._load_phase_start, LOAD_TEXT_TIMEOUT))
                        return
                    # A timeout does not cancel the worker. Leave ownership
                    # with the play loop so it cannot submit the same tail twice.
                elif box.get("done"):
                    drain_prefetch(st)
                    rows = upcoming_records(st, 3)
            if current is not None:
                rows.insert(0, current)
            s.gal_loading_resume_record = None
            s._load_rows = rows
            _load_set("正在准备存档中的台词和语音…", 0.5)
            ensure_voice(st, rows)
            s._load_stage = 1
            s._load_phase_start = now
            return

        if stage == 1:
            if s._load_mode == "resume":
                drain_prefetch(st)
            rows = list(getattr(s, "_load_rows", []) or [])
            if VOICE_ON:
                speech = []
                for rec in rows:
                    if not hasattr(rec, "get") or not rec.get("is_speech"):
                        continue
                    rel = rec.get("voice")
                    if rel:
                        speech.append(rec)
                total = len(speech)
                pending = 0
                done = 0
                failed = 0
                for rec in speech:
                    rel = rec.get("voice")
                    if _voice_file_ready(rel):
                        done += 1
                    elif _voice_pending_has(rel):
                        pending += 1
                    else:
                        failed += 1
                if total:
                    _load_set(
                        ("语音就绪 %d/%d，缺失 %d" % (done, total, failed)
                         if failed else "正在准备语音 %d/%d…" % (done, total)),
                        0.5 + 0.45 * ((done + failed) / float(total)),
                    )
                if pending:
                    if now - s._load_phase_start < LOAD_VOICE_TIMEOUT:
                        return
                    if not getattr(s, "_load_voice_logged", False):
                        s._load_voice_logged = True
                        _debug("load voice timeout pending=%d" % pending)
            if not s._load_finish_at:
                s._load_finish_at = now
                _load_set("剧情已就绪，部分语音未就绪" if VOICE_ON and (failed or pending) else "准备完成", 1.0)
                return
            if now - s._load_finish_at < 0.8:
                return
            s._load_done = True
            s._load_rows = []
            return

        s._load_done = True

    def gal_clear_line_voice():
        store.gal_late_voice = None
        _voice.play = None
        _voice.tag = None
        _voice.sustain = False
        renpy.sound.stop(channel="voice")
        store._last_voice = None

    def gal_late_voice_tick():
        pending = getattr(store, "gal_late_voice", None)
        if pending is None:
            return
        st, route, run_id, turn, rec, filename, context = pending
        if (not VOICE_ON or config.skipping or renpy.context() is not context
                or getattr(context, "_menu", False) or router_blocked()
                or getattr(store, "st", None) is not st or st.get("run_id") != run_id
                or st.get("cursor") != turn or tuple(st.get("path") or ()) != route
                or rec.get("voice") != filename):
            store.gal_late_voice = None
            return
        if not _voice_file_ready(filename):
            if not _voice_pending_has(filename):
                store.gal_late_voice = None
            return
        store.gal_late_voice = None
        tag = str(rec.get("character") or "")
        volume = GetCharacterVolume(tag)
        if not volume or tag in persistent._voice_mute:
            return
        renpy.stop_tts()
        renpy.music.get_channel("voice").set_volume(volume)
        renpy.sound.play(filename, channel="voice", synchro_start=False)
        voice_duck_start()
        store._last_voice = {"voice": filename, "character": tag, "text": rec.get("text", "")}
        _debug("event=voice.play mode=late turn=%s mono_ms=%d" % (turn, time.monotonic() * 1000))

    config.periodic_callbacks.append(gal_late_voice_tick)

    def gal_mark_visible_dialogue(event, interact=True, **kwargs):
        if event == "show" and interact:
            row = getattr(store, "gal_visible_dialogue", None)
            if row is not None:
                _debug("event=dialogue.show turn=%s mono_ms=%d" %
                       (row[0].get("turn"), time.monotonic() * 1000))
        if event == "slow_done" and interact:
            pending = getattr(store, "gal_visible_dialogue", None)
            if pending is not None:
                line_mark_read(*pending)
                store.gal_visible_dialogue = None

    config.all_character_callbacks.append(gal_mark_visible_dialogue)

    def gal_say_record(who, rec, text, run_id, late_voice=None):
        # Keep the unread color until this interaction ends, while retaining
        # fully displayed lines when a load or menu jump interrupts the say.
        store.gal_visible_dialogue = (rec, text, run_id)
        if late_voice is not None:
            st = store.st
            store.gal_late_voice = (st, tuple(st.get("path") or ()), run_id,
                                    rec.get("turn"), rec, late_voice, renpy.context())
        try:
            renpy.say(who, gal_literal_text(text))
        finally:
            store.gal_late_voice = None
            store.gal_visible_dialogue = None

    def play_record(rec, st):
        _debug("event=beat.enter turn=%s mono_ms=%d" % (rec.get("turn"), time.monotonic() * 1000))
        proposals = rec.pop("new_characters", None)
        if proposals:
            apply_new_characters({"new_characters": proposals})
        source = rec.pop("gal_cast_source", None)
        if source is not None:
            gal_normalize_beat_cast(source)
            rec.update(source)
            rec["mood"] = rec.get("standing")
        _ch = rec.get("chapter")
        if _ch is not None:
            st["chapter"] = _ch
        show_beat(rec)
        st["scene"] = rec.get("scene", st.get("scene"))
        st["mood"] = rec.get("mood", st.get("mood"))
        if rec.get("bgm") not in (None, ""):
            st["bgm"] = rec["bgm"]
        play_bgm(st.get("bgm"))
        text = rec.get("text", "")
        if rec.get("is_speech"):
            t = text.strip()
            if t and not (t.startswith("「") and t.endswith("」")):
                text = "「" + t + "」"
        gal_clear_line_voice()
        late_voice = None
        if VOICE_ON:
            if rec.get("is_speech"):
                expected = gal_record_voice(rec, st)
                if expected and _voice_file_ready(expected):
                    play_voice(rec)
                    store._last_voice = {"voice": expected, "character": rec.get("character", ""),
                                         "text": rec.get("text", "")}
                    _debug("event=voice.play mode=queued turn=%s mono_ms=%d" %
                           (rec.get("turn"), time.monotonic() * 1000))
                elif expected:
                    late_voice = expected
            if not rec.get("choices") and not rec.get("ending"):
                ensure_voice(st, upcoming_records(st))
        # 关掉「未读文本快进」时，只允许跳过读过的台词；当前句没读过就停快进
        renpy.store._cur_line_seen = line_is_read(rec, text, st.get("run_id"))
        if (renpy.config.skipping and not renpy.game.preferences.skip_unseen
                and not renpy.store._cur_line_seen):
            renpy.config.skipping = None
        # 只有台词才显示名字；动作和旁白一律不显示名字框
        renpy.store.gal_viewpoint_changed = rec.get("viewpoint_changed") is True
        try:
            if rec.get("is_speech"):
                gal_say_record(_who(rec), rec, text, st.get("run_id"), late_voice)
            else:
                gal_say_record(_who({"character": NARRATOR}), rec, text, st.get("run_id"))
        finally:
            renpy.store._cur_line_seen = False
            renpy.store.gal_viewpoint_changed = False

    def next_record(st, path=None, after=None):
        path = list(path if path is not None else st.get("path", []))
        after = st.get("cursor", 0) if after is None else after
        best = None
        for r in st.get("history", []):
            if r.get("path", []) == path and r.get("turn", 0) > after:
                if best is None or r["turn"] < best["turn"]:
                    best = r
        return best

    def has_path(st, path):
        for r in st.get("history", []):
            if r.get("path", []) == list(path):
                return True
        return False

    def start_branch_prefetch(st, choices, base_path, count=6):
        boxes = []
        for i, c in enumerate(choices):
            if has_path(st, list(base_path) + [i]):
                continue
            if getattr(renpy.store, "gal_replay_cached_quick", False):
                continue
            st2 = json.loads(json.dumps(st))
            candidates = [rec for rec in st2.get("history", [])
                          if rec.get("choices") and list(rec.get("path") or []) == list(base_path)]
            if candidates:
                choice_rec = max(candidates, key=lambda rec: rec.get("turn", 0))
                st2["cursor"] = choice_rec["turn"]
                choice_rec["chosen"] = i
            apply_choice(st2, c)
            st2["path"] = list(base_path) + [i]
            boxes.append((i, start_prefetch(st2, count)))
        return boxes

    def drain_branches(st, boxes, base_path, wait=False, selected=None):
        if wait:
            for i, box in boxes:
                if selected is None or i == selected:
                    wait_prefetch(box, 90)
        for i, box in boxes:
            if (box.get("done") and box.get("result") and not box.get("consumed")
                    and box.get("epoch") == int(getattr(renpy.store, "_prefetch_epoch", 0))):
                pth = list(base_path) + [i]
                if not has_path(st, pth):
                    append_batch(st, box["result"], pth)

    def _history_records(st, limit=None):
        active = tuple(st.get("path") or [])
        try:
            cursor = int(st.get("cursor", 0) or 0)
        except (TypeError, ValueError):
            cursor = 0
        history = []
        cutoffs = {}
        for rec in st.get("history") or []:
            if not hasattr(rec, "get"):
                continue
            try:
                turn = int(rec.get("turn", 0) or 0)
            except (TypeError, ValueError):
                continue
            if turn <= 0 or turn > cursor:
                continue
            rp = tuple(rec.get("path") or [])
            depth = len(rp)
            if active[:depth] != rp:
                continue
            history.append((turn, rp, rec))
            # An ancestor route ends at the choice we took, despite cached parent suffixes.
            if depth < len(active) and rec.get("choices") and rec.get("chosen") == active[depth]:
                cutoffs[rp] = min(cutoffs.get(rp, cursor), turn)
        rows = [(turn, rec) for turn, rp, rec in history
                if turn <= cutoffs.get(rp, cursor)]
        rows.sort(key=lambda item: item[0])
        if limit is None:
            return [rec for _, rec in rows]
        limit = max(0, int(limit))
        return [rec for _, rec in rows[-limit:]] if limit else []

    def restore_playback_state(st):
        """Rebuild inherited music from visible ancestry, including legacy saves."""
        bgm = None
        for rec in _history_records(st):
            if rec.get("bgm") not in (None, ""):
                bgm = rec["bgm"]
        st["bgm"] = bgm
        play_bgm(bgm)

    def commit_choice(st, rec, index):
        """No interaction between option effects, route selection and resume marker."""
        choice = rec["choices"][index]
        # Branch results are already merged; parent-route jobs cannot cross this boundary.
        invalidate_prefetch()
        rec["_choice_state_before"] = snapshot_choice_state(st)
        rec["chosen"] = index
        apply_choice(st, choice)
        st["path"] = list(rec.get("path") or []) + [index]
        _debug("event=choice.commit turn=%s path=%s index=%s" % (rec["turn"], st["path"], index))
        if choice.get("react"):
            st["_choice_reaction"] = {"turn": rec["turn"], "path": list(rec.get("path") or []), "text": choice["react"]}
        else:
            st.pop("_choice_reaction", None)

    def play_choice_reaction(st):
        pending = st.get("_choice_reaction")
        if pending:
            for rec in st.get("history", []):
                if rec.get("turn") == pending.get("turn") and list(rec.get("path") or []) == list(pending.get("path") or []):
                    show_beat(rec)
                    break
            gal_clear_line_voice()
            reaction = {"turn": pending.get("turn"), "path": st.get("path"), "character": "choice_reaction"}
            text = pending["text"]
            renpy.store._cur_line_seen = line_is_read(reaction, text, st.get("run_id"))
            try:
                gal_say_record(None, reaction, text, st.get("run_id"))
            finally:
                renpy.store._cur_line_seen = False
            st.pop("_choice_reaction", None)

    def prepare_resume(st):
        """Old saves can have committed effects but still point at the parent route."""
        cursor = int(st.get("cursor", 0) or 0)
        for rec in st.get("history", []):
            if rec.get("choices") and (not _on_lineage(st, rec) or rec.get("turn", 0) > cursor):
                rec["chosen"] = None
        if st.get("_choice_reaction"):
            return
        for rec in st.get("history", []):
            if (rec.get("turn") == cursor and rec.get("choices") and rec.get("chosen") is not None
                    and list(rec.get("path") or []) == list(st.get("path") or [])):
                st["path"] = list(rec.get("path") or []) + [rec["chosen"]]
                return
        # An unanswered choice must re-enter the existing menu flow.
        if any(rec.get("turn") == cursor and rec.get("choices")
               and rec.get("chosen") is None and _on_lineage(st, rec)
               for rec in st.get("history", [])):
            st["cursor"] = max(0, cursor - 1)

    def restart_cached_quick():
        """Rewind a loaded copy of quick and keep the on-disk slot intact."""
        if not load_state("quick"):
            return
        state = renpy.store._loaded
        first = next_record(state, path=[], after=0)
        if first is not None:
            restore_record(state, first)
            state["ended"] = None
        renpy.store.gal_replay_cached_quick = first is not None
        renpy.hide_screen("start_choice")
        renpy.hide_screen("main_menu")
        renpy.jump_out_of_context("ai_resume")

    def restore_record(st, target):
        """Undo only the old active route; retain cached branch records for replay."""
        turn = target.get("turn", 1)
        path = list(target.get("path") or [])
        _debug("event=rewind from=%s to=%s path=%s" % (st.get("cursor"), turn, path))
        for rec in reversed(_history_records(st)):
            if rec.get("turn", 0) >= turn and rec.get("choices") and rec.get("chosen") is not None:
                snapshot = rec.get("_choice_state_before")
                if snapshot is not None:
                    restore_choice_state(st, snapshot)
        for rec in st.get("history", []):
            rp = list(rec.get("path") or [])
            if rp[:len(path)] == path and rec.get("turn", 0) >= turn and rec.get("choices"):
                rec["chosen"] = None
        st.pop("_choice_reaction", None)
        st.pop("ended", None)
        st["path"] = path
        st["cursor"] = max(0, turn - 1)
        if st.get("summary_until", 0) > st["cursor"]:
            st["summary_until"] = st["cursor"]
        invalidate_background_boxes()

    def rewind(st):
        return rewind_many(st, 1)

    def rewind_many(st, count=5):
        rows = [r for r in _history_records(st) if r.get("turn", 0) < st.get("cursor", 0)]
        target = None
        if not rows:
            rows = _history_records(st)[-1:]
        for rec in reversed(rows[-max(1, int(count)):]):
            target = rec
            if rec.get("choices"):
                break
        if target is not None:
            restore_record(st, target)
            return True
        return False

    def jump_last_choice(st):
        rows = [r for r in _history_records(st) if r.get("choices") and r.get("turn", 0) < st.get("cursor", 0)]
        if not rows:
            return False
        restore_record(st, rows[-1])
        return True

    def drain_prefetch(st):
        box = getattr(renpy.store, "_prefetch_box", None)
        if not box or not box.get("done"):
            return False
        res = take_prefetch(box, 0)
        if res and res.get("beats"):
            added = append_batch(st, res)
            if added:
                autosave()
                return True
            _debug("prefetch appended 0 beats")
        return False

    def ensure_prefetch(st, current_record=None):
        """Apply the same continuation rule during playback and resume."""
        if st.get("ended") or (current_record and
                (current_record.get("ending") or
                 (current_record.get("choices") and current_record.get("chosen") is None))):
            return None
        if getattr(store, "gal_replay_cached_quick", False):
            if next_record(st) is not None:
                return None
            store.gal_replay_cached_quick = False
        cached = upcoming_records(st, PLAN_AHEAD + 1)
        if any(rec.get("choices") or rec.get("ending") for rec in cached):
            return None
        existing = getattr(store, "_prefetch_box", None) or getattr(store, "_prefetch_busy_box", None)
        if existing is not None:
            return existing
        if len(cached) <= max(2, PLAN_AHEAD // 2):
            return start_prefetch(continuation_snapshot(st, cached), PLAN_AHEAD, current=True)
        return None

    def continuation_snapshot(st, cached):
        snapshot = dict(st)
        for record in cached:
            snapshot["cursor"] = int(record["turn"])
            for field in ("scene", "mood"):
                if field in record:
                    snapshot[field] = record[field]
            if record.get("bgm") not in (None, ""):
                snapshot["bgm"] = record["bgm"]
        return snapshot

    def prefetch_input_key(state):
        import hashlib
        data = {field: state.get(field) for field in (
            "run_id", "cursor", "path", "affection", "affections", "flags",
            "last", "last_choice_turn", "_choice_reaction", "ended",
        )}
        data["history"] = [continuation_record(row) for row in state.get("history", [])]
        encoded = json.dumps([data, PLAN_AHEAD, active_model(), active_endpoint(),
                              SUBAGENTS, harness_available()], ensure_ascii=False,
                             sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def continuation_record(row):
        if not isinstance(row, Mapping):
            return row
        return {key: value for key, value in row.items() if key != "voice"}

    # ---------- 存档 ----------

    _PROGRESS_SEED_MARKER = ".progress-seed-v1.json"
    _PROGRESS_SEEDED = set()
    _PROGRESS_SEED_LOCK = threading.RLock()

    def _progress_seed_legacy(base):
        """Copy only known valid JSON once; never overwrite canonical progress."""
        legacy = os.path.join(config.basedir, "savedata")
        canonical = os.path.realpath(base)
        if canonical == os.path.realpath(legacy):
            return
        marker = os.path.join(base, _PROGRESS_SEED_MARKER)
        with _PROGRESS_SEED_LOCK:
            if canonical in _PROGRESS_SEEDED or os.path.exists(marker):
                _PROGRESS_SEEDED.add(canonical)
                return
            candidates = [("history.json", "object"), ("chapters.json", "object"), ("voice_fav.json", "array")]
            diary = os.path.join(legacy, "diary")
            try:
                if os.path.isdir(diary) and not os.path.islink(diary):
                    candidates.extend((os.path.join("diary", name), "object")
                                      for name in os.listdir(diary)
                                      if name.lower().endswith(".json"))
                for relative, expected in candidates:
                    source = os.path.join(legacy, relative)
                    target = os.path.join(base, relative)
                    if os.path.lexists(target) or os.path.islink(source):
                        continue
                    try:
                        os.stat(source)
                    except FileNotFoundError:
                        continue
                    if not os.path.isfile(source):
                        continue
                    try:
                        with open(source, "r", encoding="utf-8") as stream:
                            data = json.load(stream)
                    except (ValueError, UnicodeError):
                        # Invalid legacy JSON is deliberately skipped, not retried forever.
                        continue
                    if ((expected == "object" and not isinstance(data, Mapping))
                            or (expected == "array" and type(data).__name__ != "list")):
                        continue
                    parent = os.path.dirname(target)
                    if os.path.islink(parent):
                        raise OSError("progress seed target directory is a symlink")
                    os.makedirs(parent, exist_ok=True)
                    if not os.path.lexists(target):
                        _atomic_write_text(target, json.dumps(data, ensure_ascii=False))
                # Retained by wipe_progress so deleted progress cannot return from legacy.
                _atomic_write_text(marker, json.dumps({"version": 1}))
                _PROGRESS_SEEDED.add(canonical)
            except OSError as exc:
                # A valid file that could not be read/written is retried next startup.
                _debug("progress seed incomplete: %s" % exc)

    def slot_dir():
        base = os.environ.get("GALGAME_SAVEDIR") or os.path.join(config.basedir, "savedata")
        try:
            os.makedirs(base, exist_ok=True)
        except OSError:
            pass
        return base

    def _progress_startup():
        _progress_seed_legacy(slot_dir())

    GAL_SLOTS_PER_PAGE = 8
    GAL_SLOT_PAGES = 10
    GAL_MANUAL_SLOTS = tuple(str(n) for n in range(1, GAL_SLOTS_PER_PAGE * GAL_SLOT_PAGES + 1))
    SAVE_SLOTS = ("auto", "quick") + GAL_MANUAL_SLOTS

    def gal_slot_label(slot):
        if slot == "auto":
            return "自动存档"
        if slot == "quick":
            return "快速存档"
        page, index = divmod(int(_slot_name(slot)) - 1, GAL_SLOTS_PER_PAGE)
        return "%03d-%d" % (page + 1, index + 1)

    def gal_slot_dialogue(data):
        if not data:
            return ""
        reaction = data.get("_choice_reaction")
        if isinstance(reaction, Mapping) and reaction.get("text"):
            return str(reaction["text"])
        return next((str(row.get("text") or "") for row in reversed(_history_records(data))
                     if row.get("turn") == data.get("cursor")), "")

    def gal_copy_slot(source, target):
        if source == target or source not in GAL_MANUAL_SLOTS or target not in GAL_MANUAL_SLOTS:
            return
        data = stage_state(source)
        if not data:
            renpy.notify("来源存档已不可用")
            return
        destination = thumb_path(target)
        thumb = slot_thumb_data(source)
        try:
            try:
                with open(destination, "rb") as stream:
                    previous_thumb = stream.read()
            except FileNotFoundError:
                previous_thumb = None
            if thumb is not None:
                atomic_write_file(destination, thumb, binary=True)
            elif previous_thumb is not None:
                os.remove(destination)
            try:
                _atomic_write_text(slot_path(target), json.dumps(data, ensure_ascii=False))
            except OSError:
                if previous_thumb is not None:
                    atomic_write_file(destination, previous_thumb, binary=True)
                elif thumb is not None:
                    os.remove(destination)
                raise
        except OSError as exc:
            _debug("copy slot %s to %s failed: %s" % (source, target, exc))
            renpy.notify("复制失败，请检查存档目录")
            return
        finally:
            _clear_slot_thumb_cache(target)
        renpy.hide_screen("ai_confirm")
        renpy.notify("已复制到 " + gal_slot_label(target))

    def gal_write_manual_slot(slot):
        try:
            save_state(slot)
        except OSError as exc:
            _debug("save slot %s failed: %s" % (slot, exc))
            renpy.notify("保存失败，请检查存档目录")
            return
        renpy.hide_screen("ai_confirm")
        renpy.hide_screen("ai_slots")


    def _slot_name(slot):
        s = str(slot or "").strip()
        if s not in SAVE_SLOTS:
            raise ValueError("无效的存档槽位：%s" % s)
        return s

    def slot_path(slot):
        return os.path.join(slot_dir(), "slot_%s.json" % _slot_name(slot))

    def thumb_path(slot):
        return os.path.join(slot_dir(), "slot_%s.png" % _slot_name(slot))

    _THUMB_CACHE = {}

    def slot_thumb_data(slot):
        """读存档截图给界面用；Ren'Py 的图片加载器够不到 savedata，所以走字节。"""
        path = thumb_path(slot)
        try:
            key = (path, os.path.getmtime(path))
            if key not in _THUMB_CACHE:
                with open(path, "rb") as f:
                    data = f.read()
                # 按 (路径, mtime) 缓存，不清空；只做容量上限，避免长局无限增长
                if len(_THUMB_CACHE) >= 32:
                    try:
                        _THUMB_CACHE.pop(next(iter(_THUMB_CACHE)))
                    except (StopIteration, KeyError):
                        pass
                _THUMB_CACHE[key] = data
            return _THUMB_CACHE[key]
        except Exception:
            return None

    def _clean_slot_name(value):
        # Names are plain text, not Ren'Py text markup.
        return " ".join(str(value or "").replace("\x00", "").split())[:64]

    def slot_has_files(slot):
        return os.path.isfile(slot_path(slot)) or os.path.isfile(thumb_path(slot))

    def _clear_slot_thumb_cache(slot):
        path = thumb_path(slot)
        for key in list(_THUMB_CACHE):
            if key[0] == path:
                _THUMB_CACHE.pop(key, None)

    def delete_slot(slot):
        try:
            slot = _slot_name(slot)
        except ValueError:
            renpy.notify("无效的存档槽位")
            return False
        if slot == "auto":
            renpy.notify("自动存档只读，不能删除")
            return False
        failed = []
        for path in (slot_path(slot), thumb_path(slot)):
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
            except OSError as exc:
                failed.append(str(exc))
        _clear_slot_thumb_cache(slot)
        if failed:
            _debug("delete slot=%s failed: %s" % (slot, "; ".join(failed)))
            renpy.notify("部分文件未能删除，请检查文件权限后重试")
            renpy.restart_interaction()
            return False
        renpy.hide_screen("ai_confirm")
        renpy.notify("已删除存档和缩略图")
        renpy.restart_interaction()
        return True

    def request_slot_delete(slot):
        try:
            slot = _slot_name(slot)
        except ValueError:
            return False
        if slot == "auto":
            renpy.notify("自动存档只读，不能删除")
            return False
        label = "快速存档" if slot == "quick" else "槽位 " + gal_slot_label(slot)
        message = "将删除%s的存档和缩略图，不可恢复。" % label
        if slot == "quick":
            message += "删除后标题页的继续游戏将不可用。"
        renpy.show_screen("ai_confirm", text=message, act=Function(gal_slot_ui_action, delete_slot, slot))
        return True

    def rename_slot(slot, name):
        try:
            slot = _slot_name(slot)
        except ValueError:
            return False
        if slot == "auto":
            renpy.notify("自动存档只读，不能命名")
            return False
        data = read_state(slot)
        if not isinstance(data, Mapping) or not data:
            renpy.notify("空槽位或损坏的存档不能命名")
            return False
        data["name"] = _clean_slot_name(name)
        path = slot_path(slot)
        try:
            _atomic_write_text(path, json.dumps(data, ensure_ascii=False))
        except OSError as exc:
            _debug("rename slot=%s failed: %s" % (slot, exc))
            renpy.notify("存档命名未能保存，请检查文件权限")
            return False
        renpy.restart_interaction()
        return True

    def open_slot_name(slot):
        if str(slot) == "auto":
            return False
        data = stage_state(slot)
        if not data:
            return False
        renpy.store.slot_name_target = _slot_name(slot)
        renpy.store.slot_name_value = _clean_slot_name(data.get("name", ""))
        renpy.show_screen("slot_name_edit")
        return True

    def commit_slot_name():
        if rename_slot(renpy.store.slot_name_target, renpy.store.slot_name_value):
            renpy.hide_screen("slot_name_edit")

    def slot_time_label(slot, data=None):
        if data is None:
            data = stage_state(slot)
        if not data:
            return ""
        try:
            return time.strftime("%Y-%m-%d %H:%M", time.localtime(float(data.get("_time", 0))))
        except Exception:
            return ""

    def pending_thumb_path():
        return os.path.join(slot_dir(), "_pending_thumb.png")

    def capture_pending_thumb():
        """在存档界面弹出前抓一张干净的游戏画面，避免缩略图拍到存档面板。"""
        try:
            renpy.screenshot(pending_thumb_path())
        except Exception:
            pass

    def save_state(slot, quiet=False, use_pending=True, thumb=True):
        st = renpy.store.st
        data = json.loads(json.dumps(st))
        previous = read_state(slot)
        data["name"] = _clean_slot_name(previous.get("name", "")) if isinstance(previous, Mapping) else ""
        data["_time"] = time.time()
        data["_affection"] = st["affection"]
        data["_chapter"] = st.get("chapter", "")
        path = slot_path(slot)
        _atomic_write_text(path, json.dumps(data, ensure_ascii=False))
        _debug("save slot=%s cursor=%s records=%d time=%.1f" % (
            slot, data.get("cursor"), len(data.get("history") or []),
            data.get("_time", 0),
        ))
        try:
            if thumb:
                pend = pending_thumb_path()
                if use_pending and os.path.exists(pend):
                    with open(pend, "rb") as stream:
                        atomic_write_file(thumb_path(slot), stream.read(), binary=True)
                    os.remove(pend)
                elif not use_pending:
                    pass
                else:
                    renpy.screenshot(thumb_path(slot))
        except Exception:
            pass
        _clear_slot_thumb_cache(slot)
        if not quiet:
            renpy.notify("已快速存档" if _slot_name(slot) == "quick" else "已保存到 " + gal_slot_label(str(slot)))

    def autosave(thumb=False):
        try:
            save_state("auto", quiet=True, use_pending=True, thumb=thumb)
        except Exception:
            pass

    def wipe_progress():
        """重新生成：清掉剧情历史、章节、日记和全部存档（含快速存档）。"""
        base = slot_dir()
        real = os.path.realpath(base)
        allowed = {os.path.realpath(os.path.join(config.basedir, "savedata"))}
        env = os.environ.get("GALGAME_SAVEDIR")
        if env:
            allowed.add(os.path.realpath(env))
        if real not in allowed:
            _debug("wipe skip: savedata 指向外部目录 %s" % real)
            return
        try:
            if real != os.path.realpath(os.path.join(config.basedir, "savedata")):
                _atomic_write_text(os.path.join(base, _PROGRESS_SEED_MARKER), json.dumps({"version": 1}))
                _PROGRESS_SEEDED.add(real)
            for name in os.listdir(base):
                if (name.startswith("slot_") or name in ("history.json", "chapters.json", "_pending_thumb.png")
                        or ".tmp-" in name or name.endswith(".tmp")):
                    try:
                        os.remove(os.path.join(base, name))
                    except OSError:
                        pass
            diary = os.path.join(base, "diary")
            if os.path.isdir(diary) and not os.path.islink(diary):
                for name in os.listdir(diary):
                    try:
                        os.remove(os.path.join(diary, name))
                    except OSError:
                        pass
            harness = os.path.join(config.basedir, "savedata", "harness")
            if os.path.isdir(harness) and not os.path.islink(harness):
                for name in os.listdir(harness):
                    if name.startswith("request-") or name.startswith("response-"):
                        try:
                            os.remove(os.path.join(harness, name))
                        except OSError:
                            pass
        except OSError:
            pass
        _THUMB_CACHE.clear()
        renpy.store._loaded = None
        invalidate_background_boxes()

    def cleanup_tmp_leftovers():
        """清理原子写在崩溃/强杀后留下的 *.tmp / *.tmp-<pid>-<ms> 文件。"""
        game = os.path.join(config.basedir, "game")
        removed = 0
        bases = [slot_dir(), os.path.join(slot_dir(), "diary"), os.path.join(game, "persona")]
        for base in bases:
            try:
                names = os.listdir(base)
            except OSError:
                continue
            for name in names:
                if ".tmp-" in name or name.endswith(".tmp"):
                    try:
                        os.remove(os.path.join(base, name))
                        removed += 1
                    except OSError:
                        pass
        # 语音按角色分目录，必须递归
        for root, _dirs, files in os.walk(VOICE_DIR):
            for name in files:
                if ".tmp-" in name or name.endswith(".tmp"):
                    try:
                        os.remove(os.path.join(root, name))
                        removed += 1
                    except OSError:
                        pass
        if removed:
            _debug("cleanup tmp leftovers %d" % removed)

    def read_state(slot):
        path = slot_path(slot)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def gal_valid_slot(data):
        import builtins
        if not isinstance(data, Mapping) or not data:
            return False
        cursor = data.get("cursor", 0)
        route = data.get("path", [])
        history = data.get("history")
        if (type(cursor) is not int or cursor < 0 or not isinstance(route, builtins.list)
                or any(type(i) is not int or i < 0 for i in route)
                or not isinstance(history, builtins.list) or not history):
            return False
        for row in history:
            if not isinstance(row, Mapping) or type(row.get("turn")) is not int:
                return False
            path = row.get("path", [])
            choices = row.get("choices")
            chosen = row.get("chosen")
            if (not isinstance(path, builtins.list) or any(type(i) is not int or i < 0 for i in path)
                    or not isinstance(row.get("text", ""), str)
                    or (choices is not None and (not isinstance(choices, builtins.list)
                        or any(not isinstance(choice, Mapping) for choice in choices)))
                    or (chosen is not None and (type(chosen) is not int
                        or not choices or not 0 <= chosen < len(choices)))):
                return False
        if cursor and not any(row["turn"] == cursor and _on_lineage(data, row) for row in history):
            return False
        reaction = data.get("_choice_reaction")
        return reaction is None or (isinstance(reaction, Mapping) and isinstance(reaction.get("text"), str))

    def stage_state(slot):
        data = read_state(slot)
        return data if gal_valid_slot(data) else None

    gal_slot_preview_cache = {}

    def gal_slot_preview(slot):
        path = slot_path(slot)
        try:
            stat = os.stat(path)
        except OSError:
            gal_slot_preview_cache.pop(path, None)
            return None
        stamp = (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, stat.st_ino)
        cached = gal_slot_preview_cache.get(path)
        if cached is not None and cached[0] == stamp:
            return cached[1]
        data = stage_state(slot)
        summary = None if data is None else {
            "name": data.get("name"), "_chapter": data.get("_chapter"),
            "_time": data.get("_time"), "dialogue": gal_slot_dialogue(data),
        }
        if len(gal_slot_preview_cache) >= 32:
            gal_slot_preview_cache.pop(next(iter(gal_slot_preview_cache)))
        gal_slot_preview_cache[path] = (stamp, summary)
        return summary

    def merge_quick_continuation(state, auto):
        """Reuse a verified auto suffix while retaining the quick playback state."""
        import builtins
        if (not isinstance(auto, Mapping) or state.get("ended")
                or state.get("_choice_reaction")
                or state.get("path", []) != auto.get("path", [])
                or state.get("run_id") != auto.get("run_id")):
            return 0
        rows = state.get("history")
        newer = auto.get("history")
        if (not isinstance(rows, builtins.list) or not rows or not isinstance(newer, builtins.list)
                or len(newer) <= len(rows)
                or not isinstance(rows[-1], Mapping)):
            return 0
        tail = rows[-1].get("turn")
        cursor = state.get("cursor")
        if type(tail) is not int or type(cursor) is not int or cursor > tail:
            return 0
        if any(continuation_record(old) != continuation_record(new)
               for old, new in zip(rows, newer)):
            return 0
        # Legacy slots have no run identity. Require the complete stored prefix
        # and matching route effects before borrowing their straight-line suffix.
        if not state.get("run_id"):
            for key in ("affection", "affections", "flags", "last", "last_choice_turn"):
                if state.get(key) != auto.get(key):
                    return 0
        route = state.get("path", [])
        for row in rows:
            if not isinstance(row, Mapping) or type(row.get("turn")) is not int:
                return 0
            if row["turn"] >= cursor and row.get("path", []) == route and row.get("choices"):
                return 0
        suffix = newer[len(rows):]
        for offset, row in enumerate(suffix, 1):
            if (not isinstance(row, Mapping) or row.get("turn") != tail + offset
                    or row.get("path", []) != route or row.get("chosen") is not None
                    or (row.get("choices") and offset != len(suffix))):
                return 0
        rows.extend(suffix)
        return len(suffix)

    def load_state(slot, reuse_prefetch=False):
        try:
            data = read_state(slot)
        except ValueError:
            renpy.notify("无效的存档槽位")
            return False
        if not gal_valid_slot(data):
            renpy.notify("这个槽位是空的或已损坏")
            return False
        data.setdefault("cursor", 0)
        data.setdefault("path", [])
        data.pop("name", None)
        data.pop("_time", None)
        data.pop("_affection", None)
        data.pop("_chapter", None)
        if reuse_prefetch and slot != "auto":
            reused = merge_quick_continuation(data, getattr(renpy.store, "st", None))
            if not reused:
                reused = merge_quick_continuation(data, read_state("auto"))
            if reused:
                renpy.store.gal_replay_cached_quick = True
                _debug("resume cache reused slot=%s cursor=%s records=%d" % (slot, data.get("cursor"), reused))
        renpy.store._loaded = data
        keep = None
        if reuse_prefetch:
            candidate = getattr(renpy.store, "_prefetch_box", None)
            cached = upcoming_records(data, PLAN_AHEAD + 1)
            snapshot = continuation_snapshot(data, cached)
            if (candidate and not candidate.get("consumed") and not data.get("ended")
                    and not any(rec.get("choices") or rec.get("ending") for rec in cached)
                    and candidate.get("input") == prefetch_input_key(snapshot)):
                keep = candidate
                _debug("prefetch reused on load slot=%s cursor=%s id=%s" %
                       (slot, data.get("cursor"), candidate["input"][:12]))
        invalidate_background_boxes(keep)
        _debug("load slot=%s cursor=%s records=%d" % (
            slot, data.get("cursor"), len(data.get("history") or []),
        ))
        return True

    def load_and_jump(slot):
        renpy.store.gal_replay_cached_quick = False
        if load_state(slot, reuse_prefetch=True):
            renpy.hide_screen("ai_slots")
            # 主菜单是独立 context，直接 jump 会留在菜单里，功能栏不会显示
            if getattr(renpy.store, "main_menu", False) or getattr(renpy.context(), "_menu", False):
                renpy.hide_screen("main_menu")
                renpy.jump_out_of_context("ai_resume")
            else:
                renpy.jump("ai_resume")

    # ---------- 离线 mock ----------
    # 没有 GALGAME_KEY 时走这里，只为把引擎跑通（选项、分支预取、存档、章节、场景切换）。
    # 优先读 game/mock.json，方便你自己写一份离线样例；没有就用下面的通用占位节点。

    _PLACEHOLDER_NODES = {
        "p01": {
            "beats": [
                {"character": NARRATOR, "is_speech": False, "text": "这是离线占位剧情。在 options.txt 填好 GALGAME_KEY 后，这里换成模型实时生成的开场。", "scene": DEFAULT_SCENE},
                {"character": HEROINE_NAME, "standing": standing_value(default_standing(HEROINE)), "is_speech": True, "text": "人物卡在 game/persona/ 里，world 设定在 game/seikai.md。", "scene": DEFAULT_SCENE},
            ],
            "choices": [
                {"label": "继续", "hint": "走到第二个占位节点", "add": 1, "react": "占位剧情继续。真实剧情由模型按 10 拍以上的节奏预生成。", "next": "p02"},
                {"label": "看分支", "hint": "每个选项都会预生成一段反应", "add": 0, "flag": "mock_branch", "react": "选项的反应文本同样来自预生成，未选中的分支也会存进剧情树。", "next": "p02"},
                {"label": "回头", "hint": "演示 BACK：回到上一次选择", "add": -1, "react": "占位剧情结束这一段，可以用右下角 BACK 返回上一个选项。", "next": "p02"},
            ],
        },
        "p02": {
            "beats": [
                {"character": NARRATOR, "is_speech": False, "text": "第二个占位节点。背景、立绘差分、镜头都在 batch 的 JSON 里决定，Ren'Py 只负责显示。", "scene": SCENES[len(SCENES) // 2]},
                {"character": NARRATOR, "is_speech": False, "text": "接上 API 之后，这一段会一直往下写，不会在这里结束。", "scene": SCENES[len(SCENES) // 2]},
            ],
            "choices": [
                {"label": "回到开头", "hint": "占位剧情循环，方便验证存档", "add": 0, "react": "循环回第一个占位节点。", "next": "p01"},
                {"label": "再走一段", "hint": "继续循环", "add": 1, "react": "继续循环，存档和读档按拍生效。", "next": "p01"},
            ],
        },
    }

    def mock_nodes():
        path = os.path.join(config.basedir, "game", "mock.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return _PLACEHOLDER_NODES
        if hasattr(data, "get") and data.get("nodes"):
            return data["nodes"]
        if hasattr(data, "get") and data:
            return data
        return _PLACEHOLDER_NODES

    def mock_batch(st):
        nodes = mock_nodes()
        node = st.get("last") or "p01"
        data = nodes.get(node) or nodes.get("p01") or {}
        batch = json.loads(json.dumps(data))
        for b in batch.get("beats", []):
            if not hasattr(b, "get"):
                continue
            b.setdefault("scene", DEFAULT_SCENE)
            ch = b.get("character") or b.get("speaker")
            if is_narrator(ch):
                ch = NARRATOR
            else:
                ch = str(ch).strip()
            b["character"] = ch
            b["speaker"] = "" if ch == NARRATOR else ch
            b["portrait"] = ch
            raw = b.get("standing")
            if raw is None:
                raw = b.get("mood")
            sid = "" if raw is None else str(raw).strip()
            if ch == NARRATOR:
                b["standing"] = None
                b["mood"] = None
            else:
                p = resolve_persona(ch)
                if sid not in standing_ids(p):
                    sid = default_standing(p)
                b["standing"] = standing_value(sid)
                b["mood"] = b["standing"]
            if "is_speech" not in b:
                b["is_speech"] = ch != NARRATOR
        return batch

    if USING_HARNESS and not harness_available():
        _debug("GALGAME_USING_HARNESS=1 但没有 harness（GALGAME_HOST=%s），回退到对话模型" % (HOST or "空"))

    ai_cfg_endpoint = AI_ENDPOINT
    ai_cfg_model = AI_MODEL
    ai_cfg_key = AI_KEY

    _debug(
        "init basedir=%s mock=%s keylen=%d model=%s image=%s voice=%s heroine=%s ill=%s personas=%d scenes=%d moods=%s"
        % (
            config.basedir, AI_MOCK, len(AI_KEY), AI_MODEL,
            _cfg("GALGAME_IMAGE_MODEL"), VOICE_MODEL,
            HEROINE_NAME, HEROINE_ILL, len(_persona_entries()), len(SCENES), ",".join(MOODS),
        )
    )

    # Startup callbacks run even when splashscreen is skipped; screen reads stay read-only.
    config.start_callbacks.append(_progress_startup)

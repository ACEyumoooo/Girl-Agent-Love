#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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

"""按 references/art.md 的规范，给 galgame 框架批量生成背景图和角色立绘。

配置全部读游戏目录的 options.txt（和环境变量），和引擎本身的优先级一致：
    GALGAME_IMAGE_ENDPOINT / GALGAME_IMAGE_KEY / GALGAME_IMAGE_MODEL
    GALGAME_IMAGE_SIZE / GALGAME_IMAGE_SIZE_PORTRAIT / GALGAME_IMAGE_TIMEOUT
生图密钥留空时复用对话模型的 GALGAME_KEY。

两种接口都支持：
  * 阿里云万相原生异步接口（地址含 image-synthesis / image-generation）
        POST 提交任务 -> GET /api/v1/tasks/<id> 轮询 -> 拿 results[].url
  * OpenAI 兼容的 /images/generations（地址含 compatible-mode 或 images/generations）
        一次 POST，拿 data[0].url 或 data[0].b64_json

产物：
  game/picture/scene/<time>_<place>.jpg            1280x720 JPG q85
  game/picture/standing/<角色名字>/<id>.webp       920x1380 透明 WebP q88
  game/art_manifest.json                           每张图的提示词、模型、尺寸，方便复现

立绘差分的 id 来自人物卡「## 立绘」表格，表里有几行就出几张。

用法：
  python gen_art.py --game-dir /path/to/game-parent            # 全量
  python gen_art.py --game-dir . --only scenes                  # 只补背景
  python gen_art.py --game-dir . --only 绫/guarded          # 只补一张立绘
  python gen_art.py --game-dir . --only aya/calm --force --seed 7   # 换种子重抽
  python gen_art.py --game-dir . --dry-run                      # 只打印提示词，不调接口

生成后必须肉眼过一遍：背景角落有没有乱码文字、立绘抠图边缘有没有留白底，
有问题就 --force --seed 换个数字重抽。
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import ipaddress
import json
import os
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_SCENES = (
    "day_classroom", "dusk_classroom", "night_classroom",
    "day_rooftop", "dusk_rooftop", "night_rooftop",
    "day_gate", "dusk_gate", "night_gate",
    "dusk_street", "night_street",
)
DEFAULT_TIME_WORDS = {
    "day": "白天，自然光，光线均匀",
    "dusk": "黄昏，橙红斜光，影子拉长",
    "night": "夜里，冷色灯光加少量暖色点光",
}
DEFAULT_PLACE_WORDS = {
    "classroom": "空掉大半的教室，课桌歪着，窗外有树影",
    "rooftop": "教学楼天台，铁网围栏和远处屋顶",
    "gate": "校门口，斑马线与公交站",
    "street": "放学的街道，店铺招牌半亮",
    "corridor": "学校走廊，储物柜排成一列",
    "library": "图书馆内部，高书架与长桌，空气里有纸的味道",
    "cafeteria": "午餐时间的食堂，长桌与餐盘",
    "gym": "体育馆，木地板与篮球架",
    "infirmary": "医务室，白床帘和药柜",
    "station": "傍晚的车站，月台与自动贩卖机",
    "office": "教师办公室，堆满文件的桌子",
    "park": "街心公园，长椅与路灯",
    "alley": "小巷，晾衣杆和湿掉的地面",
    "shop": "小店内部，货架与柜台",
}
BG_TARGET = (1280, 720)
SPRITE_TARGET = (920, 1380)
BG_NEGATIVE = (
    "文字, 汉字, 字母, 数字, 标点, 招牌文字, 书脊文字, 字幕, 标题, logo, 水印, 印章, 二维码, "
    "人物, 角色, 人影, 动漫人物, 手, 脸, 畸变, 低分辨率, 模糊"
)
SPRITE_NEGATIVE = (
    "背景, 场景, 家具, 其他人物, 多人, 文字, 汉字, 字母, 数字, 水印, logo, 边框, 描边框, 阴影, "
    "裁切, 半身, 多视角, 拼图, Q版, 3D渲染"
)
UA = "galgame-gen-art/1.0"


# ---------------------------------------------------------------- 配置读取

def read_kv(path):
    data = {}
    if not os.path.exists(path):
        return data
    with open(path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip()
            data[k.strip()] = v
    return data


STAND_KEYS = {
    "id": "id", "编号": "id",
    "角色": "character", "character": "character",
    "衣服": "clothes", "clothing": "clothes", "clothes": "clothes",
    "动作": "action", "action": "action",
    "表情": "expression", "expression": "expression",
    "什么时候用": "when", "when": "when", "场合": "when", "使用场合": "when",
}


def parse_standings(body):
    """读人物卡「## 立绘」。主格式是键值块，也兼容表格和 `- guarded：冷淡` 列表。"""
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
            if first.lower() in ("id", "") or set(first) <= set("-: "):
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
        mapped = STAND_KEYS.get(key)
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


class Config(object):
    def __init__(self, game_dir):
        self.dir = os.path.abspath(game_dir)
        self.game = os.path.join(self.dir, "game")
        self.files = read_kv(os.path.join(self.dir, "options.txt"))
        key_txt = read_kv(os.path.join(self.dir, "key.txt"))
        for k, v in key_txt.items():
            if v:
                self.files[k] = v
        self.prompts = self._load_prompts()

    def get(self, name, default=""):
        return (os.environ.get(name, "").strip() or self.files.get(name, "").strip() or default)

    def csv(self, name, default):
        raw = self.get(name)
        if not raw:
            return list(default)
        parts = [p.strip() for p in raw.replace(";", ",").replace(" ", ",").split(",")]
        return [p for p in parts if p] or list(default)

    def _load_prompts(self):
        path = os.path.join(self.game, "art_prompts.json")
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as exc:
            print("! art_prompts.json 读不了：%s" % exc, file=sys.stderr)
            return {}
        return data if hasattr(data, "get") else {}

    def scenes(self):
        """场景从 picture/scene 的文件名读，不再看 options。"""
        found = []
        for base in (os.path.join(self.game, "picture", "scene"), os.path.join(self.game, "scene")):
            if not os.path.isdir(base):
                continue
            for fn in sorted(os.listdir(base)):
                stem, ext = os.path.splitext(fn)
                if ext.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
                    continue
                if "_" not in stem or stem.split("_", 1)[0] not in ("day", "dusk", "night"):
                    continue
                if stem not in found:
                    found.append(stem)
        return found or list(DEFAULT_SCENES)

    def moods(self):
        """立绘 id 以人物卡「## 立绘」为准，没有卡时用默认三档。"""
        ids = []
        for p in self.heroines():
            for sid in (p.get("standings") or {}):
                if sid not in ids:
                    ids.append(sid)
        return ids or ["1", "2", "3"]

    def heroines(self):
        base = os.path.join(self.game, "persona")
        out = []
        if not os.path.isdir(base):
            return out
        for fn in sorted(os.listdir(base)):
            if not fn.endswith(".md") or fn.startswith("_") or fn.lower().startswith("readme"):
                continue
            with open(os.path.join(base, fn), "r", encoding="utf-8") as f:
                text = f.read()
            meta, body = {}, text
            if text.startswith("---"):
                end = text.find("---", 3)
                if end > 0:
                    for line in text[3:end].splitlines():
                        if ":" in line:
                            k, v = line.split(":", 1)
                            meta[k.strip()] = v.strip()
                    body = text[end + 3:].strip()
            out.append({
                "file": fn,
                "id": meta.get("id") or fn[:-3],
                "name": meta.get("name") or fn[:-3],
                "gender": (meta.get("gender") or "").strip(),
                "illustration": meta.get("illustration") or fn[:-3],
                "lead": str(meta.get("lead", "")).lower() in ("1", "true", "yes"),
                "standings": parse_standings(body),
                "body": body,
            })
        return out


# ---------------------------------------------------------------- 提示词拼装

def split_scene(scene):
    if "_" in scene:
        t, p = scene.split("_", 1)
        return t, p
    return "day", scene


def _pretty(place):
    return place.replace("_", " ")


def bg_prompt(cfg, scene):
    override = (cfg.prompts.get("scenes") or {}).get(scene)
    time_key, place = split_scene(scene)
    light = DEFAULT_TIME_WORDS.get(time_key, "%s 时段的光线" % time_key)
    if override:
        subject = override
    else:
        subject = "%s，空镜头，画面里没有任何人" % (DEFAULT_PLACE_WORDS.get(place) or ("一处" + _pretty(place)))
    genre = cfg.get("GALGAME_GENRE", "校园恋爱")
    return (
        "日系恋爱视觉小说（%s题材）的游戏背景插画。%s。时段：%s，%s。"
        "手绘赛璐璐上色，柔和景深，构图留出角色站位和文字框区域，"
        "细节丰富但不抢视线，色彩统一。"
        "画面里不得出现任何可辨认的文字、字母、数字或标志，书脊和招牌一律做成模糊色块，不要人物不要水印。"
        % (genre, subject, time_key, light)
    )


def _appearance(cfg, persona):
    override = (cfg.prompts.get("characters") or {}).get(persona["id"], {})
    if override.get("look"):
        return override["look"].rstrip("。")
    body = persona["body"]
    marker = "## 外貌与身体语言"
    if marker in body:
        part = body.split(marker, 1)[1]
        if "\n## " in part:
            part = part.split("\n## ", 1)[0]
        lines = []
        for raw in part.splitlines():
            line = raw.strip().lstrip("-").strip()
            if line:
                lines.append(line)
        if lines:
            return "；".join(lines)[:240].rstrip("。")
    for block in body.split("\n\n"):
        line = " ".join(block.strip().splitlines())
        if line and not line.startswith("#") and not line.startswith("-"):
            return line[:120].rstrip("。")
    return persona["name"]


def _mood_notes(persona):
    """把立绘表的表达式、动作、使用场合拼成一句，给提示词当表情说明。"""
    out = {}
    for sid, row in (persona.get("standings") or {}).items():
        parts = [row.get("clothes"), row.get("expression"), row.get("action"), row.get("when")]
        out[sid] = "；".join(p for p in parts if p) or sid
    return out


def sprite_prompt(cfg, persona, mood, anchor=None):
    override = (cfg.prompts.get("characters") or {}).get(persona["id"], {})
    mood_desc = (override.get("moods") or {}).get(mood) or _mood_notes(persona).get(mood) or (mood + " 那种情绪")
    style = override.get("style") or "日系恋爱视觉小说角色立绘，全身，站姿，正面微侧，脚尖朝前"
    gender = (persona.get("gender") or "").strip()
    base = (
        "%s。%s固定设定：%s。服装、发型、体型、配色必须和其它表情的立绘完全一致。"
        % (style, ("性别：" + gender + "。") if gender else "", _appearance(cfg, persona))
    )
    if anchor:
        base += " 全作统一画风：%s。" % anchor
    return (
        "%s 这一张的表情与姿态：%s。"
        "背景是均匀的纯白，无渐变、无纹理、无投影、无地面、无道具，"
        "人物完整不裁切，居中竖构图，赛璐璐厚涂边缘干净，画面里不要任何文字。"
        % (base, mood_desc)
    )


# ---------------------------------------------------------------- HTTP

def ssl_context(cfg, insecure=False):
    """优先系统信任库，其次游戏目录自带的 cacert.pem，再次 certifi。
    都不行时报错，只有显式加 --insecure 才跳过证书校验（仅限本地试跑）。"""
    errors = []
    try:
        return ssl.create_default_context()
    except Exception as exc:  # pragma: no cover
        errors.append("系统信任库：%s" % exc)
    ca = os.path.join(cfg.game, "cacert.pem")
    if os.path.exists(ca):
        try:
            return ssl.create_default_context(cafile=ca)
        except Exception as exc:
            errors.append("cacert.pem：%s" % exc)
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception as exc:
        errors.append("certifi：%s" % exc)
    if insecure:
        print("! 证书校验已关闭（--insecure），仅用于本地试跑", file=sys.stderr)
        return ssl._create_unverified_context()
    raise RuntimeError("没有可用的根证书，HTTPS 无法验证：" + " / ".join(errors) + "。装一下 certifi 或保留 game/cacert.pem。")


def safe_component(value, prefix="role"):
    """目录名只允许单个路径段；异常 id 改成哈希，防止 ../ 越界。"""
    s = str(value or "").strip()
    bad = (
        not s or s in (".", "..") or "/" in s or "\\" in s or ":" in s
        or "\x00" in s or os.path.isabs(s) or s.endswith(".") or s.endswith(" ")
    )
    if bad:
        return prefix + "_" + hashlib.md5(s.encode("utf-8")).hexdigest()[:10]
    return s


def safe_under(base, rel):
    base_abs = os.path.abspath(base)
    full = os.path.abspath(os.path.join(base_abs, str(rel or "").replace("/", os.sep)))
    if full != base_abs and not full.startswith(base_abs + os.sep):
        return None
    return full


def url_parts(url):
    try:
        p = urllib.parse.urlsplit(str(url or "").strip())
    except Exception:
        return None
    if p.scheme.lower() not in ("http", "https") or not p.hostname:
        return None
    return p


def same_origin(a, b):
    pa, pb = url_parts(a), url_parts(b)
    if not pa or not pb:
        return False
    if pa.scheme.lower() != pb.scheme.lower() or (pa.hostname or "").lower() != (pb.hostname or "").lower():
        return False
    try:
        port_a = pa.port or (443 if pa.scheme.lower() == "https" else 80)
        port_b = pb.port or (443 if pb.scheme.lower() == "https" else 80)
    except Exception:
        return False
    return port_a == port_b


def host_is_private(host):
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return True
    if not infos:
        return True
    for info in infos:
        try:
            addr = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_multicast or addr.is_reserved or addr.is_unspecified):
            return True
    return False


def check_url(url, allow_private=False, trusted_origin=""):
    p = url_parts(url)
    if not p:
        raise RuntimeError("不安全的地址：只允许 http/https")
    if not allow_private and not (trusted_origin and same_origin(url, trusted_origin)):
        if host_is_private(p.hostname):
            raise RuntimeError("不安全的地址：不能访问本机或内网")
    return p


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """POST 不允许跨域重定向；GET 跨域时去掉 Authorization。"""

    def __init__(self, allow_private=False, trusted_origin=""):
        self.allow_private = allow_private
        self.trusted_origin = trusted_origin

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl, self.allow_private, self.trusted_origin)
        same = same_origin(newurl, req.full_url)
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


def open_url(req, timeout, ctx, allow_private=False, trusted_origin=""):
    check_url(req.full_url, allow_private, trusted_origin)
    handlers = [SafeRedirectHandler(allow_private, trusted_origin)]
    if ctx is not None:
        handlers.insert(0, urllib.request.HTTPSHandler(context=ctx))
    return urllib.request.build_opener(*handlers).open(req, timeout=timeout)


def request(url, data=None, headers=None, method="GET", ctx=None, timeout=60,
            allow_private=True, trusted_origin=""):
    check_url(url, allow_private=allow_private, trusted_origin=trusted_origin)
    body = None
    hdr = {"User-Agent": UA}
    hdr.update(headers or {})
    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        hdr["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=hdr, method=method)
    with open_url(req, timeout=timeout, ctx=ctx, allow_private=allow_private,
                  trusted_origin=trusted_origin) as resp:
        raw = resp.read()
    if raw[:1] == b"{":
        return json.loads(raw.decode("utf-8"))
    return raw


def get_json_bytes(url, ctx, timeout=120, trusted_origin=""):
    data = request(url, ctx=ctx, timeout=timeout, allow_private=False,
                   trusted_origin=trusted_origin)
    if isinstance(data, dict):
        raise RuntimeError("下载图片拿到的是 JSON：%s" % json.dumps(data, ensure_ascii=False)[:200])
    return data


def _seed(cfg):
    raw = cfg.get("GALGAME_IMAGE_SEED")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def compatible_generate(cfg, key, prompt, negative, size, ctx):
    endpoint = cfg.get("GALGAME_IMAGE_ENDPOINT").rstrip("/")
    if not endpoint.endswith("/images/generations"):
        endpoint += "/images/generations"
    payload = {
        "model": cfg.get("GALGAME_IMAGE_MODEL", "wanx2.1-t2i-turbo"),
        "prompt": prompt,
        "n": 1,
        "size": size.replace("*", "x"),
    }
    if negative:
        payload["negative_prompt"] = negative
    if _seed(cfg) is not None:
        payload["seed"] = _seed(cfg)
    resp = request(
        endpoint,
        data=payload,
        headers={"Authorization": "Bearer " + key},
        method="POST",
        ctx=ctx,
        timeout=180,
    )
    items = resp.get("data") or resp.get("output", {}).get("results") or []
    for item in items:
        if item.get("url"):
            return get_json_bytes(item["url"], ctx, trusted_origin=endpoint)
        if item.get("b64_json"):
            return base64.b64decode(item["b64_json"])
    raise RuntimeError("兼容接口没返回图片：%s" % json.dumps(resp, ensure_ascii=False)[:200])


def native_generate(cfg, key, prompt, negative, size, ctx):
    endpoint = cfg.get("GALGAME_IMAGE_ENDPOINT")
    parts = urllib.parse.urlsplit(endpoint)
    payload = {
        "model": cfg.get("GALGAME_IMAGE_MODEL", "wanx2.1-t2i-turbo"),
        "input": {"prompt": prompt},
        "parameters": {"size": size, "n": 1, "prompt_extend": False, "watermark": False},
    }
    if _seed(cfg) is not None:
        payload["parameters"]["seed"] = _seed(cfg)
    if negative:
        payload["input"]["negative_prompt"] = negative
    resp = request(
        endpoint,
        data=payload,
        headers={"Authorization": "Bearer " + key, "X-DashScope-Async": "enable"},
        method="POST",
        ctx=ctx,
        timeout=120,
    )
    task_id = (resp.get("output") or {}).get("task_id")
    if not task_id:
        raise RuntimeError("提交任务失败：%s" % json.dumps(resp, ensure_ascii=False)[:200])
    poll = "%s://%s/api/v1/tasks/%s" % (parts.scheme, parts.netloc, task_id)
    limit = float(cfg.get("GALGAME_IMAGE_TIMEOUT", "180"))
    started = time.time()
    last = ""
    while time.time() - started < limit:
        time.sleep(6)
        state = request(poll, headers={"Authorization": "Bearer " + key}, ctx=ctx, timeout=60)
        out = state.get("output") or {}
        status = out.get("task_status", "")
        if status == "SUCCEEDED":
            urls = [r.get("url") for r in (out.get("results") or []) if r.get("url")]
            if urls:
                return get_json_bytes(urls[0], ctx, trusted_origin=endpoint)
            raise RuntimeError("任务成功但没有 url：%s" % json.dumps(out, ensure_ascii=False)[:200])
        if status in ("FAILED", "CANCELED", "UNKNOWN"):
            raise RuntimeError("任务失败：%s %s" % (status, out.get("message", "")))
        if status != last:
            print("  · 任务 %s %s" % (task_id[:8], status))
            last = status
    raise RuntimeError("等待任务超时（%ds）：%s" % (int(limit), task_id))


def generate(cfg, key, prompt, negative, size, ctx):
    endpoint = cfg.get("GALGAME_IMAGE_ENDPOINT", "")
    if not endpoint:
        raise RuntimeError("没配 GALGAME_IMAGE_ENDPOINT")
    if "compatible-mode" in endpoint or "images/generations" in endpoint:
        return compatible_generate(cfg, key, prompt, negative, size, ctx)
    return native_generate(cfg, key, prompt, negative, size, ctx)


# ---------------------------------------------------------------- 图片后处理

def load_pillow():
    try:
        from PIL import Image, ImageDraw, ImageFilter

        return Image, ImageDraw, ImageFilter
    except ImportError:
        return None, None, None


def center_crop_resize(im, target):
    Image, _, _ = load_pillow()
    w, h = im.size
    tr = target[0] / target[1]
    sr = w / h
    if sr > tr:
        nw = int(h * tr)
        box = ((w - nw) // 2, 0, (w - nw) // 2 + nw, h)
    else:
        nh = int(w / tr)
        box = (0, (h - nh) // 2, w, (h - nh) // 2 + nh)
    return im.crop(box).resize(target, Image.LANCZOS)


def save_background(raw, out_path, target=BG_TARGET, quality=85):
    Image, _, _ = load_pillow()
    if Image is None:
        with open(out_path + ".raw", "wb") as f:
            f.write(raw)
        print("  ! 没装 Pillow，原图存为 %s.raw" % out_path)
        return out_path + ".raw"
    im = Image.open(__import__("io").BytesIO(raw)).convert("RGB")
    im = center_crop_resize(im, target)
    im.save(out_path, "JPEG", quality=quality, optimize=True)
    return out_path


def cutout_alpha(im, Image, ImageDraw, ImageFilter, tol=26):
    """从四边洪水填充纯色底，再给 alpha 做 1.2px 羽化。"""
    rgba = im.convert("RGBA")
    if rgba.getchannel("A").getextrema()[0] < 255:
        return rgba
    rgb = im.convert("RGB")
    w, h = rgb.size
    marker = (255, 0, 255)
    filled = rgb.copy()
    seeds = [
        (2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3),
        (w // 2, 2), (2, h // 3), (w - 3, h // 3), (w // 2, h - 3),
        (w // 4, 2), (3 * w // 4, 2),
    ]
    for sx, sy in seeds:
        try:
            ImageDraw.floodfill(filled, (sx, sy), marker, thresh=tol * 4)
        except Exception:
            pass
    alpha = Image.new("L", (w, h), 255)
    ap, fp = alpha.load(), filled.load()
    for y in range(h):
        for x in range(w):
            if fp[x, y] == marker:
                ap[x, y] = 0
    alpha = alpha.filter(ImageFilter.GaussianBlur(1.2))
    box = alpha.getbbox()
    if box:
        pad = 6
        box = (max(0, box[0] - pad), max(0, box[1] - pad),
               min(w, box[2] + pad), min(h, box[3] + pad))
        rgb = rgb.crop(box)
        alpha = alpha.crop(box)
    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    return out


def content_bbox(im):
    box = im.split()[3].getbbox()
    if box:
        return box
    w, h = im.size
    return (0, 0, w, h)


def normalize_sprite(im, Image, canvas=SPRITE_TARGET, height_ratio=0.96):
    """按内容高度归一化到画布：人物高度占 height_ratio，底边对齐、水平居中。
    自己提供的图和模型出的图都走这一套，跨图人物大小才一致。"""
    cw, ch = canvas
    box = content_bbox(im)
    body = im.crop(box)
    bw, bh = body.size
    if bw <= 0 or bh <= 0:
        raise ValueError("图片内容为空")
    scale = (ch * height_ratio) / float(bh)
    max_w = cw * 0.98
    if bw * scale > max_w:
        scale = max_w / float(bw)
    size = (max(1, int(round(bw * scale))), max(1, int(round(bh * scale))))
    body = body.resize(size, Image.LANCZOS)
    out = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    out.paste(body, ((cw - size[0]) // 2, max(0, ch - size[1])), body)
    return out


def save_sprite(raw, out_path, target=SPRITE_TARGET, quality=88):
    Image, ImageDraw, ImageFilter = load_pillow()
    import io

    if Image is None:
        path = out_path + ".raw"
        with open(path, "wb") as f:
            f.write(raw)
        print("  ! 没装 Pillow，原图存为 %s" % path)
        return path
    im = Image.open(io.BytesIO(raw))
    has_alpha = im.mode == "RGBA" and im.getextrema()[3][0] < 250
    if not has_alpha:
        im = cutout_alpha(im, Image, ImageDraw, ImageFilter)
    else:
        im = im.convert("RGBA")
    im = normalize_sprite(im, Image, target)
    im.save(out_path, "WEBP", quality=quality)
    return out_path


# ---------------------------------------------------------------- 任务编排

def gen_standing_mode(cfg):
    try:
        return int(cfg.get("GALGAME_GEN_STANDING", "0") or 0)
    except (TypeError, ValueError):
        return 0


def collect_jobs(cfg):
    jobs = []
    for scene in cfg.scenes():
        jobs.append({
            "kind": "background",
            "id": scene,
            "path": os.path.join(cfg.game, "picture", "scene", scene + ".jpg"),
            "prompt": bg_prompt(cfg, scene),
            "negative": BG_NEGATIVE,
            "size": cfg.get("GALGAME_IMAGE_SIZE", "1280*720"),
        })
    # 立绘开关为 0 时不生成、也不抠图，直接用 picture/standing/ 里现有的图
    if gen_standing_mode(cfg) == 0:
        return jobs
    anchor_note = cfg.get("GALGAME_ART_NOTE")
    for persona in cfg.heroines():
        safe_id = safe_component(persona["id"], "role")
        folder = os.path.join(cfg.game, "picture", "standing", safe_id)
        ids = list((persona.get("standings") or {}).keys()) or cfg.moods()
        for sid in ids:
            jobs.append({
                "kind": "sprite",
                "id": "%s/%s" % (safe_id, sid),
                "path": os.path.join(folder, sid + ".webp"),
                "prompt": sprite_prompt(cfg, persona, sid, anchor=anchor_note),
                "negative": SPRITE_NEGATIVE,
                "size": cfg.get("GALGAME_IMAGE_SIZE_PORTRAIT", "960*1440"),
            })
    return jobs


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成 galgame 框架的背景与立绘")
    ap.add_argument("--game-dir", default=".", help="包含 options.txt 和 game/ 的目录")
    ap.add_argument("--only", default="", help="scenes / sprites / <场景id> / <角色名字>/<立绘id>")
    ap.add_argument("--force", action="store_true", help="已存在的文件也重新生成")
    ap.add_argument("--seed", default="", help="固定随机种子，重抽同一张时换个数字")
    ap.add_argument("--dry-run", action="store_true", help="只打印提示词和目标路径，不调接口")
    ap.add_argument("--insecure", action="store_true", help="跳过证书校验，仅限本地试跑")
    args = ap.parse_args(argv)

    cfg = Config(args.game_dir)
    if args.seed:
        cfg.files["GALGAME_IMAGE_SEED"] = str(args.seed)
    if not os.path.isdir(cfg.game):
        print("! %s 下没有 game/ 目录" % cfg.dir, file=sys.stderr)
        return 2

    jobs = collect_jobs(cfg)
    if args.only:
        want = args.only.strip("/\\").replace("\\", "/")
        for cut in ("game/", "assets/"):
            if want.startswith(cut):
                want = want[len(cut):]
        if want in ("scenes", "scene", "backgrounds", "background"):
            jobs = [j for j in jobs if j["kind"] == "background"]
        elif want in ("illustration", "illustrations", "sprites", "sprite"):
            jobs = [j for j in jobs if j["kind"] == "sprite"]
        else:
            for cut in ("scene/", "illustration/", "scenes/"):
                if want.startswith(cut):
                    want = want[len(cut):]
                    break
            want = os.path.splitext(want)[0]
            jobs = [j for j in jobs if j["id"] == want or j["id"] == want.split(":", 1)[-1]]

    if gen_standing_mode(cfg) == 0:
        print("立绘开关 GALGAME_GEN_STANDING=0：不生成也不抠图，直接用 picture/standing/ 里现有的图。"
              "要生成请设成 1（harness）或 2（生图模型）。")
    if not jobs:
        print("没有可执行的任务。")
        return 0

    if args.dry_run:
        for j in jobs:
            print("[%s] %s -> %s (%s)" % (j["kind"], j["id"], os.path.relpath(j["path"], cfg.dir), j["size"]))
            print("    " + j["prompt"])
        print("共 %d 项，dry-run 未调用接口" % len(jobs))
        return 0

    key = cfg.get("GALGAME_IMAGE_KEY") or cfg.get("GALGAME_KEY")
    if not key:
        print("! 没有生图密钥：GALGAME_IMAGE_KEY 和 GALGAME_KEY 都是空的", file=sys.stderr)
        return 2
    if not cfg.get("GALGAME_IMAGE_ENDPOINT"):
        print("! 没有配 GALGAME_IMAGE_ENDPOINT", file=sys.stderr)
        return 2
    ctx = ssl_context(cfg, insecure=args.insecure)

    manifest_path = os.path.join(cfg.game, "art_manifest.json")
    manifest = {}
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if hasattr(loaded, "get"):
                manifest = loaded
        except (OSError, ValueError):
            manifest = {}
    entry = manifest.setdefault("images", {})

    done = skipped = failed = 0
    for j in jobs:
        if os.path.exists(j["path"]) and not args.force:
            print("= 跳过 %s（已存在）" % j["id"])
            skipped += 1
            continue
        os.makedirs(os.path.dirname(j["path"]), exist_ok=True)
        print("- 生成 %s %s" % (j["kind"], j["id"]))
        try:
            raw = generate(cfg, key, j["prompt"], j["negative"], j["size"], ctx)
            if j["kind"] == "background":
                out = save_background(raw, j["path"])
            else:
                out = save_sprite(raw, j["path"])
            entry[j["id"]] = {
                "kind": j["kind"],
                "file": os.path.relpath(out, cfg.game).replace(os.sep, "/"),
                "model": cfg.get("GALGAME_IMAGE_MODEL", ""),
                "size": j["size"],
                "prompt": j["prompt"],
                "at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            done += 1
        except (urllib.error.URLError, RuntimeError, OSError, ValueError) as exc:
            text = str(exc)
            if "CERTIFICATE_VERIFY_FAILED" in text:
                text += "（装一下 certifi，或保留 game/cacert.pem；本地试跑可加 --insecure）"
            if key and key in text:
                text = text.replace(key, "***")
            print("  ! 失败：%s" % text[:220], file=sys.stderr)
            failed += 1
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

    print("完成 %d，跳过 %d，失败 %d；清单见 %s" % (done, skipped, failed, os.path.relpath(manifest_path, cfg.dir)))
    print("尺寸规格与重画建议见技能包 references/art.md")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

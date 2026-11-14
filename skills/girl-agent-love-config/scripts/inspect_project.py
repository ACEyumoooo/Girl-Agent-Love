#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""体检 galgame Ren'Py 框架项目，输出可直接照着改的配置清单。

用法：
    python inspect_project.py <项目目录>
    python inspect_project.py <项目目录> --strict

只读，不改文件。不打印 API Key 的内容，只报告是否已填。
"""

import argparse
import json
import os
import re
import sys

AUDIO_EXT = (".mp3", ".ogg", ".wav", ".m4a", ".opus")
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp")
BOOL_KEYS = (
    "GALGAME_HEROINE_AUTO", "GALGAME_PLAYER_SPRITE", "GALGAME_ENDLESS",
    "GALGAME_AUTO_CHARACTER", "GALGAME_SUBAGENTS", "GALGAME_USING_HARNESS",
    "GALGAME_VOICE", "GALGAME_VOICE_PLAYER", "GALGAME_DOCTOR",
    "GALGAME_HARNESS_SELF_HEAL", "GALGAME_ENABLE_CHAPTER",
    "GALGAME_SCENE_LOCK", "GALGAME_SHOT_VARY", "GALGAME_DEBUG",
    "GALGAME_AUTOSTART",
)
TIME_NAMES = ("day", "dusk", "night")
SEIKAI_SECTIONS = (
    "一句话", "时代与地点", "世界规则", "主要场所",
    "人物关系", "禁忌与尺度", "当前局势",
)


class Report:
    def __init__(self):
        self.items = []

    def add(self, level, message, fix=""):
        self.items.append((level, message, fix))

    def fail(self, message, fix=""):
        self.add("FAIL", message, fix)

    def warn(self, message, fix=""):
        self.add("WARN", message, fix)

    def ok(self, message):
        self.add("OK", message)

    def info(self, message):
        self.add("INFO", message)

    def count(self, level):
        return sum(1 for item in self.items if item[0] == level)


def find_root(given):
    path = os.path.abspath(given or ".")
    if os.path.isfile(os.path.join(path, "options.txt")):
        return path
    if os.path.isfile(os.path.join(path, "GalGameFramework", "options.txt")):
        return os.path.join(path, "GalGameFramework")
    for name in sorted(os.listdir(path)) if os.path.isdir(path) else []:
        sub = os.path.join(path, name)
        if os.path.isfile(os.path.join(sub, "options.txt")):
            return sub
    return path


def read_options(root, filename="options.txt"):
    data = {}
    path = os.path.join(root, filename)
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                data[key.strip()] = value.strip()
    except OSError:
        pass
    return data


def on(cfg, key, default="0"):
    return str(cfg.get(key, default)).strip().lower() in ("1", "true", "yes", "on")


def split_list(raw):
    raw = str(raw or "").strip().strip("[]")
    out = []
    for item in re.split(r"[,，]", raw):
        item = item.strip().strip("\"'")
        if item:
            out.append(item)
    return out


def parse_persona(path):
    text = ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None
    meta = {}
    body = text
    if text.startswith("---"):
        end = text.find("---", 3)
        if end > 0:
            for line in text[3:end].splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    meta[key.strip()] = value.strip()
            body = text[end + 3:].strip()
    standings = []
    for line in body.splitlines():
        match = re.match(r"^\s*id\s*[：:]\s*(\S+)", line)
        if match:
            standings.append(match.group(1).strip())
    aliases = split_list(meta.get("aliases", ""))
    return {
        "file": os.path.basename(path),
        "id": (meta.get("id") or os.path.splitext(os.path.basename(path))[0]).strip(),
        "name": (meta.get("name") or meta.get("id") or "").strip(),
        "gender": (meta.get("gender") or "").strip().lower(),
        "aliases": aliases,
        "lead": str(meta.get("lead", "")).lower() in ("1", "true", "yes"),
        "romance": str(meta.get("romance", "")).lower() in ("1", "true", "yes"),
        "standings": standings,
        "body": body,
    }


def scene_files(root):
    base = os.path.join(root, "game", "picture", "scene")
    out = []
    if not os.path.isdir(base):
        return out
    for name in sorted(os.listdir(base)):
        stem, ext = os.path.splitext(name)
        if ext.lower() in IMAGE_EXT and "_" in stem:
            out.append((stem, os.path.join(base, name)))
    return out


def bgm_files(root):
    base = os.path.join(root, "game", "bgm")
    out = []
    if not os.path.isdir(base):
        return out
    for name in sorted(os.listdir(base)):
        stem, ext = os.path.splitext(name)
        if stem.isdigit() and ext.lower() in AUDIO_EXT:
            out.append((stem, name))
    return out


def standing_file(root, pid, sid):
    base = os.path.join(root, "game", "picture", "standing", pid)
    for ext in IMAGE_EXT:
        path = os.path.join(base, str(sid) + ext)
        if os.path.exists(path):
            return path
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description="检查 galgame Ren'Py 框架的配置")
    parser.add_argument("project", nargs="?", default=".")
    parser.add_argument("--strict", action="store_true", help="有 FAIL 时返回 1")
    args = parser.parse_args(argv)

    root = find_root(args.project)
    cfg = read_options(root)
    rep = Report()

    print("galgame 配置体检")
    print("项目：" + root)
    print("")

    for rel in ("options.txt", "game/ai.rpy", "game/script.rpy", "game/seikai.md"):
        if not os.path.exists(os.path.join(root, rel)):
            rep.fail("缺少 " + rel, "确认目录是 GalGameFramework 根目录，不是 game/ 里面")
    for rel in ("LICENSE", "NOTICE", "game/LICENSE.txt", "game/fonts/LICENSE-OFL.txt"):
        if not os.path.exists(os.path.join(root, rel)):
            rep.warn("缺少 " + rel, "分发前补齐许可证文件")

    # Mirror runtime precedence for the text-model settings used by this check.
    file_key = read_options(root, "key.txt").get("GALGAME_KEY", "")
    key = os.environ.get("GALGAME_KEY", "").strip() or file_key or cfg.get("GALGAME_KEY", "")
    for name in ("GALGAME_USING_HARNESS", "GALGAME_HOST"):
        if os.environ.get(name, "").strip():
            cfg[name] = os.environ[name].strip()
    harness = on(cfg, "GALGAME_USING_HARNESS") and cfg.get("GALGAME_HOST") == "harness"
    if harness:
        rep.info("文本模型由 harness 宿主提供")
    elif key:
        rep.ok("文本模型 Key 已填；未填写的端点和模型将使用运行时默认值")
    else:
        rep.info("当前使用本地演示")

    # 布尔开关
    for name in BOOL_KEYS:
        if name in cfg and str(cfg[name]).strip() not in ("0", "1"):
            rep.warn(name + " 不是 0/1", "改成 0 或 1")

    # 自愈 / harness
    doctor_on = on(cfg, "GALGAME_DOCTOR")
    doctor_model = str(cfg.get("GALGAME_DOCTOR_MODEL", "")).strip()
    harness = on(cfg, "GALGAME_USING_HARNESS") and str(cfg.get("GALGAME_HOST", "")).strip() == "harness"
    if doctor_on and not doctor_model:
        rep.warn("GALGAME_DOCTOR=1 但没填自愈模型", "填 GALGAME_DOCTOR_MODEL，或把开关改回 0")
    if doctor_on and harness:
        rep.info("harness + 自愈模型：harness 请求会带 self_heal=false，由 option 模型修")
    if harness:
        rep.info("当前是 harness 模式，文本由外层 agent 提供")
        if on(cfg, "GALGAME_HARNESS_SELF_HEAL", "1"):
            rep.info("harness 允许自己修坏响应；不想让它修就把 GALGAME_HARNESS_SELF_HEAL 设 0")

    # 人物
    pdir = os.path.join(root, "game", "persona")
    personas = []
    if os.path.isdir(pdir):
        for name in sorted(os.listdir(pdir)):
            if not name.endswith(".md") or name.startswith("_") or name.lower().startswith("readme"):
                continue
            item = parse_persona(os.path.join(pdir, name))
            if item:
                personas.append(item)
    if not personas:
        rep.fail("persona/ 里没有人物卡", "至少写 me.md 和一张女主角卡")
    names = {}
    aliases_ci = {}
    for p in personas:
        names[p["name"]] = p
        names[p["id"]] = p
        names[p["name"].lower()] = p
        names[p["id"].lower()] = p
        if not p["name"]:
            rep.fail(p["file"] + " 没有 name", "frontmatter 写 name")
        if not p["gender"]:
            rep.warn(p["file"] + " 没写 gender", "gender 只写 female / male / other")
        elif p["gender"] not in ("female", "male", "other"):
            rep.warn(p["file"] + " 的 gender=" + p["gender"], "只写 female / male / other")
        for alias in p["aliases"]:
            low = alias.lower()
            if low in aliases_ci and aliases_ci[low] != p["id"]:
                rep.warn("别名重复：" + alias + " 同时属于 " + aliases_ci[low] + " 和 " + p["id"], "改掉一个，避免解析到错的人")
            aliases_ci[low] = p["id"]
        if not p["standings"]:
            rep.warn(p["file"] + " 没有立绘 id", "至少写一设立绘，id 用数字")
    if not any(p["name"] == "我" for p in personas):
        rep.warn("没有 me.md 玩家卡", "复制 _ME_TEMPLATE.md 成 me.md")
    romance = [p for p in personas if p["romance"] and p["name"] != "我"]
    leads = [p for p in personas if p["lead"] and p["name"] != "我"]
    if not romance:
        rep.warn("没有 romance: true 的可攻略角色", "给女主角写 romance: true")
    heroine = str(cfg.get("GALGAME_HEROINE", "")).strip()
    if heroine:
        hit = names.get(heroine) or names.get(heroine.lower())
        if not hit:
            for p in personas:
                if heroine.lower() in [a.lower() for a in p["aliases"]]:
                    hit = p
                    break
        if not hit:
            rep.warn("GALGAME_HEROINE=" + heroine + " 找不到对应人物卡", "写 id、name 或 aliases 里的名字")
    elif not leads and not on(cfg, "GALGAME_HEROINE_AUTO", "1"):
        rep.warn("没指定女主角，也没有 lead: true", "给一张卡写 lead: true，或填 GALGAME_HEROINE")

    # 立绘文件
    for p in personas:
        if p["name"] == "我" and not on(cfg, "GALGAME_PLAYER_SPRITE"):
            continue
        ids = p["standings"] or ["1"]
        for sid in ids:
            if not str(sid).isdigit():
                rep.warn(p["file"] + " 的立绘 id 不是数字：" + str(sid), "id 只写数字")
                continue
            path = standing_file(root, p["id"], sid)
            if not path:
                rep.warn("缺立绘 " + p["id"] + "/" + str(sid), "放 game/picture/standing/" + p["id"] + "/" + str(sid) + ".webp")

    # 世界观
    seikai = os.path.join(root, "game", "seikai.md")
    if os.path.exists(seikai):
        text = open(seikai, "r", encoding="utf-8").read()
        for title in SEIKAI_SECTIONS:
            if "## " + title not in text:
                rep.warn("seikai.md 缺「" + title + "」", "按七节格式补齐")
        if "## 当前局势" in text:
            tail = text.split("## 当前局势", 1)[1].strip()
            if not tail:
                rep.warn("seikai.md 的「当前局势」是空的", "写一句开局局势")
    else:
        rep.fail("没有 game/seikai.md", "复制 seikai.example.md 再改")

    # 场景
    scenes = scene_files(root)
    good_scenes = [(s, p) for s, p in scenes if s.split("_", 1)[0] in TIME_NAMES]
    bad_scenes = [(s, p) for s, p in scenes if s.split("_", 1)[0] not in TIME_NAMES]
    if not good_scenes:
        rep.fail("picture/scene/ 没有可用场景", "放 day_/dusk_/night_ 开头的图，例如 day_classroom.jpg")
    else:
        combos = sorted(s for s, _p in good_scenes)
        rep.ok("场景 %d 张：%s" % (len(combos), "、".join(combos[:8])) + ("…" if len(combos) > 8 else ""))
        times = sorted(set(s.split("_", 1)[0] for s, _p in good_scenes))
        if len(times) < 3:
            rep.warn("场景时间只有 " + "、".join(times), "需要夜晚就补 night_*.jpg")
    for stem, path in bad_scenes:
        rep.warn("场景前缀不是 day/dusk/night：" + stem, "改名成 day_/dusk_/night_，否则引擎会忽略")

    # 开场
    opening = os.path.join(root, "game", "opening.json")
    if os.path.exists(opening):
        try:
            data = json.load(open(opening, "r", encoding="utf-8"))
            beats = data.get("beats") or []
            if not beats:
                rep.warn("opening.json 没有 beats", "写两拍开场，或删掉这个文件")
            for beat in beats:
                scene = beat.get("scene")
                if scene and scene not in [s for s, _p in scenes]:
                    rep.warn("opening.json 的场景不存在：" + str(scene), "改成 picture/scene/ 里已有的场景")
        except ValueError as exc:
            rep.warn("opening.json 不是合法 JSON：" + str(exc), "修 JSON，或删掉让引擎用章节开头")

    # BGM
    bgms = bgm_files(root)
    bgm_dir = os.path.join(root, "game", "bgm")
    bgm_doc = os.path.exists(os.path.join(bgm_dir, "bgm.md"))
    if bgms:
        rep.ok("BGM %d 首：%s" % (len(bgms), "、".join(i for i, _n in bgms)))
        if not bgm_doc:
            rep.warn("有 BGM 但缺 bgm.md", "写每个 id 什么时候用，模型才选得准")
    else:
        rep.info("没有 BGM 音频，引擎不会注入 BGM 规则")
        if bgm_doc:
            rep.warn("bgm.md 在但没有任何数字音频", "放 1.mp3、2.ogg 这类文件，重启后生效")

    # 语音
    voice_on = on(cfg, "GALGAME_VOICE")
    if voice_on:
        vmode = str(cfg.get("GALGAME_VOICE_MODE", "tts")).strip().lower()
        vmodel = str(cfg.get("GALGAME_VOICE_MODEL", "")).strip()
        if not vmodel:
            rep.warn("开了语音但 GALGAME_VOICE_MODEL 为空", "填 qwen3-tts-flash 或你的语音模型")
        if vmode == "clone":
            ws = str(cfg.get("GALGAME_VOICE_CLONE_WORKSPACE", "")).strip()
            if not ws:
                rep.warn("clone 模式缺 GALGAME_VOICE_CLONE_WORKSPACE", "填百炼业务空间 WorkspaceId")
            refs = os.path.join(root, "game", "voice_example")
            for p in romance:
                found = False
                for base in (p["name"], p["id"]):
                    for ext in AUDIO_EXT:
                        if os.path.exists(os.path.join(refs, base + ext)):
                            found = True
                            break
                if not found:
                    rep.warn("clone 缺参考音频：" + p["name"], "放 game/voice_example/" + p["name"] + ".wav")
            if "qwen-audio" in vmodel and vmode != "clone":
                rep.warn("qwen-audio 模型需要 clone 模式", "把 GALGAME_VOICE_MODE 改成 clone，或换成 qwen3-tts-flash")
    else:
        rep.info("语音关闭")

    # 生图
    gen_scene = str(cfg.get("GALGAME_GEN_SCENE", "0")).strip()
    gen_stand = str(cfg.get("GALGAME_GEN_STANDING", "0")).strip()
    img_ep = str(cfg.get("GALGAME_IMAGE_ENDPOINT", "")).strip()
    img_key = str(cfg.get("GALGAME_IMAGE_KEY", "")).strip()
    if gen_scene == "2" or gen_stand == "2":
        if not img_ep or not (img_key or key):
            rep.fail("生图开关是 2，但没配 GALGAME_IMAGE_ENDPOINT/KEY", "补生图接口，或把开关改回 0")
    if (gen_scene == "1" or gen_stand == "1") and not harness:
        rep.warn("生图开关是 1，但当前不是 harness", "改回 0 或 2，或改用 harness 启动")
    if gen_scene == "0" and not good_scenes:
        rep.warn("生图为 0 且没有背景", "先补图，或临时把 GALGAME_GEN_SCENE 设 2")
    if gen_stand == "0":
        missing = 0
        for p in personas:
            if p["name"] == "我" and not on(cfg, "GALGAME_PLAYER_SPRITE"):
                continue
            for sid in (p["standings"] or ["1"]):
                if str(sid).isdigit() and not standing_file(root, p["id"], sid):
                    missing += 1
        if missing:
            rep.warn("缺 %d 张立绘，生图开关是 0" % missing, "补图，或临时把 GALGAME_GEN_STANDING 设 2")

    # 输出
    order = {"FAIL": 0, "WARN": 1, "INFO": 2, "OK": 3}
    for level, message, fix in sorted(rep.items, key=lambda x: order.get(x[0], 9)):
        print("[" + level + "] " + message)
        if fix:
            print("       -> " + fix)
    print("")
    print("结果：FAIL %d，WARN %d，OK %d" % (rep.count("FAIL"), rep.count("WARN"), rep.count("OK")))
    if rep.count("FAIL"):
        print("先修 FAIL，再处理 WARN。改完 options.txt 后重启游戏。")
    elif rep.count("WARN"):
        print("没有阻塞项，可以启动；WARN 按需处理。")
    else:
        print("可以直接启动。")
    return 1 if args.strict and rep.count("FAIL") else 0


if __name__ == "__main__":
    sys.exit(main())

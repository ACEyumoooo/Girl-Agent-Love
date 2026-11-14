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

"""把用户自己提供的立绘导入成框架能直接用的规格。

用户给的图通常是三种：已经抠好的透明 PNG/WebP、白底 PNG/JPG、尺寸和构图各不
一样的混装。这个脚本统一处理成：

    game/picture/standing/<角色id>/<立绘id>.webp
    920x1380 透明画布，人物高度占画布 96%，底边对齐、水平居中

关键做法是**按内容包围盒归一化**，不是按整张画布缩放。这样就算每张图的留白、
尺寸都不一样，人物在画面里的大小和落地位置也一致，不会一张头大一张头小。

- 已经有透明通道的图：直接跳过抠图，不去动边缘
- 没有透明通道的图：按白底抠图（四边洪水填充 + 羽化），和 gen_art.py 同一套
- 原图默认备份到 game/picture/_import_src/，不会覆盖你的源文件

用法：
  # 单张
  python import_standing.py --game-dir . --role aya --id 1 --file ./她的立绘.png

  # 整个目录，文件名就是立绘 id（1.png、2.webp、aya-3.png 都认）
  python import_standing.py --game-dir . --role aya --dir ./立绘/

  # 白底图换更宽松的抠图阈值，或强制不抠
  python import_standing.py --game-dir . --role aya --id 2 --file ./白底.jpg --tol 40
  python import_standing.py --game-dir . --role aya --id 2 --file ./已经透明.webp --cutout off

  # 先看会写到哪，不动文件
  python import_standing.py --game-dir . --role aya --dir ./立绘/ --dry-run
"""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import gen_art as ga  # noqa: E402  复用它的 Pillow 加载与抠图实现

DEFAULT_CANVAS = (920, 1380)
DEFAULT_HEIGHT_RATIO = 0.96
IMG_EXT = (".png", ".webp", ".jpg", ".jpeg", ".bmp")


def has_alpha(im):
    """真透明才算：整张 alpha 全 255 的“假 RGBA”按白底图处理。"""
    if im.mode != "RGBA":
        return False
    try:
        return im.getextrema()[3][0] < 250
    except Exception:
        return False


def normalize(im, Image, canvas, height_ratio, fit):
    """contain：按内容高度归一化（和 gen_art 同一套）；cover：按画布比例裁满。"""
    if fit == "cover":
        src_ratio = im.width / float(im.height)
        tgt_ratio = canvas[0] / float(canvas[1])
        if src_ratio > tgt_ratio:
            nw = int(im.height * tgt_ratio)
            x = (im.width - nw) // 2
            im = im.crop((x, 0, x + nw, im.height))
        else:
            nh = int(im.width / tgt_ratio)
            y = (im.height - nh) // 2
            im = im.crop((0, y, im.width, y + nh))
        return im.resize(canvas, Image.LANCZOS)
    return ga.normalize_sprite(im, Image, canvas, height_ratio)


def gen_standing_mode(game_dir):
    """读立绘开关（环境变量优先，和引擎一致）：0 表示不生成立绘，导入时也不抠图。"""
    cfg = ga.read_kv(os.path.join(game_dir, "options.txt"))
    raw = os.environ.get("GALGAME_GEN_STANDING") or cfg.get("GALGAME_GEN_STANDING") or "0"
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return 0


def import_one(src, dst, Image, ImageDraw, ImageFilter, args):
    raw = open(src, "rb").read()
    im = Image.open(io.BytesIO(raw))
    cut = False
    if has_alpha(im):
        im = im.convert("RGBA")
    elif args.cutout == "off":
        # 不生图模式（或显式 --cutout off）：不抠图，白底原样保留
        im = im.convert("RGBA")
        print("  · %s 没有透明通道，按设置未抠图" % os.path.basename(src))
    else:
        im = ga.cutout_alpha(im, Image, ImageDraw, ImageFilter, tol=args.tol)
        cut = True
    out = normalize(im, Image, args.canvas, args.height_ratio, args.fit)
    if args.dry_run:
        return {"src": src, "dst": dst, "cutout": cut, "size": out.size}, None
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if args.format == "png":
        out.save(dst, "PNG")
    else:
        out.save(dst, "WEBP", quality=args.quality)
    return {"src": src, "dst": dst, "cutout": cut, "size": out.size}, os.path.getsize(dst)


def guess_id(path, role):
    stem = os.path.splitext(os.path.basename(path))[0]
    for sep in ("-", "_", " "):
        if sep in stem:
            head, tail = stem.split(sep, 1)
            if head.lower() == role.lower() and tail:
                return tail
    return stem


def collect(args):
    files = []
    if args.dir:
        for name in sorted(os.listdir(args.dir)):
            if name.lower().endswith(IMG_EXT):
                p = os.path.join(args.dir, name)
                files.append((guess_id(p, args.role), p))
    elif args.file:
        if not args.id:
            raise SystemExit("单张导入需要 --id")
        files.append((str(args.id), args.file))
    else:
        raise SystemExit("给 --file 或 --dir")
    return files


def load_manifest(game_dir):
    path = os.path.join(game_dir, "art_manifest.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if hasattr(data, "get"):
                return data
        except (OSError, ValueError):
            pass
    return {"images": {}}


def main(argv=None):
    ap = argparse.ArgumentParser(description="把用户提供的立绘导入成框架规格")
    ap.add_argument("--game-dir", default=".", help="包含 game/ 的游戏目录")
    ap.add_argument("--role", required=True, help="角色 id，对应 persona/<id>.md")
    ap.add_argument("--id", default="", help="单张导入时的立绘 id（数字）")
    ap.add_argument("--file", default="", help="单张图片路径")
    ap.add_argument("--dir", default="", help="批量目录，文件名即立绘 id")
    ap.add_argument("--canvas", default="920x1380", help="画布尺寸，默认 920x1380")
    ap.add_argument("--height-ratio", type=float, default=DEFAULT_HEIGHT_RATIO,
                    help="人物高度占画布比例，默认 0.96")
    ap.add_argument("--fit", choices=("contain", "cover"), default="contain",
                    help="contain 保留完整人物；cover 会裁到填满画布")
    ap.add_argument("--cutout", choices=("auto", "on", "off"), default="auto",
                    help="auto：没有透明通道才抠图；on：强制抠；off：不抠")
    ap.add_argument("--tol", type=int, default=26, help="白底抠图容差，默认 26")
    ap.add_argument("--quality", type=int, default=88, help="WebP 质量，默认 88")
    ap.add_argument("--format", choices=("webp", "png"), default="webp")
    ap.add_argument("--no-backup", action="store_true", help="不备份源文件")
    ap.add_argument("--force", action="store_true", help="已存在的目标也覆盖")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不写文件")
    args = ap.parse_args(argv)

    try:
        w, h = [int(x) for x in args.canvas.lower().split("x")]
    except ValueError:
        raise SystemExit("--canvas 写成 920x1380 这种格式")
    args.canvas = (w, h)

    game = os.path.abspath(os.path.join(args.game_dir, "game"))
    if not os.path.isdir(game):
        raise SystemExit("找不到 %s" % game)

    Image, ImageDraw, ImageFilter = ga.load_pillow()
    if Image is None:
        raise SystemExit("需要 Pillow：pip install pillow")

    if args.cutout == "on":
        args.cutout = "auto"  # 交给 has_alpha 判断，透明图仍然不重复抠
    elif args.cutout == "auto" and gen_standing_mode(args.game_dir) == 0:
        # 立绘开关为 0：不生成也不抠图，用户给什么就用什么
        args.cutout = "off"

    safe_role = ga.safe_component(args.role, "role")
    out_dir = os.path.join(game, "picture", "standing", safe_role)
    backup_dir = os.path.join(game, "picture", "_import_src")
    manifest = load_manifest(game)
    entries = manifest.setdefault("images", {})

    done = skipped = failed = 0
    for sid, src in collect(args):
        ext = ".png" if args.format == "png" else ".webp"
        dst = os.path.join(out_dir, str(sid) + ext)
        if os.path.exists(dst) and not args.force:
            print("= 跳过 %s（已存在，加 --force 覆盖）" % os.path.relpath(dst, game))
            skipped += 1
            continue
        try:
            info, size = import_one(src, dst, Image, ImageDraw, ImageFilter, args)
        except Exception as exc:
            print("! 失败 %s：%s" % (src, exc), file=sys.stderr)
            failed += 1
            continue
        print("%s %s -> %s%s" % (
            "- 导入" if not args.dry_run else "· 预览",
            os.path.basename(src),
            os.path.relpath(dst, game),
            "" if size is None else "（%d KB）" % (size // 1024),
        ))
        if not args.no_backup and not args.dry_run:
            os.makedirs(backup_dir, exist_ok=True)
            shutil.copy2(src, os.path.join(backup_dir, os.path.basename(src)))
        if not args.dry_run:
            entries["%s/%s" % (safe_role, sid)] = {
                "kind": "sprite",
                "file": os.path.relpath(dst, game).replace(os.sep, "/"),
                "model": "imported",
                "size": "%dx%d" % args.canvas,
                "prompt": "用户提供：%s" % os.path.basename(src),
                "cutout": "yes" if info["cutout"] else "no",
                "at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        done += 1

    if not args.dry_run:
        path = os.path.join(game, "art_manifest.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
        except OSError:
            pass
    print("完成 %d，跳过 %d，失败 %d" % (done, skipped, failed))
    if not args.dry_run and done:
        print("画布 %dx%d，人物高度占 %.0f%%，底边对齐；源图备份在 picture/_import_src/"
              % (args.canvas[0], args.canvas[1], args.height_ratio * 100))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

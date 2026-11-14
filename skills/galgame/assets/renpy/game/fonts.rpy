# Modified for GalGameFramework 1.7.4 (2026-11-10): shared startup/live font projection.
# 中文字体。具体文件由 options.txt 的 GALGAME_FONT 决定，
# 先查 game/fonts/ 里有没有这个文件，没有就退回思源黑体。
# gui.rpy 的 define 会直接用 FONT_PATH，这里再兜底一层。

# 菜单按钮专用的衬线字体（Noto Serif SC SemiBold，OFL 授权）。
# 与正文的思源黑体分开，只影响导航按钮，切 GALGAME_FONT 不会改到它。
define MENU_FONT_PATH = "fonts/NotoSerifSC-SemiBold.ttf"

init 1 python:
    def apply_font_path(path, rebuild=True):
        store.FONT_FILE = path[len("fonts/"):] if path.startswith("fonts/") else path.split("/")[-1]
        store.FONT_PATH = path
        for name in ("text_font", "name_text_font", "interface_text_font",
                     "button_text_font", "choice_button_text_font"):
            setattr(gui, name, path)
        for name in ("default", "say_dialogue", "say_label", "input",
                     "choice_button_text", "notify_text", "button_text", "text"):
            try:
                getattr(style, name).font = path
            except Exception:
                # Some optional styles are absent in stripped authoring templates.
                pass
        if rebuild:
            renpy.style.rebuild()

    apply_font_path(FONT_PATH, rebuild=False)

init 100 python:
    apply_font_path(FONT_PATH, rebuild=False)

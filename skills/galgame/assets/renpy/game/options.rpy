## This file contains options that can be changed to customize your
## game.
##
## Lines beginning with two '#' marks are comments, and you shouldn't
## uncomment them. Lines beginning with a single '#' mark are
## commented-out code, and you may want to uncomment them when
## appropriate.


## Basics ######################################################################

## A human-readable name of the game. This is used to set the default
## window title, and shows up in the interface and error reports.
##
## The _() surrounding the string marks it as eligible for translation.

define config.name = _("未命名作品")


## Determines if the title given above is shown on the main menu
## screen. Set this to False to hide the title.

define gui.show_name = True


## The version of the game.

define config.version = "1.0-b"

## 游戏内右键不打开原生游戏菜单（与本工程的 JSON 存档/设置体系不兼容）。
define config.game_menu_action = NullAction()

# Development tools are opt-in, including when run from an unpacked SDK project.
# GALGAME_DEBUG controls application logs only and does not enable these tools.
define config.developer = _on("GALGAME_DEVELOPER", "0")
define config.console = _on("GALGAME_DEVELOPER", "0")


## Text that is placed on the game's about screen. Place the text between
## the triple-quotes, and leave a blank line between paragraphs.

define gui.about = _p("""
一个实时生成的视觉小说短篇。

本作使用 galgame Ren'Py 实时生成框架，框架作者 ACE_yumoooo，遵循 Apache License 2.0。剧情与对白由语言模型实时生成，Ren'Py 负责显示、存档与界面。

引擎 Ren'Py，遵循 MIT 与 LGPL 许可；字体 Source Han Sans，SIL Open Font License 1.1；图像由 AI 生成，剧本与角色为原创。
""")


## A short name for the game used for executables and directories in the
## built distribution. This must be ASCII-only, and must not contain
## spaces, colons, or semicolons.

define build.name = "galgame"


## Sounds and music ############################################################

## These three variables control, among other things, which mixers are
## shown to the player by default. Setting one of these to False will
## hide the appropriate mixer.

define config.has_sound = True
define config.has_music = True
define config.has_voice = True


## To allow the user to play a test sound on the sound or voice channel,
## uncomment a line below and use it to set a sample sound to play.

# define config.sample_sound = "sample-sound.ogg"
# define config.sample_voice = "sample-voice.ogg"


## Uncomment the following line to set an audio file that will be played
## while the player is at the main menu. This file will continue playing
## into the game, until it is stopped or another file is played.

# define config.main_menu_music = "main-menu-theme.ogg"


## Transitions #################################################################
##
## These variables set transitions that are used when certain events occur.
## Each variable should be set to a transition, or None to indicate that
## no transition should be used.

## Entering or exiting the game menu.

define config.enter_transition = dissolve
define config.exit_transition = dissolve


## Between screens of the game menu.

define config.intra_transition = dissolve


## A transition that is used after a game has been loaded.

define config.after_load_transition = None


## Used when entering the main menu after the game has ended.

define config.end_game_transition = None


## A variable to set the transition used when the game starts
## does not exist. Instead, use a with statement after showing
## the initial scene.


## Window management ###########################################################
##
## This controls when the dialogue window is displayed. If "show", it is always
## displayed. If "hide", it is only displayed when dialogue is present. If
## "auto", the window is hidden before scene statements and shown again
## once dialogue is displayed.
##
## After the game has started, this can be changed with the "window show",
## "window hide", and "window auto" statements.

define config.window = "auto"


## Transitions used to show and hide the dialogue window

define config.window_show_transition = Dissolve(.2)
define config.window_hide_transition = Dissolve(.2)


## Preference defaults #########################################################

## Controls the default text speed. The default, 0, is infinite, while any
## other number is the number of characters per second to type out.

default preferences.text_cps = TEXT_CPS


## The default auto-forward delay. Larger numbers lead to longer waits,
## with 0 to 30 being the valid range.

default preferences.afm_time = 15


## Save directory ##############################################################
##
## Controls the platform-specific place Ren'Py will place the save
## files for this game. The save files will be placed in:
##
## Windows: %APPDATA\RenPy\<config.save_directory>
##
## Macintosh: $HOME/Library/RenPy/<config.save_directory>
##
## Linux: $HOME/.renpy/<config.save_directory>
##
## This generally should not be changed, and if it is, should always be a
## literal string, not an expression.

## 存档目录名。留空就用 galgame-<女主角立绘id>，换作品不会串档。
## 想固定写死就在 options.txt 里设 GALGAME_SAVE_DIR。

init 0 python:
    config.save_directory = _cfg("GALGAME_SAVE_DIR") or ("galgame-" + HEROINE_ILL)

    ## 图标：gui/window_icon.png 不存在时直接关掉，免得新作品删图就崩。
    if not os.path.exists(os.path.join(config.gamedir, "gui", "window_icon.png")):
        config.window_icon = None


## Build configuration #########################################################
##
## This section controls how Ren'Py turns your project into distribution
## files.

init python:

    ## The following functions take file patterns. File patterns are case-
    ## insensitive, and matched against the path relative to the base
    ## directory, with and without a leading /. If multiple patterns match,
    ## the first is used.
    ##
    ## In a pattern:
    ##
    ## / is the directory separator.
    ##
    ## * matches all characters, except the directory separator.
    ##
    ## ** matches all characters, including the directory separator.
    ##
    ## For example, "*.txt" matches txt files in the base directory, "game/**.ogg"
    ## matches ogg files in the game directory or any of its subdirectories, and
    ## "**.psd" matches psd files anywhere in the project.

    ## Classify files as None to exclude them from the built distributions.

    build.classify('**~', None)
    build.classify('**.bak', None)
    build.classify('**/.**', None)
    build.classify('**/#**', None)
    build.classify('**/thumbs.db', None)

    ## To archive files, classify them as 'archive'.

    # build.classify('game/**.png', 'archive')
    # build.classify('game/**.jpg', 'archive')

    ## Files matching documentation patterns are duplicated in a mac app
    ## build, so they appear in both the app and the zip file.

    build.documentation('*.html')
    build.documentation('*.txt')


## A Google Play license key is required to perform in-app purchases.
## It can be found in the Google Play developer console,
## under "Monetize" > "Monetization Setup" > "Licensing".

# define build.google_play_key = "..."


## The username and project name associated with an itch.io project,
## separated by a slash.

# define build.itch_project = "renpytom/test-project"


## 打包配置 ###################################################################

init python:
    # 打包目录/可执行文件跟随存档目录名（默认 galgame-<女主角 id>），
    # 多个作品打包后不会都叫 galgame 而互相覆盖。
    import re as _build_re
    _build_slug = _build_re.sub(
        r"[^A-Za-z0-9_-]+", "-", str(getattr(config, "save_directory", "") or "galgame")
    ).strip("-_") or "galgame"
    build.directory_name = _build_slug
    build.executable_name = _build_slug[:1].upper() + _build_slug[1:]
    build.classify('skills/**', None)
    build.classify('options.reference.txt', None)
    build.classify('key.txt', None)
    build.classify('ai_debug.log', None)
    build.classify('traceback.txt', None)
    build.classify('log.txt', None)
    build.classify('**.log', None)
    build.classify('model_requests.log.*', None)
    build.classify('ai_debug.log.*', None)
    build.classify('savedata/**', None)
    build.classify('tests/**', None)
    build.classify('game/zz_*', None)
    build.classify('game/saves/**', None)
    build.classify('game/cache/**', None)
    build.classify('game/voice/**', None)
    build.classify('game/voice_ids.json', None)
    build.classify('game/art_manifest.json', None)
    build.classify('start-game.bat', None)
    build.classify('lint.bat', None)

# Resolve optional title audio after options and settings helpers initialize.
init 10 python:
    config.main_menu_music = optional_title_music()

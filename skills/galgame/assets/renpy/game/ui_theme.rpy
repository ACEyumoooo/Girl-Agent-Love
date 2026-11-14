# GalGameFramework fixed light theme. Coordinates are logical pixels.
init offset = -3

define gal_ui_canvas = "#F2EEE5"
define gal_ui_panel = "#FFFCF6"
define gal_ui_card = "#F7F2E8"
define gal_ui_control = "#F0E9DB"
define gal_ui_hover = "#FBEBD0"
define gal_ui_selected = "#F5DFB6"
define gal_ui_ink = "#242A32"
define gal_ui_muted = "#525A64"
define gal_ui_disabled = "#616873"
define gal_ui_accent = "#805316"
define gal_ui_focus = "#805316"
define gal_ui_border = "#8B7C68"
define gal_ui_divider = "#D8CFBF"
define gal_ui_error = "#912E28"
define gal_ui_success = "#245B49"
define gal_ui_wash = "#211B1570"
define gal_ui_skin_panel = Frame("gui/theme/panel.png", 20, 20)
define gal_ui_skin_card = Frame("gui/theme/card.png", 20, 20)
define gal_ui_skin_control = Frame("gui/theme/control.png", 20, 20)
define gal_ui_skin_hover = Frame("gui/theme/hover.png", 20, 20)
define gal_ui_skin_selected = Frame("gui/theme/selected.png", 20, 20)
define gal_ui_skin_selected_hover = Frame("gui/theme/selected_hover.png", 20, 20)
define gal_ui_skin_disabled = Frame("gui/theme/disabled.png", 20, 20)
define gal_ui_skin_primary = Frame("gui/theme/primary.png", 20, 20)
define gal_ui_skin_primary_hover = Frame("gui/theme/primary_hover.png", 20, 20)
define gal_ui_skin_danger = Frame("gui/theme/danger.png", 20, 20)
define gal_ui_skin_danger_hover = Frame("gui/theme/danger_hover.png", 20, 20)
define gal_ui_skin_input = Frame("gui/theme/input.png", 20, 20)
define gal_ui_skin_input_focus = Frame("gui/theme/input_focus.png", 20, 20)
define gal_ui_skin_toast = Frame("gui/theme/toast.png", 20, 20)
define gal_ui_thumb = Transform(Solid(gal_ui_accent), xysize=(18, 18))

style gal_ui_button is button:
    yminimum 44
    padding (14, 7)
    idle_background gal_ui_skin_control
    hover_background gal_ui_skin_hover
    selected_idle_background gal_ui_skin_selected
    selected_hover_background gal_ui_skin_selected_hover
    insensitive_background gal_ui_skin_disabled

style gal_ui_button_text is button_text:
    size 18
    color gal_ui_ink
    selected_color gal_ui_accent
    insensitive_color gal_ui_disabled

style gal_ui_primary is gal_ui_button:
    idle_background gal_ui_skin_primary
    hover_background gal_ui_skin_primary_hover
    selected_idle_background gal_ui_skin_primary
    selected_hover_background gal_ui_skin_primary_hover

style gal_ui_primary_text is gal_ui_button_text:
    color "#ffffff"
    insensitive_color gal_ui_disabled

style gal_ui_danger is gal_ui_primary:
    idle_background gal_ui_skin_danger
    hover_background gal_ui_skin_danger_hover

style gal_ui_danger_text is gal_ui_primary_text

style gal_ui_icon is gal_ui_button:
    xysize (44, 44)
    padding (0, 0)

style gal_ui_slider is slider:
    ysize 44
    left_bar Solid(gal_ui_accent, ysize=6, yalign=0.5)
    right_bar Solid(gal_ui_divider, ysize=6, yalign=0.5)
    thumb gal_ui_thumb
    hover_thumb Transform(Solid(gal_ui_ink), xysize=(18, 18))
    thumb_offset 9
    bar_vertical False

style gal_ui_scroll is vscrollbar:
    xsize 16
    base_bar Solid(gal_ui_divider, xsize=8, xalign=0.5)
    thumb Solid(gal_ui_border, xsize=8, xalign=0.5)
    hover_thumb Solid(gal_ui_accent, xsize=8, xalign=0.5)

style gal_ui_dialog is empty:
    align (0.5, 0.5)
    padding (28, 24)
    background gal_ui_skin_panel

transform gal_ui_still:
    alpha 1.0

transform gal_ui_enter:
    alpha 0.0
    ease 0.14 alpha 1.0

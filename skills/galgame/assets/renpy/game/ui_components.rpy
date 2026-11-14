# Components receive actions from the owning screen.
screen gal_ui_confirm_body(message, accept, cancel, danger=False):
    add Solid(gal_ui_wash)
    frame:
        style "gal_ui_dialog"
        at (gal_ui_enter if settings_value("GALGAME_TRANSITIONS", "1") == "1" else gal_ui_still)
        xsize 600
        vbox:
            xfill True
            spacing 20
            text message size player_text_size(20) color gal_ui_ink substitute False
            hbox:
                xalign 1.0
                spacing 8
                textbutton _("取消"):
                    style "gal_ui_button"
                    text_style "gal_ui_button_text"
                    default_focus True
                    action cancel
                textbutton _("确定"):
                    style ("gal_ui_danger" if danger else "gal_ui_primary")
                    text_style ("gal_ui_danger_text" if danger else "gal_ui_primary_text")
                    action accept

screen gal_ui_tip(message, bottom=640):
    if message:
        frame:
            xalign 0.5
            ypos bottom
            yanchor 1.0
            xmaximum 360
            background gal_ui_skin_toast
            padding (14, 8)
            text message size 14 color gal_ui_ink substitute False

screen gal_ui_progress(fraction):
    fixed:
        xysize (520, 8)
        xalign 0.5
        add Solid(gal_ui_divider) xysize (520, 8)
        if fraction > 0:
            add Solid(gal_ui_accent) xysize (min(520, max(1, int(520 * fraction))), 8)

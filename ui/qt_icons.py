"""Small button helper styles (close button hover, etc.)."""

# Column header / sidebar close button size
CLOSE_BTN_ICON = 14
CLOSE_BTN_SIZE = 20


def close_button_style(colors: dict, widget: str = 'QPushButton') -> str:
    hover = colors.get('icon_btn_hover', colors.get('panel_border', '#D0D0D0'))
    return (
        f"{widget} {{ background: transparent; border: none; padding: 0; border-radius: 3px; }}"
        f"{widget}:hover {{ background: {hover}; }}"
    )

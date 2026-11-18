"""フォントの読み込みと、耐久度ゲージ・メニューの描画を担当するファイル。

注意: 日本語フォントは今は「Windowsに入っているフォント」を探して使う仮の方式。
最終的には、ゲームに同梱したフォント(M PLUS Rounded 1c など)に切り替える予定。
"""

import pygame

import config

# Windows に入っている日本語フォントの候補(上から順に探す)
_JAPANESE_FONT_NAMES = ["meiryo", "yugothic", "yugothicui", "msgothic", "msuigothic"]

_overlay_cache = None


def _japanese_font(size):
    for name in _JAPANESE_FONT_NAMES:
        path = pygame.font.match_font(name)
        if path:
            return pygame.font.Font(path, size)
    return pygame.font.Font(None, size)   # 見つからない場合(日本語は文字化けする)


def load_fonts():
    return {
        "debug": pygame.font.Font(None, 26),   # 英数字のみ(デバッグ・操作説明用)
        "small": _japanese_font(22),
        "ui": _japanese_font(26),
        "menu": _japanese_font(34),
        "title": _japanese_font(72),
    }


def draw_durability_gauge(surface, font, hp, max_hp):
    """画面右上に「耐久度 [ゲージ] 数値」を描く。"""
    number_text = f"{hp}/{max_hp}"
    number_width = font.size(f"{max_hp}/{max_hp}")[0]
    label = font.render("耐久度", True, config.COLOR_TEXT)
    number = font.render(number_text, True, config.COLOR_TEXT)

    h = config.GAUGE_HEIGHT
    y = config.UI_MARGIN
    number_x = config.WINDOW_WIDTH - config.UI_MARGIN - number_width
    bar_x = number_x - 12 - config.GAUGE_WIDTH
    label_x = bar_x - 12 - label.get_width()

    ratio = max(0.0, min(1.0, hp / max_hp))
    if ratio > 0.5:
        color = config.COLOR_GAUGE_HIGH
    elif ratio > 0.25:
        color = config.COLOR_GAUGE_MID
    else:
        color = config.COLOR_GAUGE_LOW

    bar_rect = pygame.Rect(bar_x, y, config.GAUGE_WIDTH, h)
    pygame.draw.rect(surface, config.COLOR_GAUGE_BG, bar_rect, border_radius=8)
    fill_width = int(config.GAUGE_WIDTH * ratio)
    if fill_width > 0:
        pygame.draw.rect(surface, color, (bar_x, y, fill_width, h), border_radius=8)
    pygame.draw.rect(surface, config.COLOR_GAUGE_EDGE, bar_rect, 2, border_radius=8)

    surface.blit(label, (label_x, y + (h - label.get_height()) // 2))
    surface.blit(number, (number_x, y + (h - number.get_height()) // 2))


def draw_toast_count(surface, font, count, total):
    """ゲージの下(右上)に「トースト 取得数/総数」を描く。"""
    text = font.render(f"トースト {count}/{total}", True, config.COLOR_TEXT)
    x = config.WINDOW_WIDTH - config.UI_MARGIN - text.get_width()
    y = config.UI_MARGIN + config.GAUGE_HEIGHT + 12
    surface.blit(text, (x, y))


def draw_menu(surface, fonts, title, items, selected, message=None):
    """画面を暗くして、タイトル・メッセージ・選択式メニューを描く。選択中の項目は白く強調。"""
    global _overlay_cache
    if _overlay_cache is None:
        _overlay_cache = pygame.Surface(
            (config.WINDOW_WIDTH, config.WINDOW_HEIGHT), pygame.SRCALPHA)
        _overlay_cache.fill(config.COLOR_MENU_OVERLAY)
    surface.blit(_overlay_cache, (0, 0))

    cx = config.WINDOW_WIDTH // 2
    y = 190
    title_surf = fonts["title"].render(title, True, config.COLOR_MENU_TITLE)
    surface.blit(title_surf, title_surf.get_rect(center=(cx, y)))

    y += 75
    if message:
        message_surf = fonts["menu"].render(message, True, config.COLOR_MENU_MESSAGE)
        surface.blit(message_surf, message_surf.get_rect(center=(cx, y)))
        y += 60

    y += 20
    for i, item in enumerate(items):
        rect = pygame.Rect(0, 0, 520, 58)
        rect.center = (cx, y + i * 76)
        if i == selected:
            bg, fg = config.COLOR_MENU_SELECTED_BG, config.COLOR_MENU_SELECTED_TEXT
        else:
            bg, fg = config.COLOR_MENU_ITEM_BG, config.COLOR_MENU_ITEM_TEXT
        pygame.draw.rect(surface, bg, rect, border_radius=14)
        text = fonts["menu"].render(item, True, fg)
        surface.blit(text, text.get_rect(center=rect.center))
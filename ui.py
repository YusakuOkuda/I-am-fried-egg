"""フォントの読み込みと、耐久度ゲージ・メニューの描画を担当するファイル。

注意: 日本語フォントは今は「Windowsに入っているフォント」を探して使う仮の方式。
最終的には、ゲームに同梱したフォント(M PLUS Rounded 1c など)に切り替える予定。
"""

import pygame

import config

# Windows に入っている日本語フォントの候補(上から順に探す)
_JAPANESE_FONT_NAMES = ["meiryo", "yugothic", "yugothicui", "msgothic", "msuigothic"]

# ステージ選択画面の見た目(状態ごとの札の文字と色、未解放行の色)
STAGE_STATUS_BADGE = {
    "cleared": ("クリア済み", (80, 170, 100)),
    "available": ("挑戦可能", (80, 130, 210)),
    "locked": ("未解放", (120, 125, 135)),
}
STAGE_LOCKED_BG = (70, 74, 90)
STAGE_LOCKED_TEXT = (150, 155, 170)

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
    _draw_items(surface, fonts, items, selected, cx, y)


def _draw_items(surface, fonts, items, selected, cx, y):
    """縦に並ぶメニュー項目を描く。選択中の項目は白く強調する。"""
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


def draw_title_screen(surface, fonts, title, items, selected):
    """タイトル画面。明るい背景にゲームタイトルとメニューだけを描く(操作説明は出さない)。"""
    surface.fill(config.COLOR_BACKGROUND)
    cx = config.WINDOW_WIDTH // 2
    title_surf = fonts["title"].render(title, True, config.COLOR_TEXT)
    surface.blit(title_surf, title_surf.get_rect(center=(cx, 200)))
    _draw_items(surface, fonts, items, selected, cx, 380)


def draw_stage_select(surface, fonts, title, entries, selected, hint):
    """ステージ選択画面。entries は (ステージ名, 状態) のリスト。状態は "cleared" / "available" / "locked"。"""
    surface.fill(config.COLOR_BACKGROUND)
    cx = config.WINDOW_WIDTH // 2
    title_surf = fonts["title"].render(title, True, config.COLOR_TEXT)
    surface.blit(title_surf, title_surf.get_rect(center=(cx, 130)))

    for i, (name, status) in enumerate(entries):
        rect = pygame.Rect(0, 0, 640, 72)
        rect.center = (cx, 290 + i * 96)
        locked = status == "locked"
        if i == selected:
            bg, fg = config.COLOR_MENU_SELECTED_BG, config.COLOR_MENU_SELECTED_TEXT
        elif locked:
            bg, fg = STAGE_LOCKED_BG, STAGE_LOCKED_TEXT
        else:
            bg, fg = config.COLOR_MENU_ITEM_BG, config.COLOR_MENU_ITEM_TEXT
        pygame.draw.rect(surface, bg, rect, border_radius=16)
        if i == selected:
            pygame.draw.rect(surface, config.COLOR_MENU_ITEM_BG, rect, 3, border_radius=16)

        name_surf = fonts["menu"].render(name, True, fg)
        surface.blit(name_surf, name_surf.get_rect(midleft=(rect.x + 32, rect.centery)))

        # 状態は色付きの札(バッジ)で示す。選択中でも読めるよう、札の背景色を固定している
        badge_text, badge_color = STAGE_STATUS_BADGE[status]
        badge_surf = fonts["ui"].render(badge_text, True, (255, 255, 255))
        badge_rect = pygame.Rect(0, 0, badge_surf.get_width() + 32, badge_surf.get_height() + 10)
        badge_rect.midright = (rect.right - 24, rect.centery)
        pygame.draw.rect(surface, badge_color, badge_rect, border_radius=badge_rect.height // 2)
        surface.blit(badge_surf, badge_surf.get_rect(center=badge_rect.center))

    hint_surf = fonts["ui"].render(hint, True, config.COLOR_TEXT)
    surface.blit(hint_surf, hint_surf.get_rect(center=(cx, config.WINDOW_HEIGHT - 60)))
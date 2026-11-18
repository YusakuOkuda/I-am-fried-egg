"""デバッグ表示とログ出力を担当するファイル。

■ デバッグ表示: F3 キーで表示・非表示を切り替える(通常プレイでは非表示)。
■ ログ出力: 重要なイベント(起動・ステージ開始・ダメージ・トースト取得・チェックポイント・
  ゲームオーバー・再開・クリア・セーブ・エラーなど)をファイルに記録する。毎フレームは記録しない。

ログファイルの場所(Windows): %LOCALAPPDATA%\\LostEgg2D\\logs\\game.log
  (大きくなりすぎないよう、約0.5MBで自動的に古いものへ回して、最大4ファイルまで残す)
  記録する細かさは、環境変数 LOST_EGG_LOG_LEVEL で変えられる(DEBUG / INFO / WARNING。初期値は INFO)。
"""

import logging
import logging.handlers
import math
import os
import sys
from pathlib import Path

import pygame

import config
from save_manager import get_save_dir

LOG_FILE_NAME = "game.log"
LOG_MAX_BYTES = 512 * 1024
LOG_BACKUP_COUNT = 3

logger = logging.getLogger("lost_egg")


# ======================================================================
# ログ出力
# ======================================================================
def get_log_dir():
    """ログファイルを置くフォルダを返す(セーブデータと同じ場所の logs フォルダ)。"""
    override = os.environ.get("LOST_EGG_LOG_DIR")    # テスト・開発用に場所を変えられる
    if override:
        return Path(override)
    return get_save_dir() / "logs"


def setup_logging():
    """ログの出力先を設定する。ゲーム起動時に1回だけ呼ぶ。ログファイルのパスを返す(作れなければ None)。"""
    level_name = os.environ.get("LOST_EGG_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    if not isinstance(level, int):
        level = logging.INFO
    logger.setLevel(level)
    logger.propagate = False

    if logger.handlers:                  # 2回呼ばれても、出力先が重複しないようにする
        return None

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    log_path = None
    try:
        log_dir = get_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / LOG_FILE_NAME
        file_handler = logging.handlers.RotatingFileHandler(
            log_path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError as error:             # ログが書けなくても、ゲームは起動させる
        log_path = None
        if sys.stderr is not None:
            print(f"ログファイルを作れませんでした: {error}", file=sys.stderr)

    if sys.stderr is not None:           # コンソールがあるとき(python main.py で起動したとき)は画面にも出す
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())

    sys.excepthook = _log_uncaught_exception   # 想定外のエラーもログに残す
    return log_path


def _log_uncaught_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.critical("未処理の例外でゲームが停止しました", exc_info=(exc_type, exc_value, exc_traceback))
    sys.__excepthook__(exc_type, exc_value, exc_traceback)


# ======================================================================
# デバッグ表示
# ======================================================================
_COLLISION_NAMES = {
    config.COLLISION_PLATFORM: "platform",
    config.COLLISION_SPIKE: "spike",
}


def _contact_text(egg):
    """卵がいま触れている物(接触している足場やトゲ)と、その接触面の向きを文字にする。"""
    contacts = []

    def check(arbiter):
        if len(arbiter.contact_point_set.points) == 0:
            return
        shape_a, shape_b = arbiter.shapes
        other = shape_b if shape_a is egg.shape else shape_a
        if other.sensor:
            return
        normal = arbiter.normal if shape_a is egg.shape else -arbiter.normal
        name = _COLLISION_NAMES.get(other.collision_type, "other")
        contacts.append(f"{name}(n={normal.x:.2f},{normal.y:.2f})")

    egg.body.each_arbiter(check)
    return ", ".join(contacts) if contacts else "-"


def draw_debug(surface, font, egg, steps_this_frame, fps, camera, game_state, stage):
    body = egg.body
    durability = egg.durability

    # 当たり判定(物理上の多角形)を赤線で重ねる
    pygame.draw.polygon(surface, config.COLOR_DEBUG, egg.screen_vertices(camera), 1)

    lines = [
        f"stage: {stage.number} ({stage.name})   state: {game_state}",
        f"FPS: {fps:.0f}   physics steps/frame: {steps_this_frame}",
        f"pos: ({body.position.x:.1f}, {body.position.y:.1f})",
        f"vel: ({body.velocity.x:.1f}, {body.velocity.y:.1f})",
        f"angle: {math.degrees(body.angle):.1f} deg   angvel: {body.angular_velocity:.2f}",
        f"grounded: {egg.grounded}   since_grounded: {min(egg.time_since_grounded, 9.99):.2f}s",
        f"ground normal: ({egg.ground_normal[0]:.2f}, {egg.ground_normal[1]:.2f})"
        f"   ground vel: ({egg.ground_velocity[0]:.0f}, {egg.ground_velocity[1]:.0f})",
        f"contacts: {_contact_text(egg)}",
        f"camera: ({camera.x:.1f}, {camera.y:.1f})",
        f"hp: {durability.hp}/{durability.max_hp}   invincible: {durability.invincible_timer:.2f}s",
        f"last damage: {durability.last_event}",
        f"checkpoint: {'ACTIVE' if stage.checkpoint and stage.checkpoint.active else 'inactive'}"
        f"   saved: {_saved_text(stage)}",
        f"toasts: {stage.toast_count}/{stage.toast_total}   platform time: {stage.time:.1f}s",
        "keys: F3 debug / R full reset / K hp=0 / G fall-limit test",
    ]
    y = 40
    for line in lines:
        surface.blit(font.render(line, True, config.COLOR_DEBUG), (16, y))
        y += 24


def _saved_text(stage):
    state = stage.checkpoint_state
    if state is None:
        return "-"
    return f"pos=({state['x']:.0f}, {state['y']:.0f}) hp={state['hp']} toasts={sorted(state['toasts'])} t={state['time']:.1f}"
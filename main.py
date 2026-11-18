"""ゲームの起動点。

操作:
  A / ←  : 左へ移動
  D / →  : 右へ移動
  Space  : ジャンプ
  Esc    : ポーズ(メニューでは ↑/↓ で選び、Enter で決定、Esc で戻る)
  F3     : デバッグ表示の切替

開発用(Python から起動したときだけ有効。exe版では無効。config.py の DEV_MODE):
  R      : ステージを最初からやり直す(チェックポイントも解除)
  K      : 耐久度を0にする(ゲームオーバーの確認)
  G      : 卵を落下限界の下へ移す(落下ゲームオーバーの確認)

起動方法:
  python main.py     : タイトル画面から
  python main.py 2   : ステージ2から(開発用。タイトルを飛ばす。0 はテストステージ)
"""

import logging
import sys

import pygame
import pymunk

import config
from debug import setup_logging
from game_manager import Game
from stage import STAGE_DATA


def parse_start_stage(logger):
    """開発用: python main.py 2 のようにステージ番号を指定されたら、その番号を返す。exe版では使えない。"""
    if not config.DEV_MODE or len(sys.argv) < 2:
        return None
    try:
        number = int(sys.argv[1])
    except ValueError:
        logger.warning("ステージ番号として読めないため無視します: %r", sys.argv[1])
        return None
    if number not in STAGE_DATA:
        logger.warning("存在しないステージ番号のため無視します: %d", number)
        return None
    return number


def main():
    log_path = setup_logging()
    logger = logging.getLogger("lost_egg")
    logger.info("ゲーム起動: Python %s / pygame %s / pymunk %s",
                sys.version.split()[0], pygame.version.ver, pymunk.version)
    logger.info("ログファイル: %s", log_path)
    try:
        Game(parse_start_stage(logger)).run()
    finally:
        # 想定外のエラーは debug.py の仕組みで、エラーの詳細がログに記録される
        logger.info("ゲーム終了")


if __name__ == "__main__":
    main()
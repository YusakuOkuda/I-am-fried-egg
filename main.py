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
  LAN協力プレイは現在一時停止中(起動オプションなし)
"""

import logging
import argparse
import sys

import pygame
import pymunk

import config
from debug import setup_logging
from game_manager import Game
from stage import STAGE_DATA


def parse_args(logger):
    """開発用ステージ番号を受け取る。"""
    parser = argparse.ArgumentParser(description="Lost Egg 2D")
    parser.add_argument("stage_pos", nargs="?", help="開発用ステージ番号(例: 2)")
    args = parser.parse_args()

    if args.stage_pos is None:
        start_stage = None
    elif config.DEV_MODE:
        try:
            start_stage = int(args.stage_pos)
        except ValueError:
            logger.warning("ステージ番号として読めないため無視します: %r", args.stage_pos)
            start_stage = None
    else:
        start_stage = None
    if start_stage not in STAGE_DATA:
        if start_stage is not None:
            logger.warning("存在しないステージ番号のため無視します: %d", start_stage)
        start_stage = None
    return args, start_stage


def main():
    log_path = setup_logging()
    logger = logging.getLogger("lost_egg")
    logger.info("ゲーム起動: Python %s / pygame %s / pymunk %s",
                sys.version.split()[0], pygame.version.ver, pymunk.version)
    logger.info("ログファイル: %s", log_path)
    try:
        _, start_stage = parse_args(logger)
        Game(start_stage).run()
    finally:
        # 想定外のエラーは debug.py の仕組みで、エラーの詳細がログに記録される
        logger.info("ゲーム終了")


if __name__ == "__main__":
    main()

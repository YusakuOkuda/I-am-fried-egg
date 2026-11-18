"""ゲームの起動点。

操作:
  A / ←  : 左へ移動
  D / →  : 右へ移動
  Space  : ジャンプ
  Esc    : ポーズ(メニューでは ↑/↓ で選び、Enter で決定、Esc で戻る)
  F3     : デバッグ表示の切替
  R      : ステージを最初からやり直す(開発用。チェックポイントも解除)
  K      : 耐久度を0にする(開発用。ゲームオーバーの確認)
  G      : 卵を落下限界の下へ移す(開発用。落下ゲームオーバーの確認)

起動方法:
  python main.py     : タイトル画面から
  python main.py 2   : ステージ2から(開発用。タイトルを飛ばす。0 はテストステージ)
"""

import sys

from game_manager import Game


def main():
    start_stage = int(sys.argv[1]) if len(sys.argv) > 1 else None
    Game(start_stage).run()


if __name__ == "__main__":
    main()
"""ステージデータを書きやすくするための補助関数。

足場はすべて「頂点のリスト」で表す。
座標系は Pygame と同じ (左上が原点、Y軸は下向きが正)。
足場は凸多角形(へこみのない形)にすること。
"""


def rect(x, y, w, h):
    """左上 (x, y)、幅 w、高さ h の四角形の頂点を返す。"""
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def slope_up_right(x, base_y, w, h):
    """右上がりの傾斜(三角形)。
    左下 (x, base_y) から、右端 (x+w, base_y-h) まで上がる。
    """
    return [(x, base_y), (x + w, base_y - h), (x + w, base_y)]


def slope_down_right(x, base_y, w, h):
    """右下がりの傾斜(三角形)。
    左端 (x, base_y-h) から、右下 (x+w, base_y) まで下がる。
    """
    return [(x, base_y - h), (x + w, base_y), (x, base_y)]


def spikes(x, base_y, count, width=30, height=34):
    """左端 x、足元の高さ base_y に、トゲ(三角形)を count 個、横に並べる。三角形のリストを返す。"""
    return [
        [(x + i * width, base_y),
         (x + i * width + width / 2, base_y - height),
         (x + (i + 1) * width, base_y)]
        for i in range(count)
    ]


def moving_platform(x, y, w, h, direction, distance, speed, pingpong=True, phase=0.0):
    """動く足場の設定を作る。

    (x, y, w, h): 開始位置での左上と大きさ
    direction   : 動く向き (1, 0)=右 / (-1, 0)=左 / (0, 1)=下 / (0, -1)=上
    distance    : 動く距離(px)
    speed       : 速さ(px/秒)
    pingpong    : True なら往復、False なら端まで行って止まる
    phase       : 動き始めを何秒ずらすか
    """
    return {
        "rect": (x, y, w, h),
        "direction": direction,
        "distance": distance,
        "speed": speed,
        "pingpong": pingpong,
        "phase": phase,
    }
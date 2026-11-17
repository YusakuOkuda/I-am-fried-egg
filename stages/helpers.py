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
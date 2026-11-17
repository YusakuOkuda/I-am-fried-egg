"""物理空間(Pymunk の Space)と足場の生成を担当するファイル。

物理世界の座標系は Pygame と同じ(Y下向きが正)で統一している。
そのため座標変換は不要。
"""

import pymunk

import config


def create_space():
    space = pymunk.Space()
    space.gravity = (0, config.GRAVITY)
    return space


def add_platforms(space, platforms):
    """足場(頂点リストのリスト)を静的ボディとして追加し、形状のリストを返す。

    静的ボディ = 動かない物体。各足場は凸多角形でなければならない。
    """
    shapes = []
    for vertices in platforms:
        shape = pymunk.Poly(space.static_body, vertices)
        shape.friction = config.PLATFORM_FRICTION
        shape.elasticity = config.PLATFORM_ELASTICITY
        space.add(shape)
        shapes.append(shape)
    return shapes


def limit_speed(body, max_speed):
    """物体の速さが max_speed を超えないように抑える(すり抜け防止)。"""
    speed = body.velocity.length
    if speed > max_speed:
        body.velocity = body.velocity * (max_speed / speed)
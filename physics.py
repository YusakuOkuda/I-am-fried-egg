"""物理空間(Pymunk の Space)と足場の生成を担当するファイル。

物理世界の座標系は Pygame と同じ(Y下向きが正)で統一している。
そのため座標変換は不要。
"""

import pymunk

import config
import damage


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
        shape.collision_type = config.COLLISION_PLATFORM
        space.add(shape)
        shapes.append(shape)
    return shapes


def add_sensor(space, vertices, collision_type):
    """触れても押し返さない当たり判定(センサー)を追加し、形状を返す。トースト・チェックポイント用。"""
    shape = pymunk.Poly(space.static_body, vertices)
    shape.sensor = True
    shape.collision_type = collision_type
    space.add(shape)
    return shape


def register_item_collisions(space, on_toast, on_checkpoint):
    """卵がトースト・チェックポイントに触れた瞬間に、触れた形状を on_toast(shape) / on_checkpoint(shape) で通知する。

    ここでは通知だけ。取得や保存の処理は物理ステップの後でまとめて行う。
    """
    def toast_begin(arbiter, _space, _data):
        on_toast(arbiter.shapes[1])        # 登録した順(卵, トースト)

    def checkpoint_begin(arbiter, _space, _data):
        on_checkpoint(arbiter.shapes[1])

    space.on_collision(config.COLLISION_EGG, config.COLLISION_TOAST, begin=toast_begin)
    space.on_collision(config.COLLISION_EGG, config.COLLISION_CHECKPOINT, begin=checkpoint_begin)


def register_egg_collisions(space, on_impact):
    """卵と足場が「触れ始めた瞬間」に on_impact(kind, speed) を呼ぶように登録する。

    kind  : damage.KIND_LANDING(床と判定される面)か damage.KIND_COLLISION(それ以外)
    speed : 触れる直前の、面に向かう速さ(px/秒)。0以下(離れる向き)のときは呼ばない

    ここでは判定の結果を伝えるだけ。耐久度の変更は物理ステップの後でまとめて行う。
    (ステップの途中で物理世界を書き換えないため)
    """
    def begin(arbiter, _space, _data):
        egg_shape, _platform_shape = arbiter.shapes   # 登録した順(卵, 足場)で返る
        normal = arbiter.normal                       # 卵から足場へ向かう向き
        velocity = egg_shape.body.velocity            # このステップの重力を加える前の速度
        speed = velocity.x * normal.x + velocity.y * normal.y
        if speed <= 0.0:
            return
        if normal.y > config.GROUND_NORMAL_MIN_Y:
            kind = damage.KIND_LANDING
        else:
            kind = damage.KIND_COLLISION
        on_impact(kind, speed)

    space.on_collision(config.COLLISION_EGG, config.COLLISION_PLATFORM, begin=begin)


def limit_speed(body, max_speed):
    """物体の速さが max_speed を超えないように抑える(すり抜け防止)。"""
    speed = body.velocity.length
    if speed > max_speed:
        body.velocity = body.velocity * (max_speed / speed)
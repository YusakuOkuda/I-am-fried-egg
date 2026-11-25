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


def add_spikes(space, triangles):
    """トゲ(三角形の頂点リストのリスト)を静的ボディとして追加し、形状のリストを返す。

    トゲは「押し返す固い物体」だが、種類(collision_type)が足場と別なので、
    通常の衝突ダメージ・着地ダメージの対象にはならず、トゲ専用の固定ダメージだけになる。
    """
    shapes = []
    for vertices in triangles:
        shape = pymunk.Poly(space.static_body, vertices)
        shape.friction = config.PLATFORM_FRICTION
        shape.elasticity = config.PLATFORM_ELASTICITY
        shape.collision_type = config.COLLISION_SPIKE
        space.add(shape)
        shapes.append(shape)
    return shapes


def add_spring_pads(space, pads):
    """強く跳ねる床を物理世界に追加し、形状一覧を返す。"""
    shapes = []
    for x, y, w, h in pads:
        shape = pymunk.Poly(space.static_body, [
            (x, y), (x + w, y), (x + w, y + h), (x, y + h),
        ])
        shape.friction = 0.9
        shape.elasticity = 0.2
        shape.collision_type = config.COLLISION_SPRING
        space.add(shape)
        shapes.append(shape)
    return shapes


def register_spring_collisions(space, on_spring):
    """卵が上からバネ床へ着地したとき、反発を強めるイベントを記録する。"""
    def begin(arbiter, _space, _data):
        egg_shape = next(shape for shape in arbiter.shapes
                         if shape.collision_type == config.COLLISION_EGG)
        normal = arbiter.normal if arbiter.shapes[0] is egg_shape else -arbiter.normal
        if egg_shape.body.velocity.y > 0 and normal.y > config.GROUND_NORMAL_MIN_Y:
            on_spring()

    space.on_collision(config.COLLISION_EGG, config.COLLISION_SPRING, begin=begin)


def register_spike_collisions(space, on_spike):
    """卵がトゲに触れている間、物理ステップごとに on_spike() を呼ぶ。

    触れ続けている間も呼ばれるので、無敵時間が終わるとまたダメージが入る。
    ダメージを与えるかどうかの判断(無敵時間)は耐久度側で行う。
    """
    def pre_solve(_arbiter, _space, _data):
        on_spike()

    space.on_collision(config.COLLISION_EGG, config.COLLISION_SPIKE, pre_solve=pre_solve)


def add_sensor(space, vertices, collision_type):
    """触れても押し返さない当たり判定(センサー)を追加し、形状を返す。トースト・チェックポイント用。"""
    shape = pymunk.Poly(space.static_body, vertices)
    shape.sensor = True
    shape.collision_type = collision_type
    space.add(shape)
    return shape


def register_item_collisions(space, on_toast, on_checkpoint, on_goal):
    """卵がトースト・チェックポイント・ゴールに触れた瞬間に、on_toast(shape) / on_checkpoint(shape) / on_goal(shape) で通知する。

    ここでは通知だけ。取得や保存の処理は物理ステップの後でまとめて行う。
    """
    def toast_begin(arbiter, _space, _data):
        on_toast(arbiter.shapes[1])        # 登録した順(卵, トースト)

    def checkpoint_begin(arbiter, _space, _data):
        on_checkpoint(arbiter.shapes[1])

    def goal_begin(arbiter, _space, _data):
        on_goal(arbiter.shapes[1])

    space.on_collision(config.COLLISION_EGG, config.COLLISION_TOAST, begin=toast_begin)
    space.on_collision(config.COLLISION_EGG, config.COLLISION_CHECKPOINT, begin=checkpoint_begin)
    space.on_collision(config.COLLISION_EGG, config.COLLISION_GOAL, begin=goal_begin)


def register_egg_collisions(space, on_impact):
    """卵と足場が「触れ始めた瞬間」に on_impact(kind, speed) を呼ぶように登録する。

    kind  : damage.KIND_LANDING(床と判定される面)か damage.KIND_COLLISION(それ以外)
    speed : 触れる直前の、面に向かう速さ(px/秒。動く足場は相対速度)。0以下(離れる向き)のときは呼ばない

    ここでは判定の結果を伝えるだけ。耐久度の変更は物理ステップの後でまとめて行う。
    (ステップの途中で物理世界を書き換えないため)
    """
    def begin(arbiter, _space, _data):
        egg_shape, platform_shape = arbiter.shapes    # 登録した順(卵, 足場)で返る
        normal = arbiter.normal                       # 卵から足場へ向かう向き
        # 足場が動いていても正しく測れるように、足場から見た卵の速度(相対速度)を使う
        egg_velocity = egg_shape.body.velocity        # このステップの重力を加える前の速度
        platform_velocity = platform_shape.body.velocity
        relative_x = egg_velocity.x - platform_velocity.x
        relative_y = egg_velocity.y - platform_velocity.y
        speed = relative_x * normal.x + relative_y * normal.y
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

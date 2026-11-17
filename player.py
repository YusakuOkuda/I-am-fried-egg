"""卵の形状・物理ボディ・操作・描画を担当するファイル。

卵の形は凸多角形で表し、描画と当たり判定に同じ頂点を使う。
回転は物理演算の結果(body.angle)をそのまま描画に使う。
"""

import math

import pygame
import pymunk

import config


def make_egg_vertices(width, height, points, taper):
    """卵型の頂点リストを作る(卵の中心が原点、上が細く下が太い)。"""
    vertices = []
    for i in range(points):
        t = 2 * math.pi * i / points
        x = (width / 2) * math.cos(t) * (1 - taper * math.sin(t))
        y = -(height / 2) * math.sin(t)
        vertices.append((x, y))
    vertices.reverse()
    return vertices


class Egg:
    def __init__(self, space, x, y):
        self.space = space
        self.local_vertices = make_egg_vertices(
            config.EGG_WIDTH, config.EGG_HEIGHT,
            config.EGG_POLY_POINTS, config.EGG_TAPER,
        )

        # 重心は少し下にずらす。慣性モーメントも重心基準で計算する
        cog = (0, config.EGG_COG_OFFSET_Y)
        moment = pymunk.moment_for_poly(
            config.EGG_MASS, self.local_vertices, offset=(-cog[0], -cog[1])
        )
        self.body = pymunk.Body(config.EGG_MASS, moment)
        self.body.center_of_gravity = cog
        self.body.position = (x, y)

        self.shape = pymunk.Poly(self.body, self.local_vertices)
        self.shape.friction = config.EGG_FRICTION
        self.shape.elasticity = config.EGG_ELASTICITY
        space.add(self.body, self.shape)

        # 接地関連の状態
        self.grounded = False
        self.time_since_grounded = 999.0
        self.jump_lockout = 0.0
        self.ground_normal = (0.0, 0.0)

    # ---------- 状態リセット(開発用。段階6の再開処理でも使う) ----------
    def reset(self, x, y):
        self.body.position = (x, y)
        self.body.angle = 0.0
        self.body.velocity = (0, 0)
        self.body.angular_velocity = 0.0
        self.grounded = False
        self.time_since_grounded = 999.0
        self.jump_lockout = 0.0

    # ---------- 1ステップ前の操作処理 ----------
    def apply_controls(self, move_dir, jump_pressed, dt):
        """move_dir: -1(左) / 0 / +1(右)。jump_pressed: このステップでジャンプ要求があるか。"""
        body = self.body
        self.jump_lockout = max(0.0, self.jump_lockout - dt)

        # --- ジャンプ(固定高さ:上向き速度を一定値にする) ---
        can_jump = self.time_since_grounded <= config.COYOTE_TIME and self.jump_lockout <= 0.0
        if jump_pressed and can_jump:
            body.velocity = (body.velocity.x, -config.JUMP_SPEED)
            self.jump_lockout = config.JUMP_LOCKOUT
            self.time_since_grounded = 999.0  # 猶予を使い切る(二段ジャンプ防止)
            self.grounded = False

        # --- 左右移動 ---
        ratio = 1.0 if self.grounded else config.AIR_CONTROL_RATIO
        if move_dir != 0:
            # 横方向の力(最高速度に達していたら加えない)
            if body.velocity.x * move_dir < config.MAX_MOVE_SPEED:
                force = config.EGG_MASS * config.MOVE_ACCEL * ratio * move_dir
                body.apply_force_at_world_point((force, 0), body.position)
            # 転がすトルク(Y下向き座標では、正の角度が右回り=右へ転がる向き)
            if body.angular_velocity * move_dir < config.MAX_ANGULAR_SPEED:
                body.torque = body.moment * config.MOVE_TORQUE_ACCEL * ratio * move_dir
        elif self.grounded:
            # 入力なし・接地中:回転をわずかに減衰(慣性は残す)
            body.angular_velocity *= max(0.0, 1.0 - config.ROLL_DAMPING * dt)

    # ---------- 1ステップ後の接地判定 ----------
    def update_ground_state(self, dt):
        """物理ステップ後に、接触情報(法線)から接地を判定する。"""
        self.grounded = False
        self.ground_normal = (0.0, 0.0)
        self.body.each_arbiter(self._check_arbiter)

        if self.grounded and self.jump_lockout <= 0.0:
            self.time_since_grounded = 0.0
        else:
            self.time_since_grounded += dt
            if self.jump_lockout > 0.0:
                self.grounded = False

    def _check_arbiter(self, arbiter):
        if len(arbiter.contact_point_set.points) == 0:
            return
        normal = arbiter.normal  # shapes[0] から shapes[1] へ向かう法線
        if arbiter.shapes[0] is not self.shape:
            normal = -normal      # 卵から相手へ向かう向きに揃える
        # 卵から見て「下向き(Yプラス)」に近い面なら床
        if normal.y > config.GROUND_NORMAL_MIN_Y:
            self.grounded = True
            self.ground_normal = (normal.x, normal.y)

    # ---------- 描画 ----------
    def world_vertices(self):
        """ワールド座標(ステージ上の座標)での頂点リスト。"""
        return [self.body.local_to_world(v) for v in self.local_vertices]

    def screen_vertices(self, camera):
        """カメラを反映した、画面上の頂点リスト。"""
        return [camera.apply(p) for p in self.world_vertices()]

    def draw(self, surface, camera):
        points = self.screen_vertices(camera)
        pygame.draw.polygon(surface, config.COLOR_EGG, points)
        pygame.draw.polygon(surface, config.COLOR_EGG_EDGE, points, 2)
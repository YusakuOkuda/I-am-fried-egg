"""卵の形状・物理ボディ・操作・耐久度・描画を担当するファイル。

卵の形は凸多角形で表し、描画と当たり判定に同じ頂点を使う。
回転は物理演算の結果(body.angle)をそのまま描画に使う。
"""

import math

import pygame
import pymunk

import config
import damage


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
        self.shape.collision_type = config.COLLISION_EGG
        space.add(self.body, self.shape)

        # 接地関連の状態
        self.grounded = False
        self.time_since_grounded = 999.0
        self.jump_lockout = 0.0
        self.ground_normal = (0.0, 0.0)
        self.ground_velocity = (0.0, 0.0)   # 乗っている足場の速度(動く足場の上で操作を正しく効かせるため)

        # 耐久度と、物理ステップ中に集めた衝撃(ステップ後にまとめて処理する)
        self.durability = damage.Durability()
        self.damage_multiplier = 1.0
        self.pending_impacts = []
        self.touching_spike = False
        self.spring_touched = False

    # ---------- 状態リセット(開発用・ゲームオーバーからの再開用) ----------
    def reset(self, x, y, hp=None):
        """位置・速度・耐久度を戻す。hp を省略すると耐久度は開始時の値(チェックポイント再開では保存値を渡す)。"""
        self.body.position = (x, y)
        self.body.angle = 0.0
        self.body.velocity = (0, 0)
        self.body.angular_velocity = 0.0
        self.grounded = False
        self.time_since_grounded = 999.0
        self.jump_lockout = 0.0
        self.ground_velocity = (0.0, 0.0)
        self.touching_spike = False
        self.spring_touched = False
        self.durability.reset(hp)
        self.pending_impacts.clear()

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
            # 横方向の力(最高速度に達していたら加えない)。
            # 足場に乗っているときは、足場から見た速度で判定する。
            # 力は重心に加え、意図しない回転を防ぐ。
            relative_vx = body.velocity.x - self.ground_velocity[0]
            if relative_vx * move_dir < config.MAX_MOVE_SPEED:
                force = config.EGG_MASS * config.MOVE_ACCEL * ratio * move_dir
                body.apply_force_at_world_point(
                    (force, 0),
                    body.local_to_world(body.center_of_gravity)
                )
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
        self.ground_velocity = (0.0, 0.0)
        self.body.each_arbiter(self._check_arbiter)

        if self.grounded and self.jump_lockout <= 0.0:
            self.time_since_grounded = 0.0
        else:
            self.time_since_grounded += dt
            if self.jump_lockout > 0.0:
                self.grounded = False
        if not self.grounded:
            self.ground_velocity = (0.0, 0.0)   # 空中では足場の速度を基準にしない(速度はそのまま引き継ぐ)

    def _check_arbiter(self, arbiter):
        if len(arbiter.contact_point_set.points) == 0:
            return
        shape_a, shape_b = arbiter.shapes
        other = shape_b if shape_a is self.shape else shape_a
        if other.sensor:
            return                # トーストなどのセンサーは足場ではない
        normal = arbiter.normal  # shapes[0] から shapes[1] へ向かう法線
        if shape_a is not self.shape:
            normal = -normal      # 卵から相手へ向かう向きに揃える
        # 卵から見て「下向き(Yプラス)」に近い面なら床
        if normal.y > config.GROUND_NORMAL_MIN_Y:
            self.grounded = True
            self.ground_normal = (normal.x, normal.y)
            ground_velocity = other.body.velocity
            self.ground_velocity = (ground_velocity.x, ground_velocity.y)

    # ---------- 1ステップ後のダメージ処理 ----------
    def add_impact(self, kind, speed):
        """衝突コールバックから呼ばれる。ここでは記録だけして、処理は update_damage で行う。"""
        self.pending_impacts.append((kind, speed))

    def add_spike_touch(self):
        """トゲとの接触コールバックから呼ばれる。記録だけして、処理は update_damage で行う。"""
        self.touching_spike = True

    def add_spring_touch(self):
        """バネ床の着地を物理ステップ後に処理するため記録する。"""
        self.spring_touched = True

    def update_spring(self):
        if self.spring_touched:
            self.spring_touched = False
            self.body.velocity = (self.body.velocity.x, min(self.body.velocity.y, -820.0))
            self.jump_lockout = config.JUMP_LOCKOUT
            self.time_since_grounded = 999.0
            self.grounded = False

    def update_damage(self, dt):
        """タイマーを進め、このステップのダメージを処理する。

        1. トゲ(固定ダメージ)。無敵中でなければダメージ。ダメージを受けたステップの衝撃は無視する。
        2. 衝撃(着地・衝突)。同じステップに複数あっても、いちばん大きい1つだけを採用する。
        どちらも無敵時間中は追加ダメージを受けない(二重計算の防止)。
        """
        self.durability.update(dt)

        if self.touching_spike:
            self.touching_spike = False
            if not self.durability.is_invincible:
                spike_damage = max(1, round(config.SPIKE_DAMAGE * self.damage_multiplier))
                self.durability.take_damage(
                    damage.KIND_SPIKE, 0.0, spike_damage, config.SPIKE_INVINCIBLE_TIME)
                self.pending_impacts.clear()   # トゲと同時の衝撃は数えない
                return

        if not self.pending_impacts:
            return
        impacts = self.pending_impacts
        self.pending_impacts = []

        kind, speed = max(impacts, key=lambda item: damage.impact_damage(item[0], item[1]))
        amount = damage.impact_damage(kind, speed)
        if amount > 0:
            amount = max(1, round(amount * self.damage_multiplier))
        self.durability.take_damage(kind, speed, amount, config.IMPACT_INVINCIBLE_TIME)

    # ---------- 描画 ----------
    def world_vertices(self):
        """ワールド座標(ステージ上の座標)での頂点リスト。"""
        return [self.body.local_to_world(v) for v in self.local_vertices]

    def screen_vertices(self, camera):
        """カメラを反映した、画面上の頂点リスト。"""
        return [camera.apply(p) for p in self.world_vertices()]

    def draw(self, surface, camera, fried_ratio=0.0, fried_position=None):
        """卵を描き、ゴール演出中はだんだん目玉焼きへ変える。"""
        ratio = max(0.0, min(1.0, fried_ratio))
        if ratio <= 0.0:
            self._draw_egg(surface, camera)
            return

        egg_layer = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        self._draw_egg(egg_layer, camera)
        egg_layer.set_alpha(round(255 * (1.0 - ratio)))
        surface.blit(egg_layer, (0, 0))

        transform_position = fried_position or self.body.position
        cx, cy = camera.apply(transform_position)
        ease = ratio * ratio * (3.0 - 2.0 * ratio)
        width, height = round(42 + 18 * ease), round(24 + 14 * ease)
        white = pygame.Rect(0, 0, width, height)
        white.center = (round(cx), round(cy + 8 * ease))
        pygame.draw.ellipse(surface, (255, 250, 226), white)
        pygame.draw.ellipse(surface, (210, 162, 91), white, 2)
        yolk_radius = round(1 + 13 * ease)
        yolk_center = (white.centerx, white.centery - 1)
        pygame.draw.circle(surface, (241, 163, 47), yolk_center, yolk_radius + 2)
        pygame.draw.circle(surface, (255, 202, 76), yolk_center, yolk_radius)
        if yolk_radius > 5:
            pygame.draw.circle(surface, (255, 224, 127),
                               (yolk_center[0] - yolk_radius // 3,
                                yolk_center[1] - yolk_radius // 3), max(2, yolk_radius // 4))

    def _draw_egg(self, surface, camera):
        points = self.screen_vertices(camera)
        left = int(min(point[0] for point in points))
        right = int(max(point[0] for point in points))
        top = int(min(point[1] for point in points))
        bottom = int(max(point[1] for point in points))
        center_x = (left + right) // 2
        # Contact shadow makes the egg feel grounded without changing physics.
        pygame.draw.ellipse(surface, (145, 155, 151),
                            (center_x - 17, bottom - 5, 34, 10))
        color = config.COLOR_EGG_DAMAGE if self.durability.flash_on else config.COLOR_EGG
        pygame.draw.polygon(surface, color, points)
        pygame.draw.polygon(surface, (185, 157, 119), points, 2)
        if not self.durability.flash_on:
            pygame.draw.ellipse(surface, (255, 255, 255),
                                (left + 11, top + 13, 8, 17))
            pygame.draw.ellipse(surface, (255, 255, 255),
                                (left + 21, top + 24, 4, 7))

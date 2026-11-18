"""動く足場を担当するファイル。

動く足場は「キネマティックボディ」(力は受けず、決めた速度で動く物体)で作る。
位置は「経過時間」から計算で求め、毎ステップ、その位置へ着くための速度を設定する。
卵が乗っているときの連れ回しは、物理演算(摩擦)に任せる。
卵の速度を手動で足さないので、速度の二重加算が起きず、卵の転がりや慣性も保たれる。
足場から離れたときも、物理演算が持っている速度がそのまま引き継がれる。
"""

import math

import pygame
import pymunk

import config


class MovingPlatform:
    def __init__(self, space, spec):
        """spec はステージデータの動く足場の設定(stages/helpers.py の moving_platform が作る辞書)。"""
        x, y, w, h = spec["rect"]
        dx, dy = spec["direction"]
        length = math.hypot(dx, dy)
        self.direction = (dx / length, dy / length)   # 移動方向(長さ1にそろえる)
        self.distance = spec["distance"]              # 移動範囲(px)
        self.speed = spec["speed"]                    # 移動速度(px/秒)
        self.pingpong = spec.get("pingpong", True)    # True: 往復する / False: 端まで行って止まる
        self.phase = spec.get("phase", 0.0)           # 動き始めのずらし(秒)。複数の足場の位相をずらす用
        self.start = (x + w / 2, y + h / 2)           # 開始位置(足場の中心)

        self.body = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
        self.body.position = self.position_at(0.0)
        half_w, half_h = w / 2, h / 2
        self.shape = pymunk.Poly(
            self.body, [(-half_w, -half_h), (half_w, -half_h), (half_w, half_h), (-half_w, half_h)])
        self.shape.friction = config.PLATFORM_FRICTION
        self.shape.elasticity = config.PLATFORM_ELASTICITY
        self.shape.collision_type = config.COLLISION_PLATFORM
        space.add(self.body, self.shape)

    def offset_at(self, t):
        """時刻 t(秒)での、開始位置からの移動量(px)。"""
        if self.distance <= 0:
            return 0.0
        travel = self.speed * (t + self.phase)
        if not self.pingpong:
            return min(travel, self.distance)
        cycle = 2 * self.distance
        m = travel % cycle
        return m if m <= self.distance else cycle - m

    def position_at(self, t):
        offset = self.offset_at(t)
        return (self.start[0] + self.direction[0] * offset,
                self.start[1] + self.direction[1] * offset)

    def prepare_step(self, t, dt):
        """物理ステップの直前に呼ぶ。dt 後に位置 position_at(t + dt) へ着くよう、速度を設定する。"""
        target_x, target_y = self.position_at(t + dt)
        self.body.velocity = ((target_x - self.body.position.x) / dt,
                              (target_y - self.body.position.y) / dt)

    def snap_to_time(self, t):
        """時刻 t の位置へ即座に移す(チェックポイント復元・やり直し用)。"""
        self.body.position = self.position_at(t)
        self.body.velocity = (0, 0)

    def draw(self, surface, camera):
        points = [camera.apply(self.body.local_to_world(v)) for v in self.shape.get_vertices()]
        pygame.draw.polygon(surface, config.COLOR_MOVING_PLATFORM, points)
        pygame.draw.polygon(surface, config.COLOR_MOVING_PLATFORM_EDGE, points, 3)
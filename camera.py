"""カメラを担当するファイル。

カメラの位置 (x, y) は「画面の左上に映るステージ上の座標」。
ワールド座標(ステージ上の座標)から画面座標へは、位置を引き算して変換する。
"""

import math

import config


class Camera:
    def __init__(self, stage_width, stage_height):
        self.stage_width = stage_width
        self.stage_height = stage_height
        self.x = 0.0
        self.y = 0.0

    def _clamp(self):
        """ステージの外が映らないように位置を制限する。"""
        max_x = max(0.0, self.stage_width - config.WINDOW_WIDTH)
        max_y = max(0.0, self.stage_height - config.WINDOW_HEIGHT)
        self.x = min(max(self.x, 0.0), max_x)
        self.y = min(max(self.y, 0.0), max_y)

    def snap_to(self, target_x, target_y):
        """追従せず、一瞬でその位置に合わせる(開始・再開・リセット用)。"""
        self.x = target_x - config.WINDOW_WIDTH / 2
        self.y = target_y - config.CAMERA_ANCHOR_Y
        self._clamp()

    def update(self, target_x, target_y, velocity_x, velocity_y, dt):
        """卵の位置と速度から、カメラを滑らかに動かす。"""
        # --- 横方向:卵が進む向きを少し先読みして追従 ---
        goal_x = target_x - config.WINDOW_WIDTH / 2 + velocity_x * config.CAMERA_LOOKAHEAD_X

        # --- 縦方向:デッドゾーン内の動きでは追従しない ---
        goal_y = target_y - config.CAMERA_ANCHOR_Y
        diff = goal_y - self.y
        if abs(diff) <= config.CAMERA_DEADZONE_Y:
            goal_y = self.y
        else:
            sign = 1.0 if diff > 0 else -1.0
            goal_y -= sign * config.CAMERA_DEADZONE_Y

        # --- 落下中は下を先読みする ---
        if velocity_y > config.CAMERA_FALL_LOOKAHEAD_START:
            extra = (velocity_y - config.CAMERA_FALL_LOOKAHEAD_START) * config.CAMERA_FALL_LOOKAHEAD
            goal_y += min(extra, config.CAMERA_FALL_LOOKAHEAD_MAX)

        # --- 滑らかに近づける(指数補間。フレーム時間が変わっても速さが同じ) ---
        alpha_x = 1.0 - math.exp(-config.CAMERA_SMOOTH_X * dt)
        alpha_y = 1.0 - math.exp(-config.CAMERA_SMOOTH_Y * dt)
        self.x += (goal_x - self.x) * alpha_x
        self.y += (goal_y - self.y) * alpha_y
        self._clamp()

    def apply(self, point):
        """ワールド座標 (x, y) を画面座標に変換する。"""
        return (point[0] - self.x, point[1] - self.y)
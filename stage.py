"""ステージデータの読み込み、物理空間への登録、描画、トースト・チェックポイント・ゴールの管理を担当するファイル。"""

import pygame

import config
import physics
from moving_platform import MovingPlatform
from stages import stage1, stage2, stage3, test_stage
from stages.helpers import rect

# ステージ番号とデータの対応
# 0 は開発用のテストステージ(動く足場・トゲの確認用)。python main.py 0 で起動する
STAGE_DATA = {
    0: test_stage.STAGE,
    1: stage1.STAGE,
    2: stage2.STAGE,
    3: stage3.STAGE,
}


class Toast:
    def __init__(self, index, x, y, shape):
        self.index = index      # ステージ内の通し番号(チェックポイントの保存に使う)
        self.x = x
        self.y = y
        self.shape = shape
        self.collected = False


class Checkpoint:
    def __init__(self, x, base_y, shape):
        self.x = x
        self.base_y = base_y    # ポールの足元の高さ
        self.shape = shape
        self.active = False


class Goal:
    def __init__(self, x, base_y, shape):
        self.x = x
        self.base_y = base_y    # フライパンの底の高さ
        self.shape = shape


class Stage:
    def __init__(self, space, number):
        data = STAGE_DATA[number]
        self.number = number
        self.name = data["name"]
        self.width = data["width"]
        self.height = data["height"]
        self.egg_start = data["egg_start"]
        self.fall_limit = data["fall_limit"]
        self.shapes = physics.add_platforms(space, data["platforms"])

        # --- 動く足場・トゲ ---
        self.moving_platforms = [MovingPlatform(space, spec) for spec in data.get("moving_platforms", [])]
        self.spike_shapes = physics.add_spikes(space, data.get("spikes", []))
        self.time = 0.0                # 動く足場の時計(秒)。物理ステップを進めたときだけ進む

        # --- トースト ---
        self.toasts = []
        self._toast_by_shape = {}
        half = config.TOAST_SIZE / 2
        for index, (x, y) in enumerate(data.get("toasts", [])):
            shape = physics.add_sensor(
                space, rect(x - half, y - half, config.TOAST_SIZE, config.TOAST_SIZE),
                config.COLLISION_TOAST)
            toast = Toast(index, x, y, shape)
            self.toasts.append(toast)
            self._toast_by_shape[shape] = toast

        # --- チェックポイント(各ステージに1か所) ---
        self.checkpoint = None
        if "checkpoint" in data:
            x, base_y = data["checkpoint"]
            shape = physics.add_sensor(
                space,
                rect(x - config.CHECKPOINT_WIDTH / 2, base_y - config.CHECKPOINT_POLE_HEIGHT,
                     config.CHECKPOINT_WIDTH, config.CHECKPOINT_POLE_HEIGHT),
                config.COLLISION_CHECKPOINT)
            self.checkpoint = Checkpoint(x, base_y, shape)

        # --- ゴール(フライパン) ---
        self.goal = None
        if "goal" in data:
            x, base_y = data["goal"]
            shape = physics.add_sensor(
                space,
                rect(x - config.GOAL_WIDTH / 2, base_y - config.GOAL_HEIGHT,
                     config.GOAL_WIDTH, config.GOAL_HEIGHT),
                config.COLLISION_GOAL)
            self.goal = Goal(x, base_y, shape)
        self.cleared = False           # ゴールに到達したか

        self.checkpoint_state = None   # チェックポイントで保存した状態(メモリ上のみ)
        self.popups = []               # トースト取得表示
        self._touched_toasts = []      # 物理ステップ中に触れたものを集めておく
        self._touched_checkpoint = False
        self._touched_goal = False

    # ---------- トースト数 ----------
    @property
    def toast_count(self):
        return sum(1 for toast in self.toasts if toast.collected)

    @property
    def toast_total(self):
        return len(self.toasts)

    # ---------- 衝突コールバックから呼ばれる(記録だけ) ----------
    def on_toast_touched(self, shape):
        self._touched_toasts.append(shape)

    def on_checkpoint_touched(self, shape):
        self._touched_checkpoint = True

    def on_goal_touched(self, shape):
        self._touched_goal = True

    # ---------- 動く足場 ----------
    def prepare_physics_step(self, dt):
        """物理ステップの直前に呼ぶ。動く足場の速度を設定し、足場の時計を進める。"""
        for platform in self.moving_platforms:
            platform.prepare_step(self.time, dt)
        self.time += dt

    def _snap_platforms(self):
        for platform in self.moving_platforms:
            platform.snap_to_time(self.time)

    # ---------- 1ステップ後の処理 ----------
    def process_items(self, egg):
        """このステップで触れたトースト・チェックポイントを処理する。"""
        touched, self._touched_toasts = self._touched_toasts, []
        for shape in touched:
            toast = self._toast_by_shape.get(shape)
            if toast is None or toast.collected:
                continue                      # 取得済みは再取得できない
            toast.collected = True
            healed = egg.durability.heal(config.TOAST_HEAL)
            self.popups.append({
                "text": f"トースト +{healed}", "x": toast.x, "y": toast.y,
                "timer": config.TOAST_POPUP_TIME,
            })

        touched_checkpoint, self._touched_checkpoint = self._touched_checkpoint, False
        if (touched_checkpoint and self.checkpoint is not None
                and not self.checkpoint.active and not egg.durability.is_broken):
            self.checkpoint.active = True
            self._save_checkpoint(egg)

        touched_goal, self._touched_goal = self._touched_goal, False
        if touched_goal and self.goal is not None and not egg.durability.is_broken:
            self.cleared = True

    def update(self, dt):
        """取得表示のタイマーを進める。"""
        for popup in self.popups:
            popup["timer"] -= dt
        self.popups = [p for p in self.popups if p["timer"] > 0.0]

    # ---------- チェックポイントの保存・復元 ----------
    def _save_checkpoint(self, egg):
        """卵の位置・耐久度・トーストの取得状態(と取得数)を保存する。"""
        self.checkpoint_state = {
            "x": egg.body.position.x,
            "y": egg.body.position.y,
            "hp": egg.durability.hp,
            "toasts": frozenset(t.index for t in self.toasts if t.collected),
            "time": self.time,          # 動く足場の位置(ステージ内の進行状態)
        }

    def restore_checkpoint(self):
        """保存した状態にトーストの取得状態を戻し、その状態(位置・耐久度)を返す。

        チェックポイント通過後に取得したトーストは未取得に戻る。取得数は取得状態から数えるので自動的に戻る。
        動く足場も、保存したときの位置に戻す。チェックポイントの有効状態は維持する。
        """
        state = self.checkpoint_state
        for toast in self.toasts:
            toast.collected = toast.index in state["toasts"]
        self.time = state["time"]
        self._snap_platforms()
        self._clear_transient()
        return state

    def reset_progress(self):
        """ステージの最初からやり直す(トースト・チェックポイントを初期状態に戻す)。"""
        for toast in self.toasts:
            toast.collected = False
        if self.checkpoint is not None:
            self.checkpoint.active = False
        self.checkpoint_state = None
        self.time = 0.0
        self._snap_platforms()
        self._clear_transient()

    def _clear_transient(self):
        self.popups.clear()
        self._touched_toasts.clear()
        self._touched_checkpoint = False
        self._touched_goal = False
        self.cleared = False

    # ---------- 描画 ----------
    def draw_background(self, surface, camera):
        """背景色と格子線。カメラに合わせて動くので、スクロールの確認になる。"""
        surface.fill(config.COLOR_BACKGROUND)
        size = config.GRID_SIZE
        start_x = -(int(camera.x) % size)
        start_y = -(int(camera.y) % size)
        for x in range(start_x, config.WINDOW_WIDTH, size):
            pygame.draw.line(surface, config.COLOR_GRID, (x, 0), (x, config.WINDOW_HEIGHT), 2)
        for y in range(start_y, config.WINDOW_HEIGHT, size):
            pygame.draw.line(surface, config.COLOR_GRID, (0, y), (config.WINDOW_WIDTH, y), 2)

    def draw(self, surface, camera):
        for shape in self.shapes:
            points = [camera.apply((v.x, v.y)) for v in shape.get_vertices()]
            pygame.draw.polygon(surface, config.COLOR_PLATFORM, points)
            pygame.draw.polygon(surface, config.COLOR_PLATFORM_EDGE, points, 3)
        for platform in self.moving_platforms:
            platform.draw(surface, camera)
        for shape in self.spike_shapes:
            points = [camera.apply((v.x, v.y)) for v in shape.get_vertices()]
            pygame.draw.polygon(surface, config.COLOR_SPIKE, points)
            pygame.draw.polygon(surface, config.COLOR_SPIKE_EDGE, points, 2)
        if self.checkpoint is not None:
            self._draw_checkpoint(surface, camera)
        if self.goal is not None:
            self._draw_goal(surface, camera)
        for toast in self.toasts:
            if not toast.collected:
                self._draw_toast(surface, camera, toast)

    def _draw_toast(self, surface, camera, toast):
        """トースト: 角の丸い四角に、上の2つのふくらみを付けた食パンの形。"""
        cx, cy = camera.apply((toast.x, toast.y))
        size = config.TOAST_SIZE
        body = pygame.Rect(0, 0, size, size - 6)
        body.center = (cx, cy + 3)
        pygame.draw.circle(surface, config.COLOR_TOAST, (body.left + 9, body.top + 2), 9)
        pygame.draw.circle(surface, config.COLOR_TOAST, (body.right - 9, body.top + 2), 9)
        pygame.draw.rect(surface, config.COLOR_TOAST, body, border_radius=6)
        pygame.draw.rect(surface, config.COLOR_TOAST_EDGE, body, 2, border_radius=6)
        inner = body.inflate(-12, -12)
        pygame.draw.rect(surface, config.COLOR_TOAST_INNER, inner, border_radius=4)

    def _draw_checkpoint(self, surface, camera):
        """チェックポイント: ポールと旗。通過済みなら旗の色が変わる。"""
        cp = self.checkpoint
        base_x, base_y = camera.apply((cp.x, cp.base_y))
        top_y = base_y - config.CHECKPOINT_POLE_HEIGHT
        pygame.draw.line(surface, config.COLOR_CHECKPOINT_POLE, (base_x, base_y), (base_x, top_y), 6)
        pygame.draw.circle(surface, config.COLOR_CHECKPOINT_POLE, (base_x, top_y), 6)
        flag_color = config.COLOR_FLAG_ACTIVE if cp.active else config.COLOR_FLAG_INACTIVE
        flag = [
            (base_x + 3, top_y + 4),
            (base_x + 3 + config.CHECKPOINT_FLAG_WIDTH, top_y + 4 + config.CHECKPOINT_FLAG_HEIGHT / 2),
            (base_x + 3, top_y + 4 + config.CHECKPOINT_FLAG_HEIGHT),
        ]
        pygame.draw.polygon(surface, flag_color, flag)
        pygame.draw.polygon(surface, config.COLOR_PLATFORM_EDGE, flag, 2)

    def _draw_goal(self, surface, camera):
        """ゴール: フライパン(横から見た形。本体、中の面、持ち手)。"""
        cx, base_y = camera.apply((self.goal.x, self.goal.base_y))
        handle = pygame.Rect(cx + 34, base_y - 18, 56, 10)
        pygame.draw.rect(surface, config.COLOR_PAN_HANDLE, handle, border_radius=5)
        body = pygame.Rect(cx - 42, base_y - 24, 84, 24)
        pygame.draw.rect(surface, config.COLOR_PAN, body, border_radius=10)
        inner = pygame.Rect(cx - 38, base_y - 32, 76, 16)
        pygame.draw.ellipse(surface, config.COLOR_PAN_INNER, inner)
        pygame.draw.ellipse(surface, config.COLOR_PAN, inner, 3)

    def draw_popups(self, surface, camera, font):
        """トースト取得表示(ふわっと上へ昇る文字)。"""
        for popup in self.popups:
            progress = 1.0 - popup["timer"] / config.TOAST_POPUP_TIME
            x, y = camera.apply((popup["x"], popup["y"] - config.TOAST_POPUP_RISE * progress - 30))
            text = font.render(popup["text"], True, config.COLOR_POPUP)
            surface.blit(text, text.get_rect(center=(x, y)))
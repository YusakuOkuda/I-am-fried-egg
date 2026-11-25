"""ステージデータの読み込み、物理空間への登録、描画、トースト・チェックポイント・ゴールの管理を担当するファイル。"""

import math

import pygame

import config
import physics
from moving_platform import MovingPlatform
from stages import stage1, stage2, stage3, stage4, test_stage
from stages.helpers import rect


_BACKGROUND_CACHE = {}


def _make_sky_background(top, bottom):
    """朝空のグラデーションを一度だけ作り、毎フレーム再利用する。"""
    key = (top, bottom)
    if key not in _BACKGROUND_CACHE:
        sky = pygame.Surface((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
        for y in range(config.WINDOW_HEIGHT):
            t = y / max(1, config.WINDOW_HEIGHT - 1)
            color = tuple(round(a + (b - a) * t) for a, b in zip(top, bottom))
            pygame.draw.line(sky, color, (0, y), (config.WINDOW_WIDTH, y))
        _BACKGROUND_CACHE[key] = sky
    return _BACKGROUND_CACHE[key]

# ステージ番号とデータの対応
# 0 は開発用のテストステージ(動く足場・トゲの確認用)。python main.py 0 で起動する
STAGE_DATA = {
    0: test_stage.STAGE,
    1: stage1.STAGE,
    2: stage2.STAGE,
    3: stage3.STAGE,
    4: stage4.STAGE,
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
        self.sky_colors = data.get("sky_colors", ((166, 215, 239), (255, 239, 205)))
        self.shapes = physics.add_platforms(space, data["platforms"])

        # --- 動く足場・トゲ ---
        self.moving_platforms = [MovingPlatform(space, spec) for spec in data.get("moving_platforms", [])]
        self.spike_shapes = physics.add_spikes(space, data.get("spikes", []))
        self.spring_shapes = physics.add_spring_pads(space, data.get("spring_pads", []))
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
        self.pickup_effects = []       # トースト取得時のリングと光
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
            self.pickup_effects.append({"x": toast.x, "y": toast.y, "timer": 0.7})

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
        for effect in self.pickup_effects:
            effect["timer"] -= dt
        self.pickup_effects = [e for e in self.pickup_effects if e["timer"] > 0.0]

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
        self.pickup_effects.clear()
        self._touched_toasts.clear()
        self._touched_checkpoint = False
        self._touched_goal = False
        self.cleared = False

    # ---------- 描画 ----------
    def draw_background(self, surface, camera):
        """朝空とゆっくり流れる雲で、プレイ画面に奥行きを加える。"""
        surface.blit(_make_sky_background(*self.sky_colors), (0, 0))
        period = 520
        offset = int(camera.x * 0.12) % period
        for base_x in range(-period - offset, config.WINDOW_WIDTH + period, period):
            x = base_x
            y = 148 + ((base_x // period) % 3) * 112 - int(camera.y * 0.035) % 80
            cloud = (255, 255, 255)
            pygame.draw.ellipse(surface, cloud, (x + 30, y + 18, 96, 30))
            pygame.draw.ellipse(surface, cloud, (x + 46, y, 48, 50))
            pygame.draw.ellipse(surface, cloud, (x + 75, y + 7, 58, 42))
            pygame.draw.ellipse(surface, (255, 250, 238), (x + 49, y + 35, 63, 5))

    def draw(self, surface, camera):
        for shape in self.shapes:
            points = [camera.apply((v.x, v.y)) for v in shape.get_vertices()]
            shadow = [(x + 2, y + 7) for x, y in points]
            pygame.draw.polygon(surface, (139, 157, 159), shadow)
            pygame.draw.polygon(surface, config.COLOR_PLATFORM, points)
            pygame.draw.polygon(surface, (104, 133, 119), points, 3)
        for platform in self.moving_platforms:
            platform.draw(surface, camera)
        for shape in self.spring_shapes:
            points = [camera.apply((v.x, v.y)) for v in shape.get_vertices()]
            left = round(min(p[0] for p in points))
            top = round(min(p[1] for p in points))
            right = round(max(p[0] for p in points))
            bottom = round(max(p[1] for p in points))
            pygame.draw.rect(surface, (196, 93, 104), (left, top + 6, right - left, bottom - top - 6), border_radius=5)
            pygame.draw.rect(surface, (255, 177, 117), (left, top, right - left, 11), border_radius=6)
            coil_points = []
            for i in range(7):
                coil_points.append((left + 12 + i * (right - left - 24) / 6,
                                    top + 12 if i % 2 == 0 else bottom - 2))
            pygame.draw.lines(surface, (255, 238, 186), False, coil_points, 3)
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

    def draw_pickup_effects(self, surface, camera):
        """トースト取得時に、広がるリングと小さな光を描く。"""
        for effect in self.pickup_effects:
            progress = 1.0 - effect["timer"] / 0.7
            cx, cy = camera.apply((effect["x"], effect["y"]))
            radius = int(12 + progress * 34)
            color = (255, int(224 - progress * 82), int(125 - progress * 30))
            pygame.draw.circle(surface, color, (int(cx), int(cy)), radius, 3)
            for i in range(10):
                angle = math.tau * i / 10 - math.pi / 2
                distance = 10 + progress * 42
                px = int(cx + math.cos(angle) * distance)
                py = int(cy + math.sin(angle) * distance)
                dot_radius = max(1, int(4 * (1 - progress)))
                pygame.draw.circle(surface, (255, 249, 218), (px, py), dot_radius)

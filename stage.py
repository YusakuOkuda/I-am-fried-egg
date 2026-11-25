"""ステージデータの読み込み、物理空間への登録、描画、トースト・チェックポイント・ゴールの管理を担当するファイル。"""

import math
import random

import pygame

import config
import physics
from moving_platform import MovingPlatform
from stages import stage1, stage2, stage3, stage4, stage5, test_stage
from stages.helpers import rect, spring_pad


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
    5: stage5.STAGE,
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
        self.space = space
        self.number = number
        self.name = data["name"]
        self.width = data["width"]
        self.height = data["height"]
        self.egg_start = data["egg_start"]
        self.fall_limit = data["fall_limit"]
        self.endless_climb = data.get("endless_climb", False)
        self.climb_start_y = self.egg_start[1]
        self.climb_best_y = self.egg_start[1]
        self._climb_seed = data.get("climb_seed")
        if self.endless_climb and self._climb_seed is None:
            self._climb_seed = random.SystemRandom().randrange(2 ** 32)
        if self._climb_seed is None:
            self._climb_seed = 0
        self._climb_rng = random.Random(self._climb_seed)
        self._climb_top_y = min((platform[0][1] for platform in data["platforms"]),
                                default=self.egg_start[1])
        self._climb_last_x = self.egg_start[0]
        self._climb_dynamic_shapes = []
        self.sky_colors = data.get("sky_colors", ((166, 215, 239), (255, 239, 205)))
        self.shapes = physics.add_platforms(space, data["platforms"])

        # --- 動く足場・トゲ ---
        self.moving_platforms = [MovingPlatform(space, spec) for spec in data.get("moving_platforms", [])]
        self.spike_shapes = physics.add_spikes(space, data.get("spikes", []))
        self.spring_shapes = physics.add_spring_pads(space, data.get("spring_pads", []))
        self.climb_dynamic_springs = []
        self.climb_item_shapes = {}
        self.climb_items = []
        self.climb_effects = []
        self.climb_popup = ""
        self.climb_popup_timer = 0.0
        self.climb_float_timer = 0.0
        self.climb_item_touched = []
        self.climb_fragile = {}
        self.climb_moving_platforms = []
        self._climb_fragile_touches = set()
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
        self._touched_checkpoint_player = None
        self._touched_goal = False
        self._touched_goal_player = None
        self._goal_players = set()

    # ---------- トースト数 ----------
    @property
    def toast_count(self):
        return sum(1 for toast in self.toasts if toast.collected)

    @property
    def toast_total(self):
        return len(self.toasts)

    # ---------- 衝突コールバックから呼ばれる(記録だけ) ----------
    def on_toast_touched(self, shape, egg):
        self._touched_toasts.append((shape, egg))

    def on_checkpoint_touched(self, shape, egg):
        self._touched_checkpoint = True
        self._touched_checkpoint_player = egg

    def on_goal_touched(self, shape, egg):
        self._touched_goal = True
        self._touched_goal_player = egg

    def on_fragile_touched(self, shape, _egg):
        if shape in self.climb_fragile:
            self._climb_fragile_touches.add(shape)

    def on_climb_item_touched(self, shape, egg):
        self.climb_item_touched.append((shape, egg))

    # ---------- 動く足場 ----------
    def prepare_physics_step(self, dt):
        """物理ステップの直前に呼ぶ。動く足場の速度を設定し、足場の時計を進める。"""
        for platform in self.moving_platforms:
            platform.prepare_step(self.time, dt)
        for platform in self.climb_moving_platforms:
            platform.prepare_step(self.time, dt)
        self.time += dt

    def register_climb_collisions(self):
        """崩れる足場との接触を遅延処理できるよう記録する。"""
        def mark_fragile(arbiter, _space, _data):
            fragile = next((shape for shape in arbiter.shapes
                            if shape in self.climb_fragile), None)
            if fragile is not None:
                self._climb_fragile_touches.add(fragile)

        def climb_pre_solve(arbiter, _space, _data):
            mark_fragile(arbiter, _space, _data)
            egg_shape = next(shape for shape in arbiter.shapes
                             if shape.collision_type == config.COLLISION_EGG)
            platform_shape = next(shape for shape in arbiter.shapes if shape is not egg_shape)
            return not physics.rising_through_platform(egg_shape, platform_shape)

        self.space.on_collision(config.COLLISION_EGG, config.COLLISION_PLATFORM,
                                begin=mark_fragile, pre_solve=climb_pre_solve)
        def item_begin(arbiter, _space, _data):
            egg_shape = next(shape for shape in arbiter.shapes
                             if shape.collision_type == config.COLLISION_EGG)
            item_shape = next(shape for shape in arbiter.shapes if shape is not egg_shape)
            self.on_climb_item_touched(item_shape, egg_shape.body.user_data)

        self.space.on_collision(config.COLLISION_EGG, config.COLLISION_TOAST, begin=item_begin)

    def _snap_platforms(self):
        for platform in self.moving_platforms:
            platform.snap_to_time(self.time)
        for platform in self.climb_moving_platforms:
            platform.snap_to_time(self.time)

    def sync_time(self, stage_time):
        """LANクライアント側の動く足場をホストの時刻に合わせる。"""
        self.time = stage_time
        self._snap_platforms()

    # ---------- 1ステップ後の処理 ----------
    def process_items(self, eggs):
        """このステップで触れたトースト等を処理する。トーストは触れた卵を回復する。"""
        if not isinstance(eggs, (tuple, list)):
            eggs = [eggs]
        touched, self._touched_toasts = self._touched_toasts, []
        for shape, egg in self.climb_item_touched:
            item = self.climb_item_shapes.get(shape)
            if item is not None and not item["collected"]:
                item["collected"] = True
                egg.float_glide_timer = max(egg.float_glide_timer, 4.0)
                self.climb_float_timer = 4.0
                self.climb_popup = "羽を獲得！ Eキーで4秒間浮遊"
                self.climb_popup_timer = 1.8
                self.climb_effects.append({"x": item["x"], "y": item["y"], "timer": 0.8})
        self.climb_item_touched.clear()
        for shape, egg in touched:
            if shape in self.climb_item_shapes:
                continue
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
        checkpoint_player = self._touched_checkpoint_player
        self._touched_checkpoint_player = None
        if (touched_checkpoint and self.checkpoint is not None
                and not self.checkpoint.active and checkpoint_player is not None
                and not checkpoint_player.durability.is_broken):
            self.checkpoint.active = True
            self._save_checkpoint(checkpoint_player)

        touched_goal, self._touched_goal = self._touched_goal, False
        goal_player = self._touched_goal_player
        self._touched_goal_player = None
        if (touched_goal and self.goal is not None and goal_player is not None
                and not goal_player.durability.is_broken):
            self._goal_players.add(goal_player)
        survivors = [egg for egg in eggs
                     if not egg.durability.is_broken and egg.body.position.y <= self.fall_limit]
        if survivors and all(egg in self._goal_players for egg in survivors):
            self.cleared = True

    def update(self, dt, eggs=None):
        """取得表示のタイマーを進める。"""
        if self.endless_climb and eggs:
            self.climb_best_y = min(self.climb_best_y,
                                    *(egg.body.position.y for egg in eggs))
            self._extend_climb_path()
            self._prune_climb_path()
            self._update_climb_gimmicks(dt)
        for popup in self.popups:
            popup["timer"] -= dt
        self.popups = [p for p in self.popups if p["timer"] > 0.0]
        for effect in self.pickup_effects:
            effect["timer"] -= dt
        self.pickup_effects = [e for e in self.pickup_effects if e["timer"] > 0.0]
        for effect in self.climb_effects:
            effect["timer"] -= dt
        self.climb_effects = [e for e in self.climb_effects if e["timer"] > 0.0]
        self.climb_popup_timer = max(0.0, self.climb_popup_timer - dt)
        if eggs:
            self.climb_float_timer = max(egg.float_glide_timer for egg in eggs)
    def _update_climb_gimmicks(self, dt):
        for shape, timer in list(self.climb_fragile.items()):
            if shape in self._climb_fragile_touches:
                timer += dt
                self.climb_fragile[shape] = timer
            else:
                timer = max(0.0, timer - dt * 2)
                self.climb_fragile[shape] = timer
            if timer >= 0.75 and shape in self.space.shapes:
                self.space.remove(shape)
                if shape in self.shapes:
                    self.shapes.remove(shape)
                self.climb_fragile.pop(shape, None)
        self._climb_fragile_touches.clear()

    def _add_climb_platform(self, vertices, kind="normal", moving=None):
        shape = physics.add_platforms(self.space, [vertices])[0]
        self.shapes.append(shape)
        self._climb_dynamic_shapes.append(shape)
        if kind == "fragile":
            self.climb_fragile[shape] = 0.0
        if moving:
            # 移動足場の専用キネマティックボディへ置き換える
            self.space.remove(shape)
            self.shapes.remove(shape)
            self._climb_dynamic_shapes.remove(shape)
            from moving_platform import MovingPlatform
            x, y = vertices[0]
            w = max(point[0] for point in vertices) - min(point[0] for point in vertices)
            h = max(point[1] for point in vertices) - min(point[1] for point in vertices)
            platform = MovingPlatform(self.space, {
                "rect": (x, y, w, h), "direction": moving[0], "distance": moving[1],
                "speed": moving[2], "phase": moving[3],
            })
            self.climb_moving_platforms.append(platform)
            return platform.shape
        return shape

    def _add_climb_item(self, x, y):
        size = 34
        shape = physics.add_sensor(
            self.space, rect(x - size / 2, y - size / 2, size, size), config.COLLISION_TOAST)
        item = {"x": x, "y": y, "shape": shape, "collected": False}
        self.climb_items.append(item)
        self.climb_item_shapes[shape] = item
        self._climb_dynamic_shapes.append(shape)

    def _extend_climb_path(self):
        """安全路と高難度ショートカットが分岐する上昇区間を生成する。"""
        from stages.helpers import trapezoid, zigzag
        while self._climb_top_y > self.climb_best_y - 1500:
            base_y = self._climb_top_y
            direction = self._climb_rng.choice((-1, 1))
            common_delta = 450
            if not 190 <= self._climb_last_x + direction * common_delta <= self.width - 190:
                direction *= -1
            side_x = self._climb_last_x + direction * 150
            common_x = self._climb_last_x + direction * common_delta
            split_x = side_x
            merge_x = split_x + direction * 230
            common_y = base_y - 125
            split_y = base_y - 250
            merge_y = base_y - self._climb_rng.randint(920, 940)

            # 横へ出る同じ高さの足場で、前の足場の真上を避けてから登り始める
            self._add_climb_platform(rect(side_x - 80, base_y, 160, 24))
            self._add_climb_platform(trapezoid(common_x - 90, common_y, 180, 30, 24))
            self._add_climb_platform(rect(split_x - 68, split_y, 136, 24))

            # 堅実な外周ルート: 広い足場を小さめのジャンプでいくつもつなぐ
            safe_count = 4
            for i in range(safe_count):
                t = (i + 1) / (safe_count + 1)
                y = split_y + (merge_y - split_y) * t
                width = self._climb_rng.randint(110, 130)
                lane_offsets = (230, 0, -230, 0)
                center_x = split_x + direction * lane_offsets[i]
                x = max(90, min(self.width - width - 90, center_x - width / 2))
                kind = ("fragile" if i == safe_count // 2
                        and self._climb_rng.random() < 0.55 else "normal")
                shape_kind = i % 3
                if shape_kind == 0:
                    vertices = rect(x, y, width, 24)
                elif shape_kind == 1:
                    vertices = trapezoid(x, y, width, 36, inset=26)
                else:
                    vertices = rect(x, y, width, 18)
                self._add_climb_platform(vertices, kind)

                # 時々、ゆっくり横移動する足場を外周ルートに置く
                if i == safe_count // 2 and self._climb_rng.random() < 0.6:
                    moving_x = max(55, min(self.width - 210, x + direction * 125))
                    self._add_climb_platform(
                        rect(moving_x, y - 100, 155, 22),
                        moving=( (direction, 0), 125, 105, self._climb_rng.random() * 4))

            # 直線的に大きく跳び移る危険ルート。失敗すると分岐下へ戻る
            shortcut_x = max(85, min(self.width - 305, split_x - direction * 95))
            shortcut_y = split_y - 130
            shortcut_platforms = []
            for offset, width in ((0, 112), (1, 104), (2, 96)):
                yy = shortcut_y - offset * 145
                xx = shortcut_x + direction * offset * 135
                vertices = zigzag(xx, yy, width, 38, teeth=3)[-1]
                self._add_climb_platform(
                    vertices, "fragile" if offset == 1 else "normal")
                shortcut_platforms.append((xx, yy, width))

            # ショートカットの最後にばね床を置き、合流足場までの跳躍を補助する
            boost_x, boost_y, boost_width = shortcut_platforms[-1]
            boost = physics.add_spring_pads(
                self.space, [spring_pad(boost_x + boost_width / 2 - 48, boost_y - 22, 96, 22)])
            self.spring_shapes.extend(boost)
            self.climb_dynamic_springs.extend(boost)
            self._climb_dynamic_shapes.extend(boost)

            # 分岐直後のばね床で、より高い近道へ挑戦できる
            spring_y = common_y - 22
            spring_x = common_x - 52
            pads = physics.add_spring_pads(self.space, [spring_pad(spring_x, spring_y, 104, 22)])
            self.spring_shapes.extend(pads)
            self.climb_dynamic_springs.extend(pads)
            self._climb_dynamic_shapes.extend(pads)

            # 羽アイテムは安全路上に配置し、空中の軌道修正に使えるようにする
            item_x = split_x - direction * 8
            self._add_climb_item(item_x, common_y - 72)

            # 合流地点は広い複合足場。次の分岐までの休憩場所にもする
            landing_x = max(120, min(self.width - 360, merge_x - 110))
            platform_type = self._climb_rng.randrange(3)
            if platform_type == 0:
                landing = trapezoid(landing_x, merge_y, 250, 42, 38)
                self._add_climb_platform(landing)
            elif platform_type == 1:
                for segment in zigzag(landing_x, merge_y, 250, 48, teeth=5):
                    self._add_climb_platform(segment)
            else:
                self._add_climb_platform(rect(landing_x, merge_y, 250, 28))

            self._climb_top_y = merge_y
            self._climb_last_x = landing_x + 125
            if self._climb_rng.random() < 0.65:
                self._add_climb_item(landing_x + self._climb_rng.randint(40, 210), merge_y - 88)

    def _prune_climb_path(self):
        """十分下へ離れた足場を破棄し、長時間プレイ時の物理形状数を抑える。"""
        for shape in list(self._climb_dynamic_shapes):
            lowest_y = max(vertex.y for vertex in shape.get_vertices())
            if lowest_y > self.climb_best_y + 1800:
                if shape in self.space.shapes:
                    self.space.remove(shape)
                self._climb_dynamic_shapes.remove(shape)
                if shape in self.shapes:
                    self.shapes.remove(shape)
                if shape in self.spring_shapes:
                    self.spring_shapes.remove(shape)
                if shape in self.climb_item_shapes:
                    self.climb_item_shapes.pop(shape, None)
                    self.climb_items = [item for item in self.climb_items if item["shape"] is not shape]
                self.climb_fragile.pop(shape, None)
                self._climb_fragile_touches.discard(shape)
        for platform in list(self.climb_moving_platforms):
            lowest_y = platform.body.position.y + max(vertex.y for vertex in platform.shape.get_vertices())
            if lowest_y > self.climb_best_y + 1800:
                if platform.shape in self.space.shapes:
                    self.space.remove(platform.shape, platform.body)
                self.climb_moving_platforms.remove(platform)
                if platform.shape in self.shapes:
                    self.shapes.remove(platform.shape)
                if platform.shape in self._climb_dynamic_shapes:
                    self._climb_dynamic_shapes.remove(platform.shape)

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
        if self.endless_climb:
            for platform in self.climb_moving_platforms:
                if platform.shape in self.space.shapes:
                    self.space.remove(platform.shape, platform.body)
                if platform.shape in self.shapes:
                    self.shapes.remove(platform.shape)
            self.climb_moving_platforms.clear()
            self.climb_dynamic_springs.clear()
            for shape in self._climb_dynamic_shapes:
                if shape in self.space.shapes:
                    self.space.remove(shape)
                if shape in self.shapes:
                    self.shapes.remove(shape)
                if shape in self.spring_shapes:
                    self.spring_shapes.remove(shape)
            self._climb_dynamic_shapes.clear()
            self.climb_items.clear()
            self.climb_item_shapes.clear()
            self.climb_fragile.clear()
            self._climb_fragile_touches.clear()
            self.climb_effects.clear()
            self.climb_float_timer = 0.0
            self.climb_item_touched.clear()
            self._climb_rng = random.Random(self._climb_seed)
            self._climb_top_y = min(vertex.y for shape in self.shapes for vertex in shape.get_vertices())
            self._climb_last_x = self.egg_start[0]
            self.climb_best_y = self.climb_start_y
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
        self._touched_checkpoint_player = None
        self._touched_goal = False
        self._touched_goal_player = None
        self._goal_players.clear()
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
            if shape in self.climb_fragile:
                ratio = min(1.0, self.climb_fragile[shape] / 0.75)
                fill = (218, 172 - round(76 * ratio), 95 - round(35 * ratio))
                edge = (130, 77, 52)
            else:
                fill = config.COLOR_PLATFORM
                edge = (104, 133, 119)
            pygame.draw.polygon(surface, fill, points)
            pygame.draw.polygon(surface, edge, points, 3)
        for platform in self.moving_platforms:
            platform.draw(surface, camera)
        for platform in self.climb_moving_platforms:
            platform.draw(surface, camera)
        for item in self.climb_items:
            if not item["collected"]:
                self._draw_float_item(surface, camera, item)
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
        for effect in self.climb_effects:
            progress = 1.0 - effect["timer"] / 0.8
            cx, cy = camera.apply((effect["x"], effect["y"]))
            pygame.draw.circle(surface, (192, 239, 255), (round(cx), round(cy)),
                               int(12 + progress * 28), 3)

    def _draw_float_item(self, surface, camera, item):
        """数秒浮遊できる羽アイテム。"""
        cx, cy = camera.apply((item["x"], item["y"]))
        pygame.draw.circle(surface, (246, 251, 255), (round(cx), round(cy)), 20)
        pygame.draw.circle(surface, (112, 197, 222), (round(cx), round(cy)), 20, 3)
        pygame.draw.ellipse(surface, (255, 255, 255),
                            pygame.Rect(round(cx - 5), round(cy - 14), 10, 24))
        pygame.draw.line(surface, (112, 197, 222), (round(cx), round(cy - 14)),
                         (round(cx), round(cy + 13)), 2)

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

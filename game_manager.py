"""ゲーム全体の進行(画面の状態)を管理するファイル。

状態:
  TITLE       : タイトル画面
  STAGE_SELECT: ステージ選択画面
  PLAYING     : プレイ中
  PAUSED      : ポーズ中(物理・足場・カメラ・演出がすべて止まる)
  GAME_OVER   : ゲームオーバー
  STAGE_CLEAR : ステージクリア(約3秒後に次のステージへ)
  GAME_CLEAR  : 最終ステージをクリアした

セーブ(クリア状況)は save_manager.py が担当する。
"""

import logging
import math

import pygame

import config
import physics
import ui
from camera import Camera
from debug import draw_debug
from player import Egg
from save_manager import SaveManager
from stage import STAGE_DATA, Stage

logger = logging.getLogger("lost_egg")

STATE_TITLE = "TITLE"
STATE_STAGE_SELECT = "STAGE_SELECT"
STATE_PLAYING = "PLAYING"
STATE_PAUSED = "PAUSED"
STATE_GAME_OVER = "GAME_OVER"
STATE_STAGE_CLEAR = "STAGE_CLEAR"
STATE_GAME_CLEAR = "GAME_CLEAR"

# メニューの項目 (動作の名前, 表示する文字)
DIFFICULTIES = (
    # 名前, 被ダメージ倍率, ジャンプ倍率, 空中操作倍率, 開始耐久度
    ("やさしい", 0.5, 1.15, 1.25, 100),
    ("ふつう", 1.0, 1.0, 1.0, 100),
    ("むずかしい", 1.5, 0.9, 0.8, 75),
)
PAUSE_ITEMS = [("resume", "再開"), ("title", "タイトルへ戻る")]
GAME_OVER_ITEMS = [("checkpoint", "チェックポイントから再開"), ("title", "タイトルへ戻る")]
GAME_CLEAR_ITEMS = [("title", "タイトルへ戻る"), ("again", "もう一度プレイ")]
CLIMB_GAME_OVER_ITEMS = [("climb_restart", "もう一度登る"), ("title", "タイトルへ戻る")]
CLIMB_STAGE_ID = 5
CONFIRM_ITEMS = [("yes", "はい"), ("no", "いいえ")]
STAGE_SELECT_HINT = "↑/↓:選択   Enter:決定   Esc:戻る"


class Game:
    def __init__(self, start_stage=None):
        """start_stage を指定するとタイトルを飛ばしてそのステージから始める(開発用)。省略するとタイトル画面から。"""
        pygame.init()
        self.screen = pygame.display.set_mode((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
        pygame.display.set_caption(config.WINDOW_TITLE)
        self.clock = pygame.time.Clock()
        self.fonts = ui.load_fonts()

        self.save = SaveManager()
        self.save.load()                 # クリア状況を読み込む(無い・壊れている場合は初期状態)

        self.running = True
        self.show_debug = False          # デバッグ表示は通常OFF。F3で切り替える
        self.clear_records = {}          # ステージ番号 → クリア時のトースト取得数(メモリ上のみ。保存しない)
        self.space = self.stage = self.egg = self.camera = None
        self.steps = 0
        self.shake_timer = 0.0
        self.shake_duration = 0.0
        self.shake_intensity = 0.0
        self.shake_phase = 0.0
        self.clear_elapsed = 0.0
        self.difficulty_index = 1
        self.game_mode = "stage"
        # LAN協力プレイは一時停止中。通信実装は残し、起動経路は無効化している。
        self.net_mode = None
        self.net_server = None
        self.net_client = None
        self.player_id = None
        self.players = {}
        self.remote_inputs = {}
        self.net_jump_pending = False
        self.net_send_timer = 0.0
        self.net_snapshot_timer = 0.0
        self.net_disconnected = False
        if start_stage is None:
            self.go_to_title()
        else:
            self.load_stage(start_stage)

    # ---------- ステージの読み込み ----------
    def load_stage(self, number):
        """新しい物理空間にステージと卵を作り、最初から始める。"""
        self.space = physics.create_space()
        self.stage = Stage(self.space, number)
        self.climb_mode = self.stage.endless_climb
        self.egg = Egg(self.space, *self.stage.egg_start)
        self.players = {"host": self.egg}
        self._configure_player(self.egg)
        if self.climb_mode:
            self.egg.spring_impulse = 990.0
            self.egg.jump_multiplier = 1.24
        if not self.climb_mode:
            physics.register_egg_collisions(self.space, self.egg.add_impact)
            physics.register_item_collisions(
                self.space, self.stage.on_toast_touched,
                self.stage.on_checkpoint_touched, self.stage.on_goal_touched)
            physics.register_spike_collisions(self.space, self.egg.add_spike_touch)
        else:
            self.stage.register_climb_collisions()
        physics.register_spring_collisions(
            self.space, self.egg.add_spring_touch, one_way=self.climb_mode)
        if self.net_mode == "host":
            for index, player_id in enumerate(sorted(self.remote_inputs), start=1):
                self.players[player_id] = self._create_remote_egg(index)
        self.camera = Camera(self.stage.width, self.stage.height)
        self.camera.allow_vertical_negative = self.climb_mode
        self.camera.snap_to(*self.stage.egg_start)
        logger.info("ステージ開始: ステージ%d(トースト%d個)", number, self.stage.toast_total)

        self._logged_toast_count = 0          # ログ出力用: すでに記録したトースト取得数
        self._logged_checkpoint = False       # ログ出力用: チェックポイント有効化を記録したか
        self.state = STATE_PLAYING
        self.menu_items = []
        self.menu_index = 0
        self.confirming = False
        self.message = ""
        self.accumulator = 0.0
        self.jump_requested = False
        self.reset_requested = False
        self.clear_timer = 0.0
        self.steps = 0

    def _configure_player(self, egg):
        _, damage_scale, jump_scale, air_scale, start_hp = DIFFICULTIES[self.difficulty_index]
        egg.damage_multiplier = damage_scale
        egg.jump_multiplier = jump_scale
        egg.air_control_multiplier = air_scale
        egg.durability.hp = start_hp

    def _create_remote_egg(self, index):
        egg = Egg(self.space, self.stage.egg_start[0] + index * 64,
                  self.stage.egg_start[1])
        self._configure_player(egg)
        return egg

    def respawn(self, from_checkpoint):
        """卵を復活させる。チェックポイント通過済みなら保存した状態へ、そうでなければステージの最初から。"""
        stage, egg = self.stage, self.egg
        used_checkpoint = from_checkpoint and stage.checkpoint_state is not None
        eggs = list(self.players.values())
        if used_checkpoint:
            state = stage.restore_checkpoint()
            for index, player in enumerate(eggs):
                player.reset(state["x"] + index * 58, state["y"], state["hp"])
                player.shape.sensor = False
            self.camera.snap_to(state["x"], state["y"])   # 復活時はカメラも即座に移動
        else:
            stage.reset_progress()
            for index, player in enumerate(eggs):
                player.reset(stage.egg_start[0] + index * 58, stage.egg_start[1])
                player.shape.sensor = False
            self.camera.snap_to(*stage.egg_start)
        logger.info("%s: 位置=(%.0f, %.0f) 耐久度=%d トースト=%d/%d",
                    "チェックポイントから再開" if used_checkpoint else "ステージを最初からやり直し",
                    egg.body.position.x, egg.body.position.y, egg.durability.hp,
                    stage.toast_count, stage.toast_total)
        self._sync_progress_log()
        self.accumulator = 0.0
        self.jump_requested = False

    def _sync_progress_log(self):
        """トースト取得とチェックポイント有効化を、変化した瞬間だけログに記録する。"""
        stage, egg = self.stage, self.egg
        count = stage.toast_count
        if count > self._logged_toast_count:
            logger.info("トースト取得: ステージ%d %d/%d 耐久度=%d",
                        stage.number, count, stage.toast_total, egg.durability.hp)
        self._logged_toast_count = count
        active = stage.checkpoint is not None and stage.checkpoint.active
        if active and not self._logged_checkpoint:
            logger.info("チェックポイント有効化: ステージ%d 位置=(%.0f, %.0f) 耐久度=%d",
                        stage.number, egg.body.position.x, egg.body.position.y, egg.durability.hp)
        self._logged_checkpoint = active

    def open_menu(self, state, items, message=""):
        self.state = state
        self.menu_items = items
        self.menu_index = 0
        self.confirming = False
        self.message = message
        self.jump_requested = False

    def go_to_title(self, index=0):
        """タイトル画面へ戻る。プレイ中のステージ(物理空間・卵など)は破棄する。"""
        logger.info("タイトル画面へ移動")
        if self.net_server:
            self.net_server.close()
            self.net_server = None
            self.net_mode = None
            self.remote_inputs.clear()
        self.players = {}
        self.space = self.stage = self.egg = self.camera = None
        self.state = STATE_TITLE
        self.menu_items = self._title_menu_items()
        self.menu_index = index
        self.confirming = False
        self.message = ""
        self.accumulator = 0.0
        self.jump_requested = False
        self.steps = 0

    def _title_menu_items(self):
        name = DIFFICULTIES[self.difficulty_index][0]
        mode = "ステージ攻略" if self.game_mode == "stage" else "ひたすら上へ"
        return [
            ("start", "ゲーム開始"),
            ("mode", f"モード: {mode}  ◀ ▶"),
            ("select", "ステージ選択"),
            ("difficulty", f"難易度: {name}  ◀ ▶"),
            ("quit", "ゲーム終了"),
        ]

    def change_difficulty(self, step=1):
        self.difficulty_index = (self.difficulty_index + step) % len(DIFFICULTIES)
        self.menu_items = self._title_menu_items()

    def open_stage_select(self):
        """ステージ選択画面を開く。カーソルは「次に挑戦するステージ」に置く。"""
        self.game_mode = "stage"
        self.menu_items = self._title_menu_items()
        self.state = STATE_STAGE_SELECT
        self.menu_index = self.save.next_start_stage() - 1    # メニュー番号は 0 始まり

    def move_stage_cursor(self, step):
        """ステージ選択のカーソルを動かす。未解放のステージは飛ばす(選べない)。"""
        for _ in range(config.LAST_STAGE):
            self.menu_index = (self.menu_index + step) % config.LAST_STAGE
            if self.save.is_unlocked(self.menu_index + 1):
                break

    def handle_stage_select_key(self, key):
        if key == pygame.K_UP:
            self.move_stage_cursor(-1)
        elif key == pygame.K_DOWN:
            self.move_stage_cursor(1)
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            number = self.menu_index + 1
            if self.save.is_unlocked(number):
                self.game_mode = "stage"
                self.load_stage(number)
        elif key == pygame.K_ESCAPE:
            self.go_to_title(index=2)          # カーソルは「ステージ選択」に置く

    # ---------- メインループ ----------
    def run(self):
        while self.running:
            frame_time = min(self.clock.tick(config.FPS) / 1000.0, 0.25)  # 長い停止後の暴走防止
            for event in pygame.event.get():
                self.handle_event(event)
            self.update(frame_time)
            self.draw()
        if self.net_server:
            self.net_server.close()
        if self.net_client:
            self.net_client.close()
        pygame.quit()

    # ---------- 入力 ----------
    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.running = False
            return
        if event.type != pygame.KEYDOWN:
            return
        key = event.key

        if self.state == STATE_TITLE:
            if key in (pygame.K_LEFT, pygame.K_RIGHT):
                selected_action = self.menu_items[self.menu_index][0]
                step = -1 if key == pygame.K_LEFT else 1
                if selected_action == "difficulty":
                    self.change_difficulty(step)
                elif selected_action == "mode":
                    self.game_mode = "climb" if self.game_mode == "stage" else "stage"
                    self.menu_items = self._title_menu_items()
                return
            self.handle_menu_key(key)
        elif self.state == STATE_PLAYING:
            if key == pygame.K_ESCAPE and self.net_mode != "client":
                self.open_menu(STATE_PAUSED, PAUSE_ITEMS)
            elif key == pygame.K_SPACE:
                if self.net_mode == "client":
                    self.net_jump_pending = True
                else:
                    self.jump_requested = True
            elif key == pygame.K_F3:
                self.show_debug = not self.show_debug
            elif config.DEV_MODE and key == pygame.K_r and not self.climb_mode:  # 開発用(exe版では無効)
                self.reset_requested = True
            elif config.DEV_MODE and key == pygame.K_k and not self.climb_mode:  # 開発用(exe版では無効)
                self.egg.durability.hp = 0
            elif config.DEV_MODE and key == pygame.K_g and not self.climb_mode:  # 開発用(exe版では無効)
                self.egg.body.position = (self.egg.body.position.x, self.stage.fall_limit + 50)
        elif self.state == STATE_STAGE_SELECT:
            self.handle_stage_select_key(key)
        elif (self.state in (STATE_PAUSED, STATE_GAME_OVER, STATE_GAME_CLEAR)
              and self.net_mode != "client"):
            self.handle_menu_key(key)
        # STATE_STAGE_CLEAR 中はキー入力を受け付けない

    def handle_menu_key(self, key):
        items = CONFIRM_ITEMS if self.confirming else self.menu_items
        if key == pygame.K_UP:
            self.menu_index = (self.menu_index - 1) % len(items)
        elif key == pygame.K_DOWN:
            self.menu_index = (self.menu_index + 1) % len(items)
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            action = items[self.menu_index][0]
            self.activate(action)
        elif key == pygame.K_ESCAPE:
            if self.confirming:
                self.cancel_confirm()
            elif self.state == STATE_PAUSED:
                self.state = STATE_PLAYING       # Esc でポーズ解除

    def cancel_confirm(self):
        self.confirming = False
        self.menu_index = 0

    def activate(self, action):
        if action == "start":
            number = CLIMB_STAGE_ID if self.game_mode == "climb" else self.save.next_start_stage()
            self.load_stage(number)    # 通常は最も進んだ未クリア、上昇は専用コース
        elif action == "mode":
            self.game_mode = "climb" if self.game_mode == "stage" else "stage"
            self.menu_items = self._title_menu_items()
        elif action == "difficulty":
            self.change_difficulty()
        elif action == "select":
            self.open_stage_select()
        elif action == "quit":
            self.running = False
        elif action == "resume":
            self.state = STATE_PLAYING
        elif action == "checkpoint":
            self.respawn(from_checkpoint=True)
            self.state = STATE_PLAYING
        elif action == "title":
            if self.state == STATE_GAME_CLEAR:
                self.go_to_title()
            else:
                self.confirming = True           # 確認画面を出す
                self.menu_index = 1              # 誤操作防止のため「いいえ」を最初に選ぶ
        elif action == "again":
            self.load_stage(1)                   # ステージ1から。保存済みのクリア状況はそのまま残る
        elif action == "climb_restart":
            self.load_stage(CLIMB_STAGE_ID)
        elif action == "yes":
            self.go_to_title()
        elif action == "no":
            self.cancel_confirm()

    # ---------- 更新 ----------
    def update(self, frame_time):
        if self.net_mode == "client":
            self.update_lan_client(frame_time)
            return
        if self.net_mode == "host":
            self._poll_lan_server()
        if self.state != STATE_PAUSED:
            self._update_screen_shake(frame_time)
        if self.state == STATE_PLAYING:
            self.update_playing(frame_time)
        elif self.state == STATE_STAGE_CLEAR:
            self.stage.update(frame_time)
            self.clear_elapsed += frame_time
            self.clear_timer -= frame_time
            if self.clear_timer <= 0.0:
                self.after_stage_clear()
        if self.net_mode == "host":
            self.net_snapshot_timer += frame_time
            if self.net_snapshot_timer >= 1.0 / 25.0:
                self.net_snapshot_timer = 0.0
                self.net_server.broadcast(self._make_lan_state())
        # PAUSED / GAME_OVER / GAME_CLEAR では何も進めない(物理・足場・カメラ・演出がすべて止まる)

    def _trigger_screen_shake(self, damage_amount):
        self.shake_duration = 0.32
        self.shake_timer = self.shake_duration
        self.shake_intensity = min(16.0, 7.0 + damage_amount * 0.18)
        self.shake_phase = 0.0

    def _update_screen_shake(self, dt):
        self.shake_timer = max(0.0, self.shake_timer - dt)
        if self.camera is None:
            return
        if self.shake_timer <= 0.0:
            self.camera.shake_x = self.camera.shake_y = 0.0
            return
        self.shake_phase += dt * math.tau * 28
        amount = self.shake_intensity * self.shake_timer / self.shake_duration
        self.camera.shake_x = math.sin(self.shake_phase) * amount
        self.camera.shake_y = math.cos(self.shake_phase * 0.83) * amount * 0.7

    def _poll_lan_server(self):
        for message in self.net_server.poll():
            player_id = message["player_id"]
            if message["type"] == "join" and player_id not in self.players:
                self.remote_inputs[player_id] = {"move": 0, "jump": False}
                index = len(self.players)
                player = self._create_remote_egg(index)
                player.body.position = (self.egg.body.position.x + index * 58,
                                        self.egg.body.position.y)
                self.players[player_id] = player
                logger.info("LAN参加: %s (%s)", player_id, message.get("address", ""))
            elif message["type"] == "input" and player_id in self.remote_inputs:
                control = self.remote_inputs[player_id]
                control["move"] = message["move"]
                control["jump"] = control["jump"] or message["jump"]
            elif message["type"] == "leave":
                self.remote_inputs.pop(player_id, None)
                player = self.players.pop(player_id, None)
                if player is not None and player.body in self.space.bodies:
                    self.space.remove(player.shape, player.body)
                logger.info("LAN切断: %s", player_id)

    def _make_lan_state(self):
        return {
            "stage": self.stage.number,
            "game_state": self.state,
            "stage_time": self.stage.time,
            "clear_timer": self.clear_timer,
            "clear_elapsed": self.clear_elapsed,
            "shake_x": self.camera.shake_x,
            "shake_y": self.camera.shake_y,
            "toast_indices": [toast.index for toast in self.stage.toasts if toast.collected],
            "checkpoint_active": bool(self.stage.checkpoint and self.stage.checkpoint.active),
            "players": [
                {
                    "id": player_id,
                    "x": egg.body.position.x,
                    "y": egg.body.position.y,
                    "vx": egg.body.velocity.x,
                    "vy": egg.body.velocity.y,
                    "angle": egg.body.angle,
                    "hp": egg.durability.hp,
                }
                for player_id, egg in self.players.items()
            ],
        }

    def update_lan_client(self, frame_time):
        if self.net_client.player_id:
            keys = pygame.key.get_pressed()
            move = int(bool(keys[pygame.K_d] or keys[pygame.K_RIGHT])) - int(
                bool(keys[pygame.K_a] or keys[pygame.K_LEFT]))
            self.net_client.send_input(move, self.net_jump_pending)
            self.net_jump_pending = False

        state, disconnected = self.net_client.poll()
        if state is not None:
            self._apply_lan_state(state, frame_time)
        elif self.stage is not None:
            self.stage.sync_time(self.stage.time + frame_time)
            self.stage.update(frame_time)
        if disconnected and not self.net_disconnected:
            self.net_disconnected = True
            self.state = STATE_GAME_OVER
            self.message = "ホストとの接続が切れました"

    def _apply_lan_state(self, data, frame_time):
        number = data.get("stage")
        if number not in STAGE_DATA:
            return
        if self.stage is None or self.stage.number != number:
            self.load_stage(number)

        self.state = data.get("game_state", STATE_PLAYING)
        self.clear_timer = data.get("clear_timer", 0.0)
        self.clear_elapsed = data.get("clear_elapsed", 0.0)
        self.stage.sync_time(data.get("stage_time", 0.0))
        if self.stage.checkpoint:
            self.stage.checkpoint.active = data.get("checkpoint_active", False)

        collected = set(data.get("toast_indices", []))
        for toast in self.stage.toasts:
            if toast.index in collected and not toast.collected:
                toast.collected = True
                self.stage.pickup_effects.append({"x": toast.x, "y": toast.y, "timer": 0.7})
                self.stage.popups.append({
                    "text": f"トースト +{config.TOAST_HEAL}", "x": toast.x, "y": toast.y,
                    "timer": config.TOAST_POPUP_TIME,
                })
            elif toast.index not in collected:
                toast.collected = False

        seen = set()
        for item in data.get("players", []):
            player_id = item.get("id")
            if not isinstance(player_id, str):
                continue
            seen.add(player_id)
            egg = self.players.get(player_id)
            if egg is None:
                egg = self._create_remote_egg(len(self.players))
                self.players[player_id] = egg
            egg.body.position = (item["x"], item["y"])
            egg.body.velocity = (item["vx"], item["vy"])
            egg.body.angle = item["angle"]
            if item["hp"] < egg.durability.hp:
                egg.durability.flash_timer = config.DAMAGE_FLASH_TIME
            egg.durability.hp = item["hp"]

        for player_id in set(self.players) - seen:
            egg = self.players.pop(player_id)
            if egg.body in self.space.bodies:
                self.space.remove(egg.shape, egg.body)
        self.player_id = self.net_client.player_id or self.player_id or "host"
        self.egg = self.players.get(self.player_id, next(iter(self.players.values())))
        self.stage.update(frame_time)
        if self.state == STATE_PLAYING:
            self.camera.update(self.egg.body.position.x, self.egg.body.position.y,
                               self.egg.body.velocity.x, self.egg.body.velocity.y,
                               frame_time)
        self.camera.shake_x = data.get("shake_x", 0.0)
        self.camera.shake_y = data.get("shake_y", 0.0)

    def update_playing(self, frame_time):
        egg, stage = self.egg, self.stage
        keys = pygame.key.get_pressed()
        host_move = int(bool(keys[pygame.K_d] or keys[pygame.K_RIGHT])) - int(
            bool(keys[pygame.K_a] or keys[pygame.K_LEFT]))

        # 固定時間ステップ: 描画とは別に、1/60秒ずつ物理を進める
        self.steps = 0
        self.accumulator += frame_time
        while self.accumulator >= config.PHYSICS_DT and self.steps < config.MAX_STEPS_PER_FRAME:
            for player_id, player in self.players.items():
                if player_id == "host":
                    move, jump = host_move, self.jump_requested
                else:
                    control = self.remote_inputs.get(player_id, {"move": 0, "jump": False})
                    move, jump = control["move"], control["jump"]
                player.apply_controls(
                    move, jump, config.PHYSICS_DT,
                    float_pressed=(player_id == "host" and keys[pygame.K_e]),
                    allow_float=self.climb_mode)
            self.jump_requested = False           # ジャンプ要求は最初の1ステップだけ有効
            for control in self.remote_inputs.values():
                control["jump"] = False
            stage.prepare_physics_step(config.PHYSICS_DT)   # 動く足場の速度を設定
            self.space.step(config.PHYSICS_DT)
            for player in self.players.values():
                player.update_spring()
                physics.limit_speed(player.body, config.MAX_SPEED)
                player.update_ground_state(config.PHYSICS_DT)
                if not self.climb_mode:
                    hp_before = player.durability.hp
                    player.update_damage(config.PHYSICS_DT)
                    if player.durability.hp < hp_before:
                        self._trigger_screen_shake(hp_before - player.durability.hp)
                if not self.climb_mode and (player.durability.is_broken or player.body.position.y > stage.fall_limit):
                    player.shape.sensor = True
            stage.process_items(list(self.players.values()))
            stage.update(config.PHYSICS_DT, list(self.players.values()))
            self.accumulator -= config.PHYSICS_DT
            self.steps += 1
            if stage.cleared or self.game_over_message():
                break
        if self.steps == config.MAX_STEPS_PER_FRAME:
            self.accumulator = 0.0                # 追いつけない分は捨てる
        self._sync_progress_log()

        if self.reset_requested:
            self.reset_requested = False
            self.respawn(from_checkpoint=False)
            return
        if stage.cleared:
            self.begin_stage_clear()
            return
        message = self.game_over_message()
        if message:
            logger.info("ゲームオーバー: %s ステージ%d 位置=(%.0f, %.0f) 耐久度=%d",
                        message, stage.number, egg.body.position.x, egg.body.position.y,
                        egg.durability.hp)
            items = CLIMB_GAME_OVER_ITEMS if self.climb_mode else GAME_OVER_ITEMS
            self.open_menu(STATE_GAME_OVER, items, message)
            return

        active = [player for player in self.players.values()
                  if self.climb_mode or (player.body.position.y <= stage.fall_limit
                                         and not player.durability.is_broken)]
        if not active:
            active = [egg]
        count = len(active)
        self.camera.update(
            sum(player.body.position.x for player in active) / count,
            sum(player.body.position.y for player in active) / count,
            sum(player.body.velocity.x for player in active) / count,
            sum(player.body.velocity.y for player in active) / count,
            frame_time,
        )

    def game_over_message(self):
        """ゲームオーバーの条件を満たしていれば、画面に出すメッセージを返す。満たさなければ空文字。"""
        if self.climb_mode:
            if (self.egg.body.position.y > self.stage.climb_best_y + 520
                    or self.egg.body.position.x < -70
                    or self.egg.body.position.x > self.stage.width + 70):
                return "足場から落下…もう一度登ろう"
            return ""
        if all(player.durability.is_broken or player.body.position.y > self.stage.fall_limit
               for player in self.players.values()):
            return "全員ゲームオーバー…"
        return ""

    def has_next_stage(self):
        return 1 <= self.stage.number < config.LAST_STAGE

    def begin_stage_clear(self):
        self.clear_records[self.stage.number] = self.stage.toast_count   # 取得数を記録(保存はしない)
        logger.info("ステージクリア: ステージ%d トースト=%d/%d 耐久度=%d", self.stage.number,
                    self.stage.toast_count, self.stage.toast_total, self.egg.durability.hp)
        self.save.mark_cleared(self.stage.number)    # クリア状況を保存(解放状況はここから決まる)
        self.state = STATE_STAGE_CLEAR
        self.clear_timer = config.STAGE_CLEAR_WAIT
        self.clear_elapsed = 0.0
        self.jump_requested = False

    def after_stage_clear(self):
        if self.has_next_stage():
            self.load_stage(self.stage.number + 1)    # トースト取得数は新しいステージで0に戻る
        else:
            self.open_menu(STATE_GAME_CLEAR, GAME_CLEAR_ITEMS)

    # ---------- 描画 ----------
    def draw(self):
        screen, fonts = self.screen, self.fonts
        if self.state == STATE_TITLE:
            ui.draw_title_screen(screen, fonts, config.WINDOW_TITLE,
                                 [label for _, label in self.menu_items], self.menu_index)
            pygame.display.flip()
            return
        if self.state == STATE_STAGE_SELECT:
            entries = [(STAGE_DATA[n]["name"], self.save.status(n))
                       for n in range(1, config.LAST_STAGE + 1)]
            ui.draw_stage_select(screen, fonts, "ステージ選択", entries, self.menu_index,
                                 STAGE_SELECT_HINT)
            pygame.display.flip()
            return
        stage, egg, camera = self.stage, self.egg, self.camera

        stage.draw_background(screen, camera)
        stage.draw(screen, camera)
        fried_ratio = 1.0 if self.state == STATE_GAME_CLEAR else 0.0
        if self.state == STATE_STAGE_CLEAR:
            progress = min(1.0, self.clear_elapsed / 1.15)
            fried_ratio = progress * progress * (3.0 - 2.0 * progress)
        fried_position = None
        if fried_ratio > 0.0 and stage.goal is not None:
            # Pan center is inside its bowl (base_y - 24); this is visual only.
            fried_position = (stage.goal.x, stage.goal.base_y - 24)
        for player_id, player in self.players.items():
            coop_clear = self.net_mode is not None and len(self.players) > 1
            player_fried_ratio = fried_ratio if player_id == "host" or coop_clear else 0.0
            player_fried_position = fried_position
            if coop_clear and player_id != "host" and player_fried_ratio:
                player_fried_position = player.body.position
            player.draw(screen, camera, player_fried_ratio,
                        player_fried_position if player_fried_ratio else None)
            if len(self.players) > 1:
                x, y = camera.apply((player.body.position.x, player.body.position.y - 48))
                name = "HOST" if player_id == "host" else player_id.upper()
                tag = fonts["small"].render(name, True, (45, 55, 72))
                screen.blit(tag, tag.get_rect(center=(round(x), round(y))))
        stage.draw_pickup_effects(screen, camera)
        stage.draw_popups(screen, camera, fonts["ui"])
        self.draw_hud()

        if self.net_disconnected:
            self.draw_menu("CONNECTION LOST")
        elif self.state == STATE_PAUSED:
            self.draw_menu("PAUSE")
        elif self.state == STATE_GAME_OVER:
            self.draw_menu("GAME OVER")
        elif self.state == STATE_GAME_CLEAR:
            self.draw_menu("GAME CLEAR")
        elif self.state == STATE_STAGE_CLEAR:
            message = f"トースト {stage.toast_count}/{stage.toast_total}"
            if self.has_next_stage():
                message += "   まもなく次のステージへ…"
            ui.draw_menu(screen, fonts, "STAGE CLEAR", [], 0, message=message)

        if self.show_debug:
            draw_debug(screen, fonts["debug"], egg, self.steps, self.clock.get_fps(),
                       camera, self.state, stage)
        pygame.display.flip()

    def draw_hud(self):
        """プレイ画面の表示: ステージ番号、耐久度ゲージ、トースト数、操作ガイド。"""
        screen, fonts = self.screen, self.fonts
        if self.climb_mode:
            current = max(0, int(self.stage.climb_start_y - self.egg.body.position.y))
            best = max(0, int(self.stage.climb_start_y - self.stage.climb_best_y))
            label = fonts["ui"].render("ENDLESS CLIMB", True, config.COLOR_TEXT)
            screen.blit(label, (config.UI_MARGIN, config.UI_MARGIN))
            score = fonts["ui"].render(f"上昇 {current} m   最高 {best} m", True, config.COLOR_TEXT)
            screen.blit(score, (config.UI_MARGIN, config.UI_MARGIN + 38))
            guide = fonts["small"].render(
                "A/←:左へ   D/→:右へ   Space:ジャンプ   E:羽を使って浮遊", True,
                config.COLOR_TEXT)
            screen.blit(guide, (config.UI_MARGIN,
                                config.WINDOW_HEIGHT - config.UI_MARGIN - guide.get_height()))
            status_text = "落下すると最初から"
            if self.stage.climb_float_timer > 0:
                status_text += f"   浮遊チャージ {self.stage.climb_float_timer:.1f}秒"
            if self.stage.climb_popup_timer > 0:
                status = fonts["small"].render(self.stage.climb_popup, True, (37, 99, 125))
                screen.blit(status, status.get_rect(center=(config.WINDOW_WIDTH // 2, 92)))
            else:
                status = fonts["small"].render(status_text, True, config.COLOR_TEXT)
                screen.blit(status, (config.UI_MARGIN, config.UI_MARGIN + 72))
            return
        difficulty = DIFFICULTIES[self.difficulty_index][0]
        label = (f"STAGE {self.stage.number} / {difficulty}"
                 if self.stage.number > 0 else "TEST STAGE")
        screen.blit(fonts["ui"].render(label, True, config.COLOR_TEXT),
                    (config.UI_MARGIN, config.UI_MARGIN))
        if self.net_mode:
            mode = "LAN協力プレイ" if len(self.players) > 1 else "LAN待機中"
            screen.blit(fonts["small"].render(f"{mode}  {len(self.players)}/8", True,
                                               config.COLOR_TEXT),
                        (config.UI_MARGIN, config.UI_MARGIN + 32))
        ui.draw_durability_gauge(screen, fonts["ui"], self.egg.durability.hp,
                                 self.egg.durability.max_hp)
        ui.draw_toast_count(screen, fonts["ui"], self.stage.toast_count, self.stage.toast_total)

        guide = fonts["small"].render(
            "A/←:左へ移動   D/→:右へ移動   Space:ジャンプ   Esc:ポーズ", True, config.COLOR_TEXT)
        screen.blit(guide, (config.UI_MARGIN,
                            config.WINDOW_HEIGHT - config.UI_MARGIN - guide.get_height()))

    def draw_menu(self, title):
        if self.confirming:
            ui.draw_menu(self.screen, self.fonts, title, [label for _, label in CONFIRM_ITEMS],
                         self.menu_index, message="タイトルへ戻りますか?")
        else:
            ui.draw_menu(self.screen, self.fonts, title, [label for _, label in self.menu_items],
                         self.menu_index, message=self.message)

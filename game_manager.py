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

import pygame

import config
import physics
import ui
from camera import Camera
from debug import draw_debug
from player import Egg
from save_manager import SaveManager
from stage import Stage

logger = logging.getLogger("lost_egg")

STATE_TITLE = "TITLE"
STATE_STAGE_SELECT = "STAGE_SELECT"
STATE_PLAYING = "PLAYING"
STATE_PAUSED = "PAUSED"
STATE_GAME_OVER = "GAME_OVER"
STATE_STAGE_CLEAR = "STAGE_CLEAR"
STATE_GAME_CLEAR = "GAME_CLEAR"

# メニューの項目 (動作の名前, 表示する文字)
TITLE_ITEMS = [("start", "ゲーム開始"), ("select", "ステージ選択"), ("quit", "ゲーム終了")]
PAUSE_ITEMS = [("resume", "再開"), ("title", "タイトルへ戻る")]
GAME_OVER_ITEMS = [("checkpoint", "チェックポイントから再開"), ("title", "タイトルへ戻る")]
GAME_CLEAR_ITEMS = [("title", "タイトルへ戻る"), ("again", "もう一度プレイ")]
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
        if start_stage is None:
            self.go_to_title()
        else:
            self.load_stage(start_stage)

    # ---------- ステージの読み込み ----------
    def load_stage(self, number):
        """新しい物理空間にステージと卵を作り、最初から始める。"""
        self.space = physics.create_space()
        self.stage = Stage(self.space, number)
        self.egg = Egg(self.space, *self.stage.egg_start)
        physics.register_egg_collisions(self.space, self.egg.add_impact)
        physics.register_item_collisions(
            self.space, self.stage.on_toast_touched,
            self.stage.on_checkpoint_touched, self.stage.on_goal_touched)
        physics.register_spike_collisions(self.space, self.egg.add_spike_touch)
        self.camera = Camera(self.stage.width, self.stage.height)
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

    def respawn(self, from_checkpoint):
        """卵を復活させる。チェックポイント通過済みなら保存した状態へ、そうでなければステージの最初から。"""
        stage, egg = self.stage, self.egg
        used_checkpoint = from_checkpoint and stage.checkpoint_state is not None
        if used_checkpoint:
            state = stage.restore_checkpoint()
            egg.reset(state["x"], state["y"], state["hp"])
            self.camera.snap_to(state["x"], state["y"])   # 復活時はカメラも即座に移動
        else:
            stage.reset_progress()
            egg.reset(*stage.egg_start)
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
        self.space = self.stage = self.egg = self.camera = None
        self.state = STATE_TITLE
        self.menu_items = TITLE_ITEMS
        self.menu_index = index
        self.confirming = False
        self.message = ""
        self.accumulator = 0.0
        self.jump_requested = False
        self.steps = 0

    def open_stage_select(self):
        """ステージ選択画面を開く。カーソルは「次に挑戦するステージ」に置く。"""
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
                self.load_stage(number)
        elif key == pygame.K_ESCAPE:
            self.go_to_title(index=1)          # カーソルは「ステージ選択」に置く

    # ---------- メインループ ----------
    def run(self):
        while self.running:
            frame_time = min(self.clock.tick(config.FPS) / 1000.0, 0.25)  # 長い停止後の暴走防止
            for event in pygame.event.get():
                self.handle_event(event)
            self.update(frame_time)
            self.draw()
        pygame.quit()

    # ---------- 入力 ----------
    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.running = False
            return
        if event.type != pygame.KEYDOWN:
            return
        key = event.key

        if self.state == STATE_PLAYING:
            if key == pygame.K_ESCAPE:
                self.open_menu(STATE_PAUSED, PAUSE_ITEMS)
            elif key == pygame.K_SPACE:
                self.jump_requested = True
            elif key == pygame.K_F3:
                self.show_debug = not self.show_debug
            elif config.DEV_MODE and key == pygame.K_r:     # 開発用(exe版では無効)
                self.reset_requested = True
            elif config.DEV_MODE and key == pygame.K_k:     # 開発用(exe版では無効)
                self.egg.durability.hp = 0
            elif config.DEV_MODE and key == pygame.K_g:     # 開発用(exe版では無効)
                self.egg.body.position = (self.egg.body.position.x, self.stage.fall_limit + 50)
        elif self.state == STATE_STAGE_SELECT:
            self.handle_stage_select_key(key)
        elif self.state in (STATE_TITLE, STATE_PAUSED, STATE_GAME_OVER, STATE_GAME_CLEAR):
            self.handle_menu_key(key)
        # STATE_STAGE_CLEAR 中はキー入力を受け付けない

    def handle_menu_key(self, key):
        items = CONFIRM_ITEMS if self.confirming else self.menu_items
        if key == pygame.K_UP:
            self.menu_index = (self.menu_index - 1) % len(items)
        elif key == pygame.K_DOWN:
            self.menu_index = (self.menu_index + 1) % len(items)
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.activate(items[self.menu_index][0])
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
            self.load_stage(self.save.next_start_stage())    # 最も進んだ未クリアステージから
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
        elif action == "yes":
            self.go_to_title()
        elif action == "no":
            self.cancel_confirm()

    # ---------- 更新 ----------
    def update(self, frame_time):
        if self.state == STATE_PLAYING:
            self.update_playing(frame_time)
        elif self.state == STATE_STAGE_CLEAR:
            self.clear_timer -= frame_time
            if self.clear_timer <= 0.0:
                self.after_stage_clear()
        # PAUSED / GAME_OVER / GAME_CLEAR では何も進めない(物理・足場・カメラ・演出がすべて止まる)

    def update_playing(self, frame_time):
        egg, stage = self.egg, self.stage
        keys = pygame.key.get_pressed()
        move_dir = 0
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            move_dir -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            move_dir += 1

        # 固定時間ステップ: 描画とは別に、1/60秒ずつ物理を進める
        self.steps = 0
        self.accumulator += frame_time
        while self.accumulator >= config.PHYSICS_DT and self.steps < config.MAX_STEPS_PER_FRAME:
            egg.apply_controls(move_dir, self.jump_requested, config.PHYSICS_DT)
            self.jump_requested = False           # ジャンプ要求は最初の1ステップだけ有効
            stage.prepare_physics_step(config.PHYSICS_DT)   # 動く足場の速度を設定
            self.space.step(config.PHYSICS_DT)
            physics.limit_speed(egg.body, config.MAX_SPEED)
            egg.update_ground_state(config.PHYSICS_DT)
            egg.update_damage(config.PHYSICS_DT)
            stage.process_items(egg)
            stage.update(config.PHYSICS_DT)
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
            self.open_menu(STATE_GAME_OVER, GAME_OVER_ITEMS, message)
            return

        self.camera.update(
            egg.body.position.x, egg.body.position.y,
            egg.body.velocity.x, egg.body.velocity.y,
            frame_time,
        )

    def game_over_message(self):
        """ゲームオーバーの条件を満たしていれば、画面に出すメッセージを返す。満たさなければ空文字。"""
        if self.egg.durability.is_broken:
            return "卵が割れてしまった…"
        if self.egg.body.position.y > self.stage.fall_limit:
            return "落ちてしまった…"
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
            entries = [(f"ステージ {n}", self.save.status(n))
                       for n in range(1, config.LAST_STAGE + 1)]
            ui.draw_stage_select(screen, fonts, "ステージ選択", entries, self.menu_index,
                                 STAGE_SELECT_HINT)
            pygame.display.flip()
            return
        stage, egg, camera = self.stage, self.egg, self.camera

        stage.draw_background(screen, camera)
        stage.draw(screen, camera)
        egg.draw(screen, camera)
        stage.draw_popups(screen, camera, fonts["ui"])
        self.draw_hud()

        if self.state == STATE_PAUSED:
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
        label = f"STAGE {self.stage.number}" if self.stage.number > 0 else "TEST STAGE"
        screen.blit(fonts["ui"].render(label, True, config.COLOR_TEXT),
                    (config.UI_MARGIN, config.UI_MARGIN))
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
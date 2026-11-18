"""ゲームの起動点。段階7:動く足場・トゲ。

操作:
  A / ←  : 左へ移動
  D / →  : 右へ移動
  Space  : ジャンプ
  F3     : デバッグ表示の切替(起動時はOFF)
  R      : ステージを最初からやり直す(開発用。チェックポイントも解除)
  K      : 耐久度を0にする(開発用。ゲームオーバーの確認)
  G      : 卵を落下限界の下へ移す(開発用。落下ゲームオーバーの確認)
  Esc    : 終了
ゲームオーバー画面では ↑/↓ で選び、Enter で決定する。

起動方法:
  python main.py     : ステージ1
  python main.py 0   : 開発用テストステージ(動く足場・トゲの確認用)
"""

import sys

import pygame

import config
import physics
import ui
from camera import Camera
from debug import draw_debug
from player import Egg
from stage import Stage

STATE_PLAYING = "PLAYING"
STATE_GAME_OVER = "GAME_OVER"

GAME_OVER_ITEMS = ["チェックポイントから再開", "タイトルへ戻る"]
CONFIRM_ITEMS = ["はい", "いいえ"]
# 画面左下に常時表示する操作ガイド(Esc は段階8でポーズに変更する。それまでは終了)
CONTROLS_GUIDE = "A / ←:左移動   D / →:右移動   Space:ジャンプ   Esc:終了(仮)"


def respawn(egg, stage, camera, from_checkpoint):
    """卵を復活させる。

    from_checkpoint が True で、チェックポイントを通過済みなら、保存した状態(位置・耐久度・
    トーストの取得状態)に戻す。それ以外はステージの最初からやり直す。
    """
    if from_checkpoint and stage.checkpoint_state is not None:
        state = stage.restore_checkpoint()
        egg.reset(state["x"], state["y"], state["hp"])
        camera.snap_to(state["x"], state["y"])   # 復活時はカメラも即座に移動
    else:
        stage.reset_progress()
        egg.reset(*stage.egg_start)
        camera.snap_to(*stage.egg_start)


def check_game_over(egg, stage):
    """ゲームオーバーの条件を満たしていれば、画面に出すメッセージを返す。満たさなければ None。"""
    if egg.durability.is_broken:
        return "卵が割れてしまった…"
    if egg.body.position.y > stage.fall_limit:
        return "落ちてしまった…"
    return None


def main():
    pygame.init()
    screen = pygame.display.set_mode((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
    pygame.display.set_caption(config.WINDOW_TITLE)
    clock = pygame.time.Clock()
    fonts = ui.load_fonts()

    space = physics.create_space()
    stage_number = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    stage = Stage(space, stage_number)
    egg = Egg(space, *stage.egg_start)
    physics.register_egg_collisions(space, egg.add_impact)
    physics.register_item_collisions(space, stage.on_toast_touched, stage.on_checkpoint_touched)
    physics.register_spike_collisions(space, egg.add_spike_touch)
    camera = Camera(stage.width, stage.height)
    camera.snap_to(*stage.egg_start)

    state = STATE_PLAYING
    game_over_message = ""
    menu_index = 0
    confirming = False        # 「タイトルへ戻りますか?」の確認画面を出しているか
    show_debug = False        # デバッグ表示は通常OFF。F3で切り替える
    jump_requested = False
    accumulator = 0.0
    running = True
    steps = 0

    while running:
        frame_time = clock.tick(config.FPS) / 1000.0
        frame_time = min(frame_time, 0.25)  # 長い停止後の暴走防止

        # ---------- 入力イベント ----------
        reset_requested = False
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                continue
            if event.type != pygame.KEYDOWN:
                continue
            key = event.key

            if state == STATE_PLAYING:
                if key == pygame.K_ESCAPE:
                    running = False
                elif key == pygame.K_SPACE:
                    jump_requested = True
                elif key == pygame.K_F3:
                    show_debug = not show_debug
                elif key == pygame.K_r:
                    reset_requested = True
                elif key == pygame.K_k:
                    egg.durability.hp = 0   # 開発用
                elif key == pygame.K_g:
                    egg.body.position = (egg.body.position.x, stage.fall_limit + 50)  # 開発用

            elif state == STATE_GAME_OVER:
                items = CONFIRM_ITEMS if confirming else GAME_OVER_ITEMS
                if key == pygame.K_UP:
                    menu_index = (menu_index - 1) % len(items)
                elif key == pygame.K_DOWN:
                    menu_index = (menu_index + 1) % len(items)
                elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    if not confirming:
                        if menu_index == 0:      # チェックポイントから再開(未通過ならステージの最初から)
                            respawn(egg, stage, camera, from_checkpoint=True)
                            state = STATE_PLAYING
                            accumulator = 0.0
                            jump_requested = False
                        else:                    # タイトルへ戻る → 確認画面へ
                            confirming = True
                            menu_index = 1       # 誤操作防止のため「いいえ」を最初に選ぶ
                    else:
                        if menu_index == 0:      # はい(タイトル画面は段階8で作る。今はゲーム終了)
                            running = False
                        else:                    # いいえ
                            confirming = False
                            menu_index = 1
                elif key == pygame.K_ESCAPE and confirming:
                    confirming = False
                    menu_index = 1

        keys = pygame.key.get_pressed()
        move_dir = 0
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            move_dir -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            move_dir += 1

        # ---------- 更新(プレイ中だけ。ゲームオーバー中は物理もカメラも止まる) ----------
        steps = 0
        if state == STATE_PLAYING:
            accumulator += frame_time
            while accumulator >= config.PHYSICS_DT and steps < config.MAX_STEPS_PER_FRAME:
                egg.apply_controls(move_dir, jump_requested, config.PHYSICS_DT)
                jump_requested = False  # ジャンプ要求は最初の1ステップだけ有効
                stage.prepare_physics_step(config.PHYSICS_DT)   # 動く足場の速度を設定
                space.step(config.PHYSICS_DT)
                physics.limit_speed(egg.body, config.MAX_SPEED)
                egg.update_ground_state(config.PHYSICS_DT)
                egg.update_damage(config.PHYSICS_DT)
                stage.process_items(egg)
                stage.update(config.PHYSICS_DT)
                accumulator -= config.PHYSICS_DT
                steps += 1
                if check_game_over(egg, stage):
                    break
            if steps == config.MAX_STEPS_PER_FRAME:
                accumulator = 0.0  # 追いつけない分は捨てる

            if reset_requested:
                respawn(egg, stage, camera, from_checkpoint=False)
                accumulator = 0.0
            else:
                message = check_game_over(egg, stage)
                if message:
                    state = STATE_GAME_OVER
                    game_over_message = message
                    menu_index = 0
                    confirming = False
                    jump_requested = False

            if state == STATE_PLAYING:
                camera.update(
                    egg.body.position.x, egg.body.position.y,
                    egg.body.velocity.x, egg.body.velocity.y,
                    frame_time,
                )

        # ---------- 描画 ----------
        stage.draw_background(screen, camera)
        stage.draw(screen, camera)
        egg.draw(screen, camera)
        stage.draw_popups(screen, camera, fonts["ui"])
        ui.draw_stage_label(screen, fonts["ui"], stage.number)
        ui.draw_controls_guide(screen, fonts["ui"], CONTROLS_GUIDE)
        ui.draw_durability_gauge(screen, fonts["ui"], egg.durability.hp, egg.durability.max_hp)
        ui.draw_toast_count(screen, fonts["ui"], stage.toast_count, stage.toast_total)

        if state == STATE_GAME_OVER:
            if confirming:
                ui.draw_menu(screen, fonts, "GAME OVER", CONFIRM_ITEMS, menu_index,
                             message="タイトルへ戻りますか?")
            else:
                ui.draw_menu(screen, fonts, "GAME OVER", GAME_OVER_ITEMS, menu_index,
                             message=game_over_message)

        if show_debug:
            draw_debug(screen, fonts["debug"], egg, steps, clock.get_fps(), camera, state, stage)
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
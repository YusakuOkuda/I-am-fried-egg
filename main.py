"""ゲームの起動点。段階4:カメラ(縦横スクロール)。

操作:
  A / ←  : 左へ移動
  D / →  : 右へ移動
  Space  : ジャンプ
  F3     : デバッグ表示の切替
  R      : 卵を初期位置に戻す(開発用)
  Esc    : 終了
"""

import pygame

import config
import physics
from camera import Camera
from debug import draw_debug
from player import Egg
from stage import Stage


def main():
    pygame.init()
    screen = pygame.display.set_mode((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
    pygame.display.set_caption(config.WINDOW_TITLE)
    clock = pygame.time.Clock()
    font = pygame.font.Font(None, 26)

    space = physics.create_space()
    stage = Stage(space, 1)
    egg = Egg(space, *stage.egg_start)
    camera = Camera(stage.width, stage.height)
    camera.snap_to(*stage.egg_start)

    show_debug = True
    jump_requested = False
    accumulator = 0.0
    running = True

    while running:
        frame_time = clock.tick(config.FPS) / 1000.0
        frame_time = min(frame_time, 0.25)  # 長い停止後の暴走防止

        # ---------- 入力イベント ----------
        reset_requested = False
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_SPACE:
                    jump_requested = True
                elif event.key == pygame.K_F3:
                    show_debug = not show_debug
                elif event.key == pygame.K_r:
                    reset_requested = True

        keys = pygame.key.get_pressed()
        move_dir = 0
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            move_dir -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            move_dir += 1

        # ---------- 物理演算(固定ステップ) ----------
        accumulator += frame_time
        steps = 0
        while accumulator >= config.PHYSICS_DT and steps < config.MAX_STEPS_PER_FRAME:
            egg.apply_controls(move_dir, jump_requested, config.PHYSICS_DT)
            jump_requested = False  # ジャンプ要求は最初の1ステップだけ有効
            space.step(config.PHYSICS_DT)
            physics.limit_speed(egg.body, config.MAX_SPEED)
            egg.update_ground_state(config.PHYSICS_DT)
            accumulator -= config.PHYSICS_DT
            steps += 1
        if steps == config.MAX_STEPS_PER_FRAME:
            accumulator = 0.0  # 追いつけない分は捨てる

        if reset_requested or egg.body.position.y > stage.fall_limit:
            egg.reset(*stage.egg_start)
            camera.snap_to(*stage.egg_start)  # リセット時はカメラも即座に移動

        # ---------- カメラ ----------
        camera.update(
            egg.body.position.x, egg.body.position.y,
            egg.body.velocity.x, egg.body.velocity.y,
            frame_time,
        )

        # ---------- 描画 ----------
        stage.draw_background(screen, camera)
        stage.draw(screen, camera)
        egg.draw(screen, camera)
        screen.blit(
            font.render("A/D or Arrows: move   Space: jump   F3: debug   R: reset   Esc: quit",
                        True, config.COLOR_TEXT), (16, 12))
        if show_debug:
            draw_debug(screen, font, egg, steps, clock.get_fps(), camera)
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
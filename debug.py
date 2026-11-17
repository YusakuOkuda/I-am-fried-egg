"""デバッグ表示を担当するファイル(簡易版)。F3で表示切替。"""

import math

import pygame

import config


def draw_debug(surface, font, egg, steps_this_frame, fps, camera, game_state):
    body = egg.body
    durability = egg.durability

    # 当たり判定(物理上の多角形)を赤線で重ねる
    pygame.draw.polygon(surface, config.COLOR_DEBUG, egg.screen_vertices(camera), 1)

    lines = [
        f"state: {game_state}   FPS: {fps:.0f}   physics steps/frame: {steps_this_frame}",
        f"pos: ({body.position.x:.1f}, {body.position.y:.1f})",
        f"vel: ({body.velocity.x:.1f}, {body.velocity.y:.1f})",
        f"angle: {math.degrees(body.angle):.1f} deg   angvel: {body.angular_velocity:.2f}",
        f"grounded: {egg.grounded}   since_grounded: {min(egg.time_since_grounded, 9.99):.2f}s",
        f"ground normal: ({egg.ground_normal[0]:.2f}, {egg.ground_normal[1]:.2f})",
        f"camera: ({camera.x:.1f}, {camera.y:.1f})",
        f"hp: {durability.hp}/{durability.max_hp}   invincible: {durability.invincible_timer:.2f}s",
        f"last damage: {durability.last_event}",
        "dev keys: R reset / K hp=0 / G fall-limit test",
    ]
    y = 40
    for line in lines:
        surface.blit(font.render(line, True, config.COLOR_DEBUG), (16, y))
        y += 24
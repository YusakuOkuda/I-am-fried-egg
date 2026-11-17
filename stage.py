"""ステージデータを読み込み、物理空間への登録と描画を担当するファイル。"""

import pygame

import config
import physics
from stages import stage1

# ステージ番号とデータの対応(段階8で stage2, stage3 を追加する)
STAGE_DATA = {
    1: stage1.STAGE,
}


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
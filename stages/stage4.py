"""ステージ4: バネ床・動く足場・トゲを使うキッチンラッシュ。"""

from stages.helpers import moving_platform, rect, spikes, spring_pad

STAGE = {
    "name": "Kitchen Rush",
    "width": 4350,
    "height": 1250,
    "egg_start": (140, 1000),
    "fall_limit": 1530,
    "checkpoint": (2180, 1080),
    "goal": (4210, 1080),
    "sky_colors": ((205, 190, 229), (255, 221, 190)),
    "toasts": [
        (430, 1010),
        (1170, 1010),
        (2250, 1010),
        (2760, 860),
        (3690, 1010),
    ],
    "platforms": [
        rect(-40, -400, 40, 1600),
        rect(4350, -400, 40, 1600),
        rect(-40, 1080, 720, 120),
        rect(1010, 1080, 730, 120),
        rect(2070, 1080, 860, 120),
        rect(3270, 1080, 1080, 120),
        rect(2630, 900, 260, 20),
    ],
    "spring_pads": [
        spring_pad(485, 1060, 110, 20),
        spring_pad(1520, 1060, 110, 20),
        spring_pad(2640, 880, 100, 20),
        spring_pad(3520, 1060, 110, 20),
    ],
    "moving_platforms": [
        moving_platform(690, 990, 130, 24, direction=(1, 0), distance=190, speed=85),
        moving_platform(1760, 1030, 130, 24, direction=(1, 0), distance=230, speed=95),
        moving_platform(2940, 1000, 140, 24, direction=(1, 0), distance=260, speed=110),
    ],
    "spikes": (
        spikes(1120, 1080, 4)
        + spikes(2350, 1080, 4)
        + spikes(2790, 900, 3)
        + spikes(3390, 1080, 4)
    ),
}

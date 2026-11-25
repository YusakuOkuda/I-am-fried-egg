"""終わりのない上昇チャレンジ。足場はプレイ中に上へ追加生成される。"""

from stages.helpers import rect

STAGE = {
    "name": "Skybound - Endless Climb",
    "width": 1280,
    "height": 62000,
    "egg_start": (640, 59950),
    "fall_limit": 61000,
    "endless_climb": True,
    "sky_colors": ((100, 171, 215), (224, 243, 246)),
    "platforms": [
        rect(440, 60000, 400, 28),
    ],
}

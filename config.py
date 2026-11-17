"""ゲーム全体で使う定数をまとめるファイル。

数値を調整したいときは、基本的にこのファイルだけを編集する。
座標系は Pygame と同じ (左上が原点、Y軸は下向きが正)。
"""

# ---------- 画面 ----------
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720
FPS = 60
WINDOW_TITLE = "LOST EGG 2D"

# ---------- 色 (R, G, B) ----------
COLOR_BACKGROUND = (232, 244, 255)
COLOR_GRID = (215, 232, 248)        # 背景の格子(スクロール確認用)
COLOR_PLATFORM = (196, 214, 190)
COLOR_PLATFORM_EDGE = (120, 140, 115)
COLOR_EGG = (255, 255, 255)
COLOR_EGG_EDGE = (90, 90, 100)
COLOR_TEXT = (60, 60, 70)
COLOR_DEBUG = (200, 40, 40)

# ---------- 背景 ----------
GRID_SIZE = 160                     # 背景の格子の間隔(px)

# ---------- 物理演算の時間管理 ----------
PHYSICS_DT = 1 / 60          # 物理の1ステップの長さ(秒)。固定
MAX_STEPS_PER_FRAME = 5      # 1フレームで進める最大ステップ数(処理落ち対策)
GRAVITY = 1800.0             # 重力加速度 (px/秒^2)。下向きが正
MAX_SPEED = 1500.0           # 卵の最高速さ (px/秒)。足場のすり抜け防止

# ---------- 卵の形 ----------
EGG_WIDTH = 46
EGG_HEIGHT = 60
EGG_POLY_POINTS = 20
EGG_TAPER = 0.18

# ---------- 卵の物理特性 ----------
EGG_MASS = 1.0
EGG_FRICTION = 1.0           # 摩擦係数。大きいほど滑らず転がる
EGG_ELASTICITY = 0.0         # 反発係数。0で跳ねない
EGG_COG_OFFSET_Y = 6.0       # 重心を下側へずらす量(px)。大きいほど起き上がりやすい
PLATFORM_FRICTION = 1.0
PLATFORM_ELASTICITY = 0.0

# ---------- 左右移動 ----------
MOVE_ACCEL = 1400.0          # 地上での横方向の加速度 (px/秒^2)
MOVE_TORQUE_ACCEL = 40.0     # 地上での回転の加速度 (rad/秒^2)
MAX_MOVE_SPEED = 380.0       # 横方向の最高速度 (px/秒)
MAX_ANGULAR_SPEED = 18.0     # 最高の回転速度 (rad/秒)
ROLL_DAMPING = 0.6           # 入力なし・接地中の回転の減衰 (大きいほど早く止まる)

# ---------- 空中操作 ----------
AIR_CONTROL_RATIO = 0.25     # 空中での操作力は地上の何倍か (0.2~0.3が目安)

# ---------- ジャンプ・接地 ----------
JUMP_SPEED = 620.0           # ジャンプ直後の上向き速度 (px/秒)
COYOTE_TIME = 0.1            # 接地猶予時間(秒)
JUMP_LOCKOUT = 0.15          # ジャンプ直後に再ジャンプ・再接地を無視する時間(秒)
GROUND_NORMAL_MIN_Y = 0.5    # 接地とみなす面の傾き。0.5=約60度まで床扱い

# ---------- カメラ ----------
CAMERA_ANCHOR_Y = 420.0              # 卵を画面の上から何pxの高さに置くか(中央は360)
CAMERA_SMOOTH_X = 6.0                # 横の追従の速さ(大きいほど素早い)
CAMERA_SMOOTH_Y = 4.0                # 縦の追従の速さ
CAMERA_LOOKAHEAD_X = 0.25            # 横速度の何倍(秒)だけ進行方向を先読みするか
CAMERA_DEADZONE_Y = 90.0             # 縦のデッドゾーン(px)。この範囲の上下動では追従しない
CAMERA_FALL_LOOKAHEAD_START = 600.0  # この落下速度(px/秒)を超えたら下を先読みし始める
CAMERA_FALL_LOOKAHEAD = 0.25         # 超えた分の速度に掛ける係数
CAMERA_FALL_LOOKAHEAD_MAX = 200.0    # 先読みの最大量(px)
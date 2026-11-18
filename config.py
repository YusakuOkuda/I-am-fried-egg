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
COLOR_EGG_DAMAGE = (255, 90, 90)    # ダメージ点滅時の卵の色
COLOR_TEXT = (60, 60, 70)
COLOR_DEBUG = (200, 40, 40)
COLOR_TOAST = (232, 190, 120)
COLOR_TOAST_INNER = (248, 224, 170)
COLOR_TOAST_EDGE = (170, 120, 60)
COLOR_CHECKPOINT_POLE = (130, 130, 145)
COLOR_FLAG_INACTIVE = (185, 185, 195)   # 未通過の旗
COLOR_FLAG_ACTIVE = (90, 200, 120)      # 通過済みの旗
COLOR_POPUP = (210, 110, 20)            # 取得表示の文字色
COLOR_MOVING_PLATFORM = (170, 196, 230)       # 動く足場(固定足場と見分けるため青系)
COLOR_MOVING_PLATFORM_EDGE = (95, 120, 165)
COLOR_SPIKE = (225, 70, 70)                   # トゲ(危険物は赤系)
COLOR_SPIKE_EDGE = (150, 30, 30)
COLOR_PAN = (70, 70, 82)                      # フライパン(ゴール)
COLOR_PAN_INNER = (105, 105, 118)
COLOR_PAN_HANDLE = (150, 105, 70)

# ---------- 背景 ----------
GRID_SIZE = 160                     # 背景の格子の間隔(px)

# ---------- 物理演算の時間管理 ----------
PHYSICS_DT = 1 / 60          # 物理の1ステップの長さ(秒)。固定
MAX_STEPS_PER_FRAME = 5      # 1フレームで進める最大ステップ数(処理落ち対策)
GRAVITY = 1800.0             # 重力加速度 (px/秒^2)。下向きが正
MAX_SPEED = 1000.0           # 卵の最高速さ (px/秒)。1ステップで約17px進む。薄い足場(20px)のすり抜け防止

# ---------- 衝突の種類(Pymunkの collision_type) ----------
COLLISION_EGG = 1
COLLISION_PLATFORM = 2
COLLISION_TOAST = 3
COLLISION_CHECKPOINT = 4
COLLISION_SPIKE = 5
COLLISION_GOAL = 6

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

# ---------- 耐久度・ダメージ ----------
DURABILITY_MAX = 100                 # 最大耐久度
DURABILITY_START = 100               # 開始時の耐久度

# 着地ダメージ: 着地の瞬間の「面に向かう速さ」(px/秒)で決まる。落下距離は使わない
LANDING_DAMAGE_THRESHOLD = 700.0     # この速さ以下ならダメージなし(ジャンプの着地は約620)
LANDING_DAMAGE_PER_SPEED = 0.12      # 閾値を超えた分の速さ1(px/秒)あたりのダメージ

# 通常の衝突ダメージ: 壁・天井など「床ではない面」にぶつかった速さで決まる
COLLISION_DAMAGE_THRESHOLD = 520.0   # この速さ以下ならダメージなし(最高移動速度は380)
COLLISION_DAMAGE_PER_SPEED = 0.12

IMPACT_INVINCIBLE_TIME = 0.3         # 衝撃ダメージを受けた直後の無敵時間(秒)
DAMAGE_FLASH_TIME = 0.6              # ダメージ後に赤く点滅する時間(秒)
DAMAGE_FLASH_INTERVAL = 0.08         # 点滅の切り替え間隔(秒)

# ---------- ステージ進行・ゴール ----------
LAST_STAGE = 3                       # 最終ステージの番号
STAGE_CLEAR_WAIT = 3.0               # ステージクリア後、次のステージへ移るまでの待ち時間(秒)
GOAL_WIDTH = 90                      # フライパンの判定の幅(px)
GOAL_HEIGHT = 50                     # フライパンの判定の高さ(px)

# ---------- トゲ ----------
SPIKE_DAMAGE = 30                    # トゲに触れたときの固定ダメージ
SPIKE_INVINCIBLE_TIME = 0.8          # トゲのダメージ後の無敵時間(秒)。触れ続けるとこの間隔で再びダメージ

# ---------- トースト ----------
TOAST_HEAL = 10                      # 取得時の耐久度の回復量
TOAST_SIZE = 34                      # 見た目と判定の大きさ(px)
TOAST_POPUP_TIME = 1.0               # 取得表示を出す時間(秒)
TOAST_POPUP_RISE = 50                # 取得表示が上へ昇る距離(px)

# ---------- チェックポイント ----------
CHECKPOINT_POLE_HEIGHT = 120         # ポールの高さ(px)。判定の高さでもある
CHECKPOINT_WIDTH = 28                # 判定の幅(px)
CHECKPOINT_FLAG_WIDTH = 46           # 旗の横の長さ(px)
CHECKPOINT_FLAG_HEIGHT = 30          # 旗の縦の長さ(px)

# ---------- UI ----------
UI_MARGIN = 16
GAUGE_WIDTH = 220
GAUGE_HEIGHT = 22
COLOR_GAUGE_BG = (200, 205, 215)
COLOR_GAUGE_EDGE = (90, 90, 100)
COLOR_GAUGE_HIGH = (110, 200, 120)   # 耐久度50%超
COLOR_GAUGE_MID = (240, 200, 80)     # 25~50%
COLOR_GAUGE_LOW = (230, 80, 80)      # 25%未満
COLOR_MENU_OVERLAY = (20, 20, 30, 150)
COLOR_MENU_TITLE = (255, 255, 255)
COLOR_MENU_MESSAGE = (235, 235, 245)
COLOR_MENU_ITEM_BG = (90, 95, 115)
COLOR_MENU_ITEM_TEXT = (230, 230, 240)
COLOR_MENU_SELECTED_BG = (255, 255, 255)
COLOR_MENU_SELECTED_TEXT = (40, 40, 60)

# ---------- カメラ ----------
CAMERA_ANCHOR_Y = 420.0              # 卵を画面の上から何pxの高さに置くか(中央は360)
CAMERA_SMOOTH_X = 6.0                # 横の追従の速さ(大きいほど素早い)
CAMERA_SMOOTH_Y = 4.0                # 縦の追従の速さ
CAMERA_LOOKAHEAD_X = 0.25            # 横速度の何倍(秒)だけ進行方向を先読みするか
CAMERA_DEADZONE_Y = 90.0             # 縦のデッドゾーン(px)。この範囲の上下動では追従しない
CAMERA_FALL_LOOKAHEAD_START = 600.0  # この落下速度(px/秒)を超えたら下を先読みし始める
CAMERA_FALL_LOOKAHEAD = 0.25         # 超えた分の速度に掛ける係数
CAMERA_FALL_LOOKAHEAD_MAX = 200.0    # 先読みの最大量(px)
"""耐久度とダメージ計算を担当するファイル。

ダメージの計算ルールはすべてここに集める(数値は config.py)。
衝撃ダメージは「触れ始めた瞬間」の速さだけで決める。
"""

import logging
import math

import config

logger = logging.getLogger("lost_egg")

KIND_LANDING = "landing"      # 着地(床と判定される面に当たった)
KIND_COLLISION = "collision"  # 通常の衝突(壁・天井など)
KIND_SPIKE = "spike"          # トゲ(固定ダメージ)


def impact_damage(kind, speed):
    """衝撃の種類と速さ(px/秒)から、ダメージ量(整数)を計算する。閾値以下なら0。"""
    if kind == KIND_LANDING:
        threshold = config.LANDING_DAMAGE_THRESHOLD
        rate = config.LANDING_DAMAGE_PER_SPEED
    else:
        threshold = config.COLLISION_DAMAGE_THRESHOLD
        rate = config.COLLISION_DAMAGE_PER_SPEED
    if speed <= threshold:
        return 0
    return math.ceil((speed - threshold) * rate)


class Durability:
    """耐久度・無敵時間・赤点滅の状態を持つ。"""

    def __init__(self):
        self.max_hp = config.DURABILITY_MAX
        self.hp = config.DURABILITY_START
        self.invincible_timer = 0.0
        self.flash_timer = 0.0
        self.last_event = "-"   # デバッグ表示用(直近のダメージ判定の結果)

    def reset(self, hp=None):
        """耐久度を戻す。hp を省略すると開始時の値。チェックポイント再開では保存値を渡す。"""
        self.hp = config.DURABILITY_START if hp is None else min(hp, self.max_hp)
        self.invincible_timer = 0.0
        self.flash_timer = 0.0
        self.last_event = "-"

    @property
    def is_broken(self):
        return self.hp <= 0

    @property
    def is_invincible(self):
        return self.invincible_timer > 0.0

    @property
    def flash_on(self):
        """点滅中で、今が赤い側のタイミングなら True。"""
        if self.flash_timer <= 0.0:
            return False
        elapsed = config.DAMAGE_FLASH_TIME - self.flash_timer
        return int(elapsed / config.DAMAGE_FLASH_INTERVAL) % 2 == 0

    def update(self, dt):
        self.invincible_timer = max(0.0, self.invincible_timer - dt)
        self.flash_timer = max(0.0, self.flash_timer - dt)

    def heal(self, amount):
        """耐久度を回復する(最大値を超えない)。実際に回復した量を返す。"""
        before = self.hp
        self.hp = min(self.max_hp, self.hp + amount)
        return self.hp - before

    def take_damage(self, kind, speed, amount, invincible_time):
        """ダメージを与える。無敵中なら無効。ダメージが入ったら True。"""
        if amount <= 0:
            return False
        if self.is_invincible:
            self.last_event = f"{kind} speed={speed:.0f} dmg={amount} BLOCKED (invincible)"
            logger.debug("ダメージ無効(無敵中): 種類=%s 速度=%.0f ダメージ=%d", kind, speed, amount)
            return False
        self.hp = max(0, self.hp - amount)
        self.invincible_timer = invincible_time
        self.flash_timer = config.DAMAGE_FLASH_TIME
        self.last_event = f"{kind} speed={speed:.0f} dmg={amount} -> hp={self.hp}"
        logger.info("ダメージ: 種類=%s 速度=%.0f ダメージ=%d 耐久度=%d", kind, speed, amount, self.hp)
        return True
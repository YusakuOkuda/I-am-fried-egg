"""セーブ・ロードを担当するファイル。

保存するのは「クリア済みのステージ番号」だけ。
  - ステージの解放状況は、クリア状況から計算で求める(ステージ1は最初から解放、
    ステージNはステージN-1をクリアすると解放)。そのため、解放状況を別に保存しない。
  - トースト取得数や耐久度などは保存しない。

保存形式は JSON(テキストファイル)。例:
    {"version": 1, "cleared_stages": [1, 2]}

保存場所(Windows): %LOCALAPPDATA%\\LostEgg2D\\save.json
  ゲームの実行ファイル(exe)があるフォルダは、書き込みできない場合があるため使わない。

読み込みに失敗(ファイルが壊れている等)した場合は、初期状態で起動する。
  壊れたファイルは「save.json.corrupt-日時」という名前に変えて残し、エラーをログに記録する。
"""

import json
import logging
import os
import time
from pathlib import Path

import config

APP_FOLDER_NAME = "LostEgg2D"
SAVE_FILE_NAME = "save.json"
SAVE_VERSION = 1

logger = logging.getLogger("lost_egg")   # ログの出力先設定は第9段階で行う


def get_save_dir():
    """セーブデータを置くフォルダを返す。"""
    override = os.environ.get("LOST_EGG_SAVE_DIR")   # テスト・開発用に場所を変えられる
    if override:
        return Path(override)
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / APP_FOLDER_NAME
    return Path.home() / ".lost_egg_2d"              # Windows 以外(開発用)


class SaveManager:
    def __init__(self, save_dir=None):
        self.save_dir = Path(save_dir) if save_dir else get_save_dir()
        self.path = self.save_dir / SAVE_FILE_NAME
        self.cleared = set()      # クリア済みステージ番号の集合

    # ---------- 読み込み ----------
    def load(self):
        """セーブデータを読み込む。ファイルが無い・壊れている場合は初期状態にする。"""
        self.cleared = set()
        if not self.path.exists():
            logger.info("セーブデータなし。初期状態で開始します: %s", self.path)
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.cleared = self._parse(data)
            logger.info("セーブデータを読み込みました: クリア済み=%s", sorted(self.cleared))
        except Exception:   # 壊れたファイル、読み込み権限なし、など。何があってもゲームは起動させる
            logger.exception("セーブデータの読み込みに失敗しました。初期状態で開始します: %s", self.path)
            self.cleared = set()
            self._set_aside_broken_file()

    @staticmethod
    def _parse(data):
        """読み込んだ内容を検査して、クリア済みステージの集合にする。おかしければ例外を出す。"""
        if not isinstance(data, dict):
            raise ValueError("セーブデータの形式が不正です")
        stages = data.get("cleared_stages")
        if not isinstance(stages, list):
            raise ValueError("cleared_stages がありません")
        result = set()
        for stage in stages:
            if isinstance(stage, bool) or not isinstance(stage, int) \
                    or not 1 <= stage <= config.LAST_STAGE:
                raise ValueError(f"不正なステージ番号です: {stage!r}")
            result.add(stage)
        return result

    def _set_aside_broken_file(self):
        """壊れたセーブデータの名前を変えて退避する(次回起動で同じエラーを繰り返さないため)。"""
        backup = self.path.with_name(f"{SAVE_FILE_NAME}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}")
        try:
            os.replace(self.path, backup)
            logger.warning("壊れたセーブデータを退避しました: %s", backup)
        except OSError:
            logger.exception("壊れたセーブデータの退避に失敗しました")

    # ---------- 保存 ----------
    def save(self):
        """セーブデータを書き込む。成功したら True。失敗してもゲームは続ける(ログに記録する)。"""
        data = {"version": SAVE_VERSION, "cleared_stages": sorted(self.cleared)}
        temp_path = self.path.with_name(SAVE_FILE_NAME + ".tmp")
        try:
            self.save_dir.mkdir(parents=True, exist_ok=True)
            # いったん別ファイルに書いてから置き換える(書き込み途中で止まっても、元のデータを壊さない)
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, self.path)
            logger.info("セーブしました: クリア済み=%s", sorted(self.cleared))
            return True
        except OSError:
            logger.exception("セーブに失敗しました: %s", self.path)
            return False

    # ---------- クリア・解放の問い合わせ ----------
    def mark_cleared(self, stage_number):
        """ステージをクリア済みにして保存する(ステージクリア時に呼ぶ)。"""
        if 1 <= stage_number <= config.LAST_STAGE:
            self.cleared.add(stage_number)
            self.save()

    def is_cleared(self, stage_number):
        return stage_number in self.cleared

    def is_unlocked(self, stage_number):
        """ステージ1は最初から解放。ステージNは、ステージN-1をクリアすると解放。クリア済みなら当然解放済み。"""
        return (stage_number == 1
                or (stage_number - 1) in self.cleared
                or stage_number in self.cleared)

    def status(self, stage_number):
        """"cleared"(クリア済み) / "available"(挑戦可能) / "locked"(未解放) のどれかを返す。"""
        if self.is_cleared(stage_number):
            return "cleared"
        if self.is_unlocked(stage_number):
            return "available"
        return "locked"

    def next_start_stage(self):
        """「ゲーム開始」で始めるステージ。最も進んだ未クリアステージ。全部クリア済みならステージ1。"""
        for number in range(1, config.LAST_STAGE + 1):
            if number not in self.cleared:
                return number
        return 1
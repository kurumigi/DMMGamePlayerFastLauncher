import json
import logging
import traceback
from base64 import b64encode
from pathlib import Path
from typing import Callable

import customtkinter as ctk
import i18n
from component.component import CTkProgressWindow
from customtkinter import CTk
from lib.DGPSessionWrap import DgpSessionWrap
from lib.process_manager import ProcessManager
from lib.thread import threading_wrapper
from lib.toast import ErrorWindow
from models.setting_data import AppConfig
from models.shortcut_data import LauncherShortcutData, ShortcutData
from static.config import DataPathConfig
from static.env import Env
from tab.home import HomeTab


class GameLauncher(CTk):
    loder: Callable

    def __init__(self, loder):
        super().__init__()

        self.title("DMMGamePlayer Fast Launcher")
        self.geometry("900x600")
        self.withdraw()
        loder(self)

    def create(self):
        HomeTab(self).create().pack(expand=True, fill=ctk.BOTH)
        return self

    @threading_wrapper
    def thread(self, id: str):
        try:
            self.launch(id)
            self.quit()
        except Exception as e:
            if not Env.DEVELOP:
                self.iconify()
                ErrorWindow(self, str(e), traceback.format_exc(), quit=True).create()
            raise

    def launch(self, id: str):
        path = DataPathConfig.SHORTCUT.joinpath(id).with_suffix(".json")
        with open(path, "r", encoding="utf-8") as f:
            data = ShortcutData.from_dict(json.load(f))

        account_path = DataPathConfig.ACCOUNT.joinpath(data.account_path.get()).with_suffix(".bytes")
        session = DgpSessionWrap.read_cookies(account_path)

        dgp_config = session.get_config()
        game = [x for x in dgp_config["contents"] if x["productId"] == data.product_id.get()][0]

        response = session.lunch(data.product_id.get(), game["gameType"]).json()

        if response["result_code"] != 100:
            raise Exception(response["error"])

        if response["data"].get("drm_auth_token") is not None:
            filename = b64encode(data.product_id.get().encode("utf-8")).decode("utf-8")
            drm_path = Env.DMM_GAME_PLAYER_HIDDEN_FOLDER.joinpath(filename)
            drm_path.parent.mkdir(parents=True, exist_ok=True)
            with open(drm_path.absolute(), "w+") as f:
                f.write(response["data"]["drm_auth_token"])

        if not Env.DEVELOP:
            if response["data"]["is_administrator"] and not ProcessManager.admin_check():
                raise Exception(i18n.t("app.launch.admin_error"))

        game_file = Path(game["detail"]["path"])
        game_path = game_file.joinpath(response["data"]["exec_file_name"])

        if response["data"]["latest_version"] != game["detail"]["version"]:
            if data.auto_update.get():
                download = session.download(response["data"]["file_list_url"], game_file)
                box = CTkProgressWindow(self).create()
                for progress, file in download:
                    box.set(progress)
                box.destroy()
                game["detail"]["version"] = response["data"]["latest_version"]
                session.set_config(dgp_config)

        dmm_args = response["data"]["execute_args"].split(" ") + data.game_args.get().split(" ")

        process = ProcessManager.run([str(game_path.relative_to(game_file))] + dmm_args, cwd=str(game_file))
        assert process.stdout is not None

        for line in process.stdout:
            logging.debug(decode(line))


class LanchLauncher(CTk):
    loder: Callable

    def __init__(self, loder):
        super().__init__()

        self.title("DMMGamePlayer Fast Launcher")
        self.geometry("900x600")
        self.withdraw()
        loder(self)

    def create(self):
        HomeTab(self).create().pack(expand=True, fill=ctk.BOTH)
        return self

    @threading_wrapper
    def thread(self, id: str):
        try:
            self.launch(id)
            self.quit()
        except Exception as e:
            if not Env.DEVELOP:
                self.iconify()
                ErrorWindow(self, str(e), traceback.format_exc(), quit=True).create()
            raise

    def launch(self, id: str):
        path = DataPathConfig.ACCOUNT_SHORTCUT.joinpath(id).with_suffix(".json")
        with open(path, "r", encoding="utf-8") as f:
            data = LauncherShortcutData.from_dict(json.load(f))

        account_path = DataPathConfig.ACCOUNT.joinpath(data.account_path.get()).with_suffix(".bytes")

        with DgpSessionWrap() as session:
            session.read_bytes(str(account_path))
            if session.cookies.get("login_secure_id", **session.cookies_kwargs) is None:
                raise Exception(i18n.t("app.launch.export_error"))
            session.write()

        dgp = AppConfig.DATA.dmm_game_player_program_folder.get_path()

        dmm_args = data.dgp_args.get().split(" ")
        process = ProcessManager.run(["DMMGamePlayer.exe"] + dmm_args, cwd=str(dgp.absolute()))

        assert process.stdout is not None
        for line in process.stdout:
            logging.debug(decode(line))

        with DgpSessionWrap() as session:
            session.read()
            if session.cookies.get("login_secure_id", **session.cookies_kwargs) is None:
                raise Exception(i18n.t("app.launch.import_error"))
            session.write_bytes(str(account_path))

            session.cookies.clear()
            session.write()


def decode(s: bytes) -> str:
    try:
        return s.decode("utf-8").strip()
    except Exception:
        pass
    try:
        return s.decode("cp932").strip()
    except Exception:
        pass
    return str(s)

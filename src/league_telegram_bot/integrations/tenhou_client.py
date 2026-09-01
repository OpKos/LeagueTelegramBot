from urllib.parse import quote_plus, unquote

import requests


class TenhouClient:
    def __init__(self, lobby, game_type, is_enable):
        self.is_enable = is_enable
        self.lobby = lobby
        self.game_type = game_type
        self.start_game_url = "https://tenhou.net/cs/edit/cmd_start.cgi"
        self.get_players_url = "https://tenhou.net/cs/edit/cmd_get_players.cgi"

    def is_tenhou_client_enable(self):
        return self.is_enable

    def get_waited_players(self):
        """
        Send request to tenhou.net to get all waited players in lobby
        """
        url = self.get_players_url
        headers = {
            "Origin": "https://tenhou.net",
            "Content-Type": "text/plain;charset=UTF-8",
            "Referer": f"https://tenhou.net/cs/edit/?{self.lobby}",
            "User-agent": "Mozilla/5.0 (Linux; Android 8.0.0; BND-L34) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.66 Mobile Safari/537.36",
        }
        data = f"L={self.lobby}"
        try:
            response = requests.post(
                url,
                headers=headers,
                data=data,
                verify=False,
                timeout=10,
            )
            result = unquote(response.text)
            # 'IDLE=NoNameA,FrozenM&PLAY=...'
            waited_players = [
                x.strip()
                for x in result[result.index("IDLE=") + 5 : result.index("&PLAY")].split(",")
                if x
            ]
            return waited_players, True
        except Exception as e:
            return str(e), False

    def start_game(self, player_names):
        """
        Send request to tenhou.net to start a new game in the tournament lobby
        """
        url = self.start_game_url
        players = quote_plus("\r\n".join([x for x in player_names]))
        headers = {
            "Origin": "https://tenhou.net",
            "Content-Type": "text/plain;charset=UTF-8",
            "Referer": f"https://tenhou.net/cs/edit/?{self.lobby}",
            "User-agent": "Mozilla/5.0 (Linux; Android 8.0.0; BND-L34) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.66 Mobile Safari/537.36",
        }
        data = f"L={self.lobby}&R2={self.game_type}&M={players}&RND=default&WG=1&PW="
        try:
            response = requests.post(
                url,
                headers=headers,
                data=data,
                verify=False,
                timeout=10,
            )
            result = unquote(response.text)
            if result.startswith("FAILED"):
                return "FAILED", [], False
            elif result.startswith("MEMBER NOT FOUND"):
                missed_player_ids = [x for x in result.split("\r\n")[1:] if x]
                return "MEMBER NOT FOUND", missed_player_ids, False
            elif result.startswith("OK"):
                return "STARTED", [], True
        except Exception:
            return "EXCEPTION", [], False

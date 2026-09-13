"""
Endstone Bedrock plugin: Clans + Glow + Friendly-fire toggle
Target: Endstone Bedrock 1.26.45, Python 3.12 plugins
Files: manifest.json, main.py, data/config.json

Описание:
 - Команды: /clans, /clan <create|disband|invite|accept|leave|info|promote|demote|kick|glow|chat|pvp>
 - Поддержка glow (подсветка членов клана)
 - Friendly-fire (PvP внутри клана) можно выключать/включать через /clan pvp on|off
 - Хранение: data/clans.json и data/config.json (JSON)

Примечание: Endstone API может иметь небольшие отличия в названиях методов; при необходимости я подправлю адаптеры в _get_online_player, _send и применении эффектов.
"""

import json
import os
import traceback
from typing import Dict, Any

# Try to import Endstone API objects. If names differ adjust accordingly.
try:
    from endstone import Plugin, Command, events
except Exception:
    Plugin = object
    Command = object
    events = None

DATA_DIR_NAME = "data"
CLANS_FILE = "clans.json"
CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "tag_min_len": 2,
    "tag_max_len": 6,
    "name_min_len": 3,
    "default_clan_limit": 50,
    "glow_duration_ticks": 200,
    "default_friendly_fire": False
}


class ClansPlugin(Plugin):
    def on_load(self):
        try:
            self.logger.info("[Clans] Загружаю плагин кланов...")
        except Exception:
            pass

        base = os.path.dirname(__file__)
        self.data_dir = os.path.join(base, DATA_DIR_NAME)
        os.makedirs(self.data_dir, exist_ok=True)

        self.clans_path = os.path.join(self.data_dir, CLANS_FILE)
        self.config_path = os.path.join(self.data_dir, CONFIG_FILE)

        self._load_config()
        self._load_clans()

        self.player_glow_toggle: Dict[str, bool] = {}

        # Register commands
        try:
            self.register_command(Command(
                name="clan",
                description="Клановые команды",
                usage="/clan <subcommand>",
                executor=self.cmd_clan
            ))
            self.register_command(Command(
                name="clans",
                description="Список кланов",
                usage="/clans",
                executor=self.cmd_clans
            ))
        except Exception:
            try:
                self.logger.warning("[Clans] Не удалось зарегистрировать команды стандартно.")
            except Exception:
                pass

        # Register events
        if events:
            try:
                events.PlayerChatEvent.register(self.on_player_chat)
            except Exception:
                pass
            try:
                events.PlayerJoinEvent.register(self.on_player_join)
            except Exception:
                pass
            # Try to register damage event for friendly-fire handling
            try:
                events.EntityDamageByEntityEvent.register(self.on_entity_damage)
            except Exception:
                try:
                    events.PlayerDamageEvent.register(self.on_entity_damage)
                except Exception:
                    pass

        self.save_clans()
        try:
            self.logger.info("[Clans] Плагин кланов загружен.")
        except Exception:
            pass

    def _load_config(self):
        if not os.path.exists(self.config_path):
            with open(self.config_path, "w", encoding="utf8") as f:
                json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
            self.config = DEFAULT_CONFIG.copy()
            return
        try:
            with open(self.config_path, "r", encoding="utf8") as f:
                self.config = json.load(f)
        except Exception:
            self.config = DEFAULT_CONFIG.copy()

    def _load_clans(self):
        if not os.path.exists(self.clans_path):
            self.clans = {"clans": {}, "invites": {}}
            return
        try:
            with open(self.clans_path, "r", encoding="utf8") as f:
                self.clans = json.load(f)
        except Exception:
            self.clans = {"clans": {}, "invites": {}}

    def save_clans(self):
        try:
            with open(self.clans_path, "w", encoding="utf8") as f:
                json.dump(self.clans, f, ensure_ascii=False, indent=2)
        except Exception:
            try:
                self.logger.error("[Clans] Ошибка при сохранении данных кланов:\n" + traceback.format_exc())
            except Exception:
                pass

    # Helpers
    def _player_name(self, sender):
        try:
            p = getattr(sender, "get_player", None)
            if callable(p):
                player = p()
                if player:
                    return getattr(player, "get_name", lambda: None)() or getattr(player, "name", None)
        except Exception:
            pass
        try:
            return getattr(sender, "get_name", lambda: None)() or getattr(sender, "name", None)
        except Exception:
            return "console"

    def _get_online_player(self, name):
        try:
            srv = getattr(self, "server", None) or getattr(self, "get_server", lambda: None)()
            if srv:
                getter = getattr(srv, "get_player", None) or getattr(srv, "getPlayer", None)
                if callable(getter):
                    return getter(name)
        except Exception:
            pass
        return None

    def _send(self, target, message):
        try:
            send_method = getattr(target, "send_message", None) or getattr(target, "sendMessage", None)
            if callable(send_method):
                send_method(message)
                return
            p = self._get_online_player(target)
            if p:
                send_method = getattr(p, "send_message", None) or getattr(p, "sendMessage", None)
                if callable(send_method):
                    send_method(message)
        except Exception:
            try:
                self.logger.info(f"[Clans] {message}")
            except Exception:
                pass

    # Commands
    def cmd_clans(self, sender, label, args):
        try:
            clans = self.clans.get("clans", {})
            if not clans:
                self._send(sender, "§7Пока нет созданных кланов.")
                return True
            lines = ["§6Список кланов:"]
            for tag, data in clans.items():
                lines.append(f"§e[{tag}] §f{data.get('name','?')} §7({len(data.get('members',[]))}/{data.get('limit', self.config.get('default_clan_limit'))})")
            for l in lines:
                self._send(sender, l)
        except Exception:
            self._send(sender, "§cОшибка при выводе списка кланов.")
        return True

    def cmd_clan(self, sender, label, args):
        try:
            player_name = self._player_name(sender)
            if not args:
                self._send(sender, "§eИспользование: /clan <create|disband|invite|accept|leave|info|promote|demote|kick|glow|chat|pvp>")
                return True
            sub = args[0].lower()
            sub_args = args[1:]
            if sub == "create":
                return self._cmd_create(sender, player_name, sub_args)
            if sub == "disband":
                return self._cmd_disband(sender, player_name)
            if sub == "invite":
                return self._cmd_invite(sender, player_name, sub_args)
            if sub == "accept":
                return self._cmd_accept(sender, player_name, sub_args)
            if sub == "leave":
                return self._cmd_leave(sender, player_name)
            if sub == "info":
                return self._cmd_info(sender, player_name, sub_args)
            if sub == "promote":
                return self._cmd_promote(sender, player_name, sub_args)
            if sub == "demote":
                return self._cmd_demote(sender, player_name, sub_args)
            if sub == "kick":
                return self._cmd_kick(sender, player_name, sub_args)
            if sub == "glow":
                return self._cmd_glow(sender, player_name, sub_args)
            if sub == "chat":
                return self._cmd_chat(sender, player_name, sub_args)
            if sub == "pvp":
                return self._cmd_pvp(sender, player_name, sub_args)
            self._send(sender, "§cНеизвестная подкоманда.")
        except Exception:
            self._send(sender, "§cОшибка при обработке команды.")
            try:
                self.logger.error(traceback.format_exc())
            except Exception:
                pass
        return True

    # create/disband/invite/accept/leave/info/promote/demote/kick/glow/chat implementations (similar to earlier code)
    def _cmd_create(self, sender, player_name, args):
        if len(args) < 2:
            self._send(sender, "§eИспользование: /clan create <tag> <name>")
            return True
        tag = args[0].upper()
        name = " ".join(args[1:])
        if len(tag) < self.config.get("tag_min_len", 2) or len(tag) > self.config.get("tag_max_len", 6):
            self._send(sender, f"§cТег должен быть длиной {self.config.get('tag_min_len')}–{self.config.get('tag_max_len')} символов.")
            return True
        if len(name) < self.config.get("name_min_len", 3):
            self._send(sender, "§cНазвание слишком короткое.")
            return True
        clans = self.clans.setdefault("clans", {})
        if tag in clans:
            self._send(sender, "§cКлан с таким тегом уже существует.")
            return True
        if self._player_in_any_clan(player_name):
            self._send(sender, "§cВы уже состоите в клане.")
            return True
        clans[tag] = {
            "name": name,
            "leader": player_name,
            "officers": [],
            "members": [player_name],
            "limit": self.config.get("default_clan_limit", 50),
            "glow_enabled": False,
            "chat_enabled": False,
            "friendly_fire": self.config.get("default_friendly_fire", False)
        }
        self.save_clans()
        self._send(sender, f"§aКлан [{tag}] {name} успешно создан. Вы — лидер.")
        return True

    def _player_in_any_clan(self, player_name):
        for tag, data in self.clans.get("clans", {}).items():
            if player_name in data.get("members", []) or player_name == data.get("leader"):
                return tag
        return None

    def _cmd_disband(self, sender, player_name):
        tag = self._player_in_any_clan(player_name)
        if not tag:
            self._send(sender, "§cВы не состоите в клане.")
            return True
        clan = self.clans["clans"][tag]
        if clan.get("leader") != player_name:
            self._send(sender, "§cТолько лидер может распустить клан.")
            return True
        members = clan.get("members", [])[:]
        for m in members:
            p = self._get_online_player(m)
            if p:
                self._send(p, f"§cКлан [{tag}] был распущен лидером.")
        del self.clans["clans"][tag]
        self.save_clans()
        self._send(sender, "§aКлан распущен.")
        return True

    def _cmd_invite(self, sender, player_name, args):
        if len(args) < 1:
            self._send(sender, "§eИспользование: /clan invite <игрок>")
            return True
        target = args[0]
        tag = self._player_in_any_clan(player_name)
        if not tag:
            self._send(sender, "§cВы не состоите в клане.")
            return True
        clan = self.clans["clans"][tag]
        if player_name != clan.get("leader") and player_name not in clan.get("officers", []):
            self._send(sender, "§cТолько лидер или офицер может приглашать.")
            return True
        if target in clan.get("members", []) or target == clan.get("leader"):
            self._send(sender, "§cИгрок уже в вашем клане.")
            return True
        invites = self.clans.setdefault("invites", {})
        invites.setdefault(target, [])
        if tag in invites[target]:
            self._send(sender, "§eИгрок уже приглашён.")
            return True
        invites[target].append(tag)
        self.save_clans()
        self._send(sender, f"§aИгрок {target} приглашён в клан [{tag}].")
        p = self._get_online_player(target)
        if p:
            self._send(p, f"§eВас пригласили в клан [{tag}] {clan.get('name')}. Используйте §a/clan accept§e чтобы принять.")
        return True

    def _cmd_accept(self, sender, player_name, args):
        invites = self.clans.setdefault("invites", {})
        player_invites = invites.get(player_name, [])
        if not player_invites:
            self._send(sender, "§cУ вас нет приглашений.")
            return True
        tag = player_invites[0]
        clan = self.clans["clans"].get(tag)
        if not clan:
            self._send(sender, "§cКлан не найден.")
            invites[player_name].remove(tag)
            self.save_clans()
            return True
        if len(clan.get("members", [])) >= clan.get("limit", self.config.get("default_clan_limit")):
            self._send(sender, "§cКлан переполнен.")
            return True
        clan.setdefault("members", []).append(player_name)
        invites[player_name].remove(tag)
        self.save_clans()
        self._send(sender, f"§aВы вступили в клан [{tag}] {clan.get('name')}.")
        for m in clan.get("members", []):
            if m == player_name:
                continue
            p = self._get_online_player(m)
            if p:
                self._send(p, f"§e{player_name} присоединился к клану [{tag}].")
        if clan.get("glow_enabled"):
            self._apply_glow_to_clan(tag)
        return True

    def _cmd_leave(self, sender, player_name):
        tag = self._player_in_any_clan(player_name)
        if not tag:
            self._send(sender, "§cВы не состоите в клане.")
            return True
        clan = self.clans["clans"][tag]
        if clan.get("leader") == player_name:
            self._send(sender, "§cЛидер не может покинуть клан. Используйте /clan disband или передайте лидерство.")
            return True
        if player_name in clan.get("members", []):
            clan["members"].remove(player_name)
        if player_name in clan.get("officers", []):
            clan["officers"].remove(player_name)
        self.save_clans()
        self._send(sender, "§aВы вышли из клана.")
        leader_name = clan.get("leader")
        leader = self._get_online_player(leader_name)
        if leader:
            self._send(leader, f"§e{player_name} покинул клан [{tag}].")
        return True

    def _cmd_info(self, sender, player_name, args):
        target_tag = None
        if args:
            maybe = args[0]
            clan_of = self._player_in_any_clan(maybe)
            if clan_of:
                target_tag = clan_of
            else:
                target_tag = maybe.upper()
        else:
            target_tag = self._player_in_any_clan(player_name)
            if not target_tag:
                self._send(sender, "§eИспользование: /clan info <tag|игрок>")
                return True
        clan = self.clans["clans"].get(target_tag)
        if not clan:
            self._send(sender, "§cКлан не найден.")
            return True
        lines = [
            f"§6Информация о клане [{target_tag}]",
            f"§eНазвание: §f{clan.get('name')}",
            f"§eЛидер: §f{clan.get('leader')}",
            f"§eОфицеры: §f{', '.join(clan.get('officers',[]) ) or '—'}",
            f"§eЧлены ({len(clan.get('members',[]))}/{clan.get('limit')}): §f{', '.join(clan.get('members',[]) )}",
            f"§ePvP внутри клана: §f{ 'включено' if clan.get('friendly_fire') else 'выключено' }",
            f"§eGlow: §f{ 'включено' if clan.get('glow_enabled') else 'выключено' }"
        ]
        for l in lines:
            self._send(sender, l)
        return True

    def _cmd_promote(self, sender, player_name, args):
        if len(args) < 1:
            self._send(sender, "§eИспользование: /clan promote <игрок>")
            return True
        target = args[0]
        tag = self._player_in_any_clan(player_name)
        if not tag:
            self._send(sender, "§cВы не состоите в клане.")
            return True
        clan = self.clans["clans"][tag]
        if clan.get("leader") != player_name:
            self._send(sender, "§cТолько лидер может повышать.")
            return True
        if target not in clan.get("members", []):
            self._send(sender, "§cИгрок не в клане.")
            return True
            }],
from __future__ import annotations

import contextlib
import logging
import re

import discord
from discord.ext import commands, tasks
from discord.utils import get as discord_get

from europython_discord.tutorials.config import TutorialsConfig
from europython_discord.tutorials.tutorial import Tutorial, load_tutorials

_logger = logging.getLogger(__name__)

MANAGE_BUTTON_ID = "tutorials:manage"
EMBED_COLOR = 0xB42A34
WARNING_COLOR = 0xF1C40F
EMBED_DESCRIPTION_LIMIT = 4000  # Discord's hard limit is 4096
PANEL_TITLE = "Tutorials registration"
FOOTER_ID_PREFIX = "ID: "
USER_LINE = re.compile(r"^- (?P<name>.*) \(`(?P<id>\d+)`\)$", re.MULTILINE)
WARNING_TITLE = "⚠️ DO NOT EDIT OR DELETE THE MESSAGES IN THIS CHANNEL ⚠️"
WARNING_TEXT = (
    "🛑 The bot **stores the tutorials registrations in these messages**.\n"
    "🗑️ Deleting or editing them **permanently removes people's registrations**.\n"
    "🔄 They are rebuilt automatically each time the bot restarts.\n"
    "👀 Please only read them."
)


class RegistrationStore:
    """In-memory registrations.

    Nothing is written to disk: the report channel is the persistent storage (each
    registered user is listed there as ``username (`user id`)``), and it is read
    back when the bot starts, see ``TutorialsCog._restore_registrations``.
    """

    def __init__(self) -> None:
        # tutorial id -> {user id (str) -> username}
        self.registrations: dict[str, dict[str, str]] = {}

    def registered_ids(self, user_id: int) -> set[str]:
        return {tid for tid, users in self.registrations.items() if str(user_id) in users}

    def set_user_registrations(self, user: discord.abc.User, tutorial_ids: set[str]) -> None:
        for tid in {*self.registrations, *tutorial_ids}:
            users = self.registrations.setdefault(tid, {})
            if tid in tutorial_ids:
                users[str(user.id)] = user.name
            else:
                users.pop(str(user.id), None)


def build_tutorials_embed(tutorials: list[Tutorial], registered: set[str]) -> discord.Embed:
    embed = discord.Embed(
        title="Tutorials",
        description=(
            "Pick the tutorials you want to attend in the menu below. "
            "Deselect a tutorial to unregister.\n"
            "🕒 Times are displayed in **your local timezone**."
        ),
        color=EMBED_COLOR,
    )
    for t in tutorials:
        mark = "✅" if t.id in registered else "▫️"
        embed.add_field(
            name=f"{mark} {t.title}",
            value=f"{t.local_time}\n{t.presenters_text}\n[Details]({t.url})",
            inline=False,
        )
    return embed


class TutorialSelect(discord.ui.Select):
    def __init__(self, cog: TutorialsCog, registered: set[str]) -> None:
        options = [
            discord.SelectOption(
                label=t.title[:100],
                value=t.id,
                description=t.presenters_text[:100],
                default=t.id in registered,
            )
            for t in cog.tutorials
        ]
        super().__init__(
            placeholder="Select the tutorials you want to attend",
            min_values=0,
            max_values=len(options),
            options=options,
        )
        self.cog = cog

    async def callback(self, interaction: discord.Interaction) -> None:
        selected = set(self.values)
        self.cog.store.set_user_registrations(interaction.user, selected)
        self.cog.report_dirty = True
        view: ManageView = self.view
        view.interaction = interaction
        view.show(selected)
        await interaction.response.edit_message(
            embed=build_tutorials_embed(self.cog.tutorials, selected), view=view
        )


class ManageView(discord.ui.View):
    """Ephemeral view, one per user: the select menu with their current registrations."""

    # Shorter than the 15 minutes Discord keeps an interaction token valid, so the
    # message can still be edited when the view times out
    TIMEOUT = 14 * 60

    def __init__(self, cog: TutorialsCog, registered: set[str]) -> None:
        super().__init__(timeout=self.TIMEOUT)
        self.cog = cog
        # The latest interaction on this message, used to edit it on timeout
        self.interaction: discord.Interaction | None = None
        self.show(registered)

    def show(self, registered: set[str]) -> None:
        self.clear_items()
        self.add_item(TutorialSelect(self.cog, registered))

    async def on_timeout(self) -> None:
        if self.interaction is None:
            return
        embed = discord.Embed(
            title="This menu has expired",
            description="Click **Manage my tutorials** again to see or change your registrations.",
            color=EMBED_COLOR,
        )
        try:
            await self.interaction.edit_original_response(embed=embed, view=None)
        except discord.HTTPException:
            _logger.debug("Could not replace the expired tutorials menu")


class PanelView(discord.ui.View):
    """Persistent view attached to the message in the registration channel."""

    def __init__(self, cog: TutorialsCog) -> None:
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Manage my tutorials",
        emoji="🎟️",
        style=discord.ButtonStyle.primary,
        custom_id=MANAGE_BUTTON_ID,
    )
    async def manage(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        registered = self.cog.store.registered_ids(interaction.user.id)
        view = ManageView(self.cog, registered)
        view.interaction = interaction
        await interaction.response.send_message(
            embed=build_tutorials_embed(self.cog.tutorials, registered), view=view, ephemeral=True
        )


class TutorialsCog(commands.Cog):
    def __init__(self, bot: commands.Bot, config: TutorialsConfig) -> None:
        self.bot: commands.Bot = bot
        self.config = config
        self.tutorials = load_tutorials(config.tutorials_file)
        self.store = RegistrationStore()
        self.report_dirty = True
        self.report_message_ids: dict[str, int] = {}
        self._started = False
        _logger.info(
            "Cog 'TutorialsCog' has been initialized with %d tutorials", len(self.tutorials)
        )

    async def cog_load(self) -> None:
        # Makes the button of the panel message keep working after a restart
        self.bot.add_view(PanelView(self))

    async def cog_unload(self) -> None:
        self.refresh_report.cancel()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        # on_ready is also triggered after reconnecting, only start once
        if self._started:
            return
        self._started = True
        await self._ensure_panel()
        await self._restart_report()
        self.refresh_report.start()

    async def _ensure_panel(self) -> None:
        channel = discord_get(
            self.bot.get_all_channels(), name=self.config.registration_channel_name
        )
        if channel is None:
            _logger.error("Tutorials channel %r not found", self.config.registration_channel_name)
            return

        embed = discord.Embed(
            title=PANEL_TITLE,
            description=(
                "Click the button below to see all the tutorials, register to the ones you "
                "want to attend, or unregister if you can no longer make it.\n\n"
                "🕒 Dates and times are shown in **your local timezone**."
            ),
            color=EMBED_COLOR,
        )
        view = PanelView(self)

        async for message in channel.history(limit=100):
            if message.author == self.bot.user and any(
                e.title == PANEL_TITLE for e in message.embeds
            ):
                await message.edit(embed=embed, view=view)
                return
        await channel.send(embed=embed, view=view)

    async def _restart_report(self) -> None:
        """Restore the registrations from the report channel, then post a fresh report.

        The old report messages are deleted only after the new ones are sent, so the
        registrations are never only in memory.
        """
        channel = discord_get(self.bot.get_all_channels(), name=self.config.report_channel_name)
        if channel is None:
            _logger.error("Tutorials report channel %r not found", self.config.report_channel_name)
            return

        old_messages = [
            m
            async for m in channel.history(limit=None)  # newest first
            if m.author == self.bot.user and m.embeds
        ]
        self._restore_registrations(old_messages)

        await channel.send(
            embed=discord.Embed(title=WARNING_TITLE, description=WARNING_TEXT, color=WARNING_COLOR)
        )
        await self._update_report(channel, send_new=True)
        for message in old_messages:
            with contextlib.suppress(discord.NotFound):
                await message.delete()
        self.report_dirty = False

    def _restore_registrations(self, messages: list[discord.Message]) -> None:
        known = {t.id for t in self.tutorials}
        restored: set[str] = set()
        for message in messages:  # newest first, an older duplicate never overrides a newer one
            footer = message.embeds[0].footer.text or ""
            if not footer.startswith(FOOTER_ID_PREFIX):
                continue
            tutorial_id = footer.removeprefix(FOOTER_ID_PREFIX).split(" · ")[0]
            if tutorial_id not in known or tutorial_id in restored:
                continue
            restored.add(tutorial_id)
            users = self.store.registrations.setdefault(tutorial_id, {})
            for embed in message.embeds:
                for match in USER_LINE.finditer(embed.description or ""):
                    users[match["id"]] = match["name"]
        _logger.info("Restored the registrations of %d tutorials from the report", len(restored))

    def _report_embeds(self, tutorial: Tutorial) -> list[discord.Embed]:
        """Build the report of a tutorial, split in several embeds if the list is very long."""
        registered = self.store.registrations.get(tutorial.id, {})
        users = sorted(registered.items(), key=lambda u: u[1].lower())
        chunks: list[list[str]] = [[]]
        length = 0
        for user_id, name in users:
            line = f"- {name} (`{user_id}`)"
            if length + len(line) + 1 > EMBED_DESCRIPTION_LIMIT:
                chunks.append([])
                length = 0
            chunks[-1].append(line)
            length += len(line) + 1

        embeds = []
        for i, chunk in enumerate(chunks):
            lines = [f"**Total registered: {len(users)}**", ""] if i == 0 else []
            embed = discord.Embed(
                title=tutorial.title if i == 0 else None,
                description="\n".join(lines + chunk),
                url=tutorial.url if i == 0 else None,
                color=EMBED_COLOR,
            )
            if i == 0:
                embed.set_footer(
                    text=f"{FOOTER_ID_PREFIX}{tutorial.id} · {tutorial.presenters_text}"
                    f" · {tutorial.date:%Y-%m-%d %H:%M %z}"
                )
            embeds.append(embed)
        return embeds

    async def _update_report(
        self, channel: discord.abc.Messageable, *, send_new: bool = False
    ) -> None:
        for tutorial in self.tutorials:
            embeds = self._report_embeds(tutorial)
            message_id = self.report_message_ids.get(tutorial.id)
            if message_id and not send_new:
                try:
                    await channel.get_partial_message(message_id).edit(embeds=embeds)
                    continue
                except discord.NotFound:
                    _logger.warning("Report message for %r disappeared", tutorial.id)
            message = await channel.send(embeds=embeds)
            self.report_message_ids[tutorial.id] = message.id

    @tasks.loop(seconds=10)
    async def refresh_report(self) -> None:
        """Keep one message per tutorial in the report channel up to date."""
        if not self.report_dirty:
            return
        channel = discord_get(self.bot.get_all_channels(), name=self.config.report_channel_name)
        if channel is None:
            return

        self.report_dirty = False
        try:
            await self._update_report(channel)
        except discord.HTTPException:
            _logger.exception("Failed to update the tutorials report, will retry")
            self.report_dirty = True

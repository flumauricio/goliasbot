import logging

import discord
from discord.ext import commands

from config_manager import ConfigManager
from db import Database


LOGGER = logging.getLogger(__name__)


async def _ask(ctx: commands.Context, prompt: str) -> str:
    await ctx.send(prompt)

    def check(msg: discord.Message) -> bool:
        return msg.author == ctx.author and msg.channel == ctx.channel

    msg = await ctx.bot.wait_for("message", check=check, timeout=120)
    return msg.content.strip()


class SetupCog(commands.Cog):
    def __init__(self, bot: commands.Bot, db: Database, config: ConfigManager):
        self.bot = bot
        self.db = db
        self.config = config

    @commands.command(name="setup")
    @commands.has_permissions(administrator=True)
    async def interactive_setup(self, ctx: commands.Context):
        guild = ctx.guild
        if not guild:
            await ctx.reply("Use este comando em um servidor.")
            return

        settings = self.db.get_settings(guild.id)
        channels_cfg = self.config.guild_channels(guild.id)
        roles_cfg = self.config.guild_roles(guild.id)

        def current(key: str, default_section: dict) -> str:
            val = settings.get(key)
            if val is None or str(val).strip() == "":
                val = default_section.get(key.replace("channel_", ""))
            return str(val).strip() if val else ""

        needed_prompts = [
            ("channel_registration_embed", "Informe o ID do canal para a embed de cadastro (!set):", channels_cfg),
            ("channel_welcome", "Informe o ID do canal de boas-vindas:", channels_cfg),
            ("channel_warnings", "Informe o ID do canal de advertências:", channels_cfg),
            ("channel_leaves", "Informe o ID do canal de saídas:", channels_cfg),
            ("channel_approval", "Informe o ID do canal de aprovação:", channels_cfg),
            ("channel_records", "Informe o ID do canal de registros (aprovados):", channels_cfg),
            ("role_set", "Informe o ID do cargo SET (atribuído ao entrar):", roles_cfg),
            ("role_member", "Informe o ID do cargo Membro (após aprovação):", roles_cfg),
            ("role_adv1", "Informe o ID do cargo ADV 1:", roles_cfg),
            ("role_adv2", "Informe o ID do cargo ADV 2:", roles_cfg),
        ]

        collected = {}
        try:
            for key, prompt, section in needed_prompts:
                existing = current(key, section)
                if existing:
                    collected[key] = existing
                    continue
                answer = await _ask(ctx, prompt)
                collected[key] = answer.strip()
        except TimeoutError:
            await ctx.reply("Tempo esgotado. Rode !setup novamente.")
            return

        self.db.upsert_settings(
            guild.id,
            channel_registration_embed=int(collected["channel_registration_embed"]),
            channel_welcome=int(collected["channel_welcome"]),
            channel_warnings=int(collected["channel_warnings"]),
            channel_leaves=int(collected["channel_leaves"]),
            channel_approval=int(collected["channel_approval"]),
            channel_records=int(collected["channel_records"]),
            role_set=int(collected["role_set"]),
            role_member=int(collected["role_member"]),
            role_adv1=int(collected["role_adv1"]),
            role_adv2=int(collected["role_adv2"]),
        )

        self.config.set_guild_value(
            guild.id, "channels", "registration_embed", collected["channel_registration_embed"]
        )
        self.config.set_guild_value(guild.id, "channels", "welcome", collected["channel_welcome"])
        self.config.set_guild_value(guild.id, "channels", "warnings", collected["channel_warnings"])
        self.config.set_guild_value(guild.id, "channels", "leaves", collected["channel_leaves"])
        self.config.set_guild_value(guild.id, "channels", "approval", collected["channel_approval"])
        self.config.set_guild_value(guild.id, "channels", "records", collected["channel_records"])
        self.config.set_guild_value(guild.id, "roles", "set", collected["role_set"])
        self.config.set_guild_value(guild.id, "roles", "member", collected["role_member"])
        self.config.set_guild_value(guild.id, "roles", "adv1", collected["role_adv1"])
        self.config.set_guild_value(guild.id, "roles", "adv2", collected["role_adv2"])

        await ctx.reply("Configurações salvas/atualizadas para este servidor (apenas campos faltantes foram solicitados).")

    @commands.command(name="setup_cargos")
    @commands.has_permissions(administrator=True)
    async def setup_roles_for_commands(self, ctx: commands.Context):
        """Configura quais cargos podem usar cada comando do bot (por servidor)."""
        guild = ctx.guild
        if not guild:
            await ctx.reply("Use este comando em um servidor.")
            return

        # Comandos configuráveis: todos os comandos públicos, exceto setup/setup_cargos
        configurable = [
            cmd for cmd in self.bot.commands
            if not cmd.hidden and cmd.name not in ("setup", "setup_cargos")
        ]
        if not configurable:
            await ctx.reply("Nenhum comando configurável encontrado.")
            return

        await ctx.send(
            "Configuração de cargos por comando.\n"
            "Para cada comando, responda com:\n"
            "- `0` para apenas administradores\n"
            "- menções de cargos (`@Cargo1 @Cargo2`) ou IDs separados por vírgula\n"
            "- deixe em branco para manter a configuração atual\n"
            "Digite `cancel` a qualquer momento para cancelar."
        )

        def msg_check(m: discord.Message) -> bool:
            return m.author == ctx.author and m.channel == ctx.channel

        for command in configurable:
            current_roles = self.db.get_command_permissions(guild.id, command.name)
            texto_atual = "apenas administradores (padrão)"
            if current_roles:
                if current_roles.strip() == "0":
                    texto_atual = "apenas administradores"
                else:
                    ids = [rid for rid in current_roles.split(",") if rid.strip()]
                    mentions = []
                    for rid in ids:
                        role = guild.get_role(int(rid))
                        if role:
                            mentions.append(role.mention)
                    texto_atual = ", ".join(mentions) if mentions else current_roles

            await ctx.send(
                f"Comando: `!{command.name}`\n"
                f"Atual: {texto_atual}\n"
                "Responda agora com 0 / cargos / IDs / vazio para manter:"
            )

            try:
                resp = await self.bot.wait_for("message", check=msg_check, timeout=180)
            except TimeoutError:
                await ctx.reply("Tempo esgotado em setup_cargos. Processo encerrado.")
                return

            content = resp.content.strip()
            if content.lower() == "cancel":
                await ctx.reply("setup_cargos cancelado.")
                return

            # Vazio -> mantém configuração existente
            if not content and current_roles is not None:
                continue

            # Apenas admin
            if content == "0":
                self.db.set_command_permissions(guild.id, command.name, "0")
                continue

            role_ids = set()
            # Primeiro tenta pegar pelas menções
            for role in resp.role_mentions:
                role_ids.add(str(role.id))

            if not role_ids:
                # Tenta por IDs numéricos separados por vírgula ou espaço
                parts = [p.strip() for p in content.replace(",", " ").split() if p.strip()]
                for part in parts:
                    if part.isdigit():
                        role_ids.add(part)

            if not role_ids:
                await ctx.send(
                    "Não encontrei cargos válidos na resposta. Pulando este comando (mantida configuração atual)."
                )
                continue

            self.db.set_command_permissions(guild.id, command.name, ",".join(sorted(role_ids)))

        # Resumo final
        perms = self.db.list_command_permissions(guild.id)
        if not perms:
            await ctx.reply("Nenhuma permissão de comando foi configurada.")
            return

        embed = discord.Embed(
            title="Permissões de comandos configuradas",
            color=discord.Color.blurple(),
        )
        for item in perms:
            name = item["command_name"]
            role_ids = item["role_ids"].strip()
            if role_ids == "0" or not role_ids:
                desc = "Apenas administradores"
            else:
                ids = [rid for rid in role_ids.split(",") if rid.strip()]
                mentions = []
                for rid in ids:
                    role = guild.get_role(int(rid))
                    if role:
                        mentions.append(role.mention)
                desc = ", ".join(mentions) if mentions else role_ids
            embed.add_field(name=f"!{name}", value=desc, inline=False)

        await ctx.reply(embed=embed)


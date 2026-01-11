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
        """Configura os canais e cargos do servidor através de um wizard interativo."""
        guild = ctx.guild
        if not guild:
            await ctx.reply("Use este comando em um servidor.")
            return

        settings = await self.db.get_settings(guild.id)

        def current(key: str) -> str:
            """Retorna o valor atual de uma configuração do banco de dados."""
            val = settings.get(key)
            return str(val).strip() if val else ""

        needed_prompts = [
            ("channel_registration_embed", "Informe o ID do canal para a embed de cadastro (!set):"),
            ("channel_welcome", "Informe o ID do canal de boas-vindas:"),
            ("channel_warnings", "Informe o ID do canal de advertências:"),
            ("channel_leaves", "Informe o ID do canal de saídas:"),
            ("channel_approval", "Informe o ID do canal de aprovação:"),
            ("channel_records", "Informe o ID do canal de registros (aprovados):"),
            ("role_set", "Informe o ID do cargo SET (atribuído ao entrar):"),
            ("role_member", "Informe o ID do cargo Membro (após aprovação):"),
            ("role_adv1", "Informe o ID do cargo ADV 1:"),
            ("role_adv2", "Informe o ID do cargo ADV 2:"),
        ]

        def validate_id(value: str, field_name: str) -> int:
            """Valida se o valor é um ID numérico válido."""
            value = value.strip()
            if not value:
                raise ValueError(f"ID não pode estar vazio para {field_name}")
            if not value.isdigit():
                raise ValueError(f"ID inválido para {field_name}: '{value}' não é um número. Por favor, forneça apenas números.")
            return int(value)

        async def validate_channel_id(channel_id: int, field_name: str) -> None:
            """Valida se o ID do canal existe e o bot tem permissões necessárias."""
            channel = guild.get_channel(channel_id)
            if not channel:
                raise ValueError(f"Canal com ID `{channel_id}` não encontrado no servidor ({field_name}).")
            
            if not isinstance(channel, discord.TextChannel):
                raise ValueError(f"O ID `{channel_id}` não pertence a um canal de texto ({field_name}).")
            
            # Verifica permissões do bot
            bot_member = guild.me
            permissions = channel.permissions_for(bot_member)
            missing_perms = []
            
            if not permissions.view_channel:
                missing_perms.append("visualizar o canal")
            if not permissions.send_messages:
                missing_perms.append("enviar mensagens")
            if not permissions.embed_links:
                missing_perms.append("enviar embeds")
            
            if missing_perms:
                raise ValueError(
                    f"O bot não tem permissões suficientes no canal {channel.mention} ({field_name}): "
                    f"{', '.join(missing_perms)}. "
                    f"Verifique as permissões do bot neste canal."
                )

        collected = {}
        try:
            for key, prompt in needed_prompts:
                existing = current(key)
                if existing:
                    collected[key] = existing
                    continue
                answer = await _ask(ctx, prompt)
                collected[key] = answer.strip()
        except TimeoutError:
            await ctx.reply("Tempo esgotado. Rode !setup novamente.")
            return

        # Valida todos os IDs antes de salvar
        try:
            validated = {}
            
            # Valida e verifica canais
            channel_fields = [
                ("channel_registration_embed", "canal de cadastro"),
                ("channel_welcome", "canal de boas-vindas"),
                ("channel_warnings", "canal de advertências"),
                ("channel_leaves", "canal de saídas"),
                ("channel_approval", "canal de aprovação"),
                ("channel_records", "canal de registros"),
            ]
            
            for key, field_name in channel_fields:
                channel_id = validate_id(collected[key], field_name)
                await validate_channel_id(channel_id, field_name)
                validated[key] = channel_id
            
            # Valida cargos (apenas verifica se é número, não verifica existência)
            role_fields = [
                ("role_set", "cargo SET"),
                ("role_member", "cargo Membro"),
                ("role_adv1", "cargo ADV 1"),
                ("role_adv2", "cargo ADV 2"),
            ]
            
            for key, field_name in role_fields:
                validated[key] = validate_id(collected[key], field_name)
                
        except ValueError as e:
            await ctx.reply(f"❌ Erro de validação: {str(e)}\nPor favor, rode !setup novamente e forneça IDs válidos.")
            return

        await self.db.upsert_settings(
            guild.id,
            channel_registration_embed=validated["channel_registration_embed"],
            channel_welcome=validated["channel_welcome"],
            channel_warnings=validated["channel_warnings"],
            channel_leaves=validated["channel_leaves"],
            channel_approval=validated["channel_approval"],
            channel_records=validated["channel_records"],
            role_set=validated["role_set"],
            role_member=validated["role_member"],
            role_adv1=validated["role_adv1"],
            role_adv2=validated["role_adv2"],
        )

        await ctx.reply("✅ Configurações salvas/atualizadas para este servidor no banco de dados (apenas campos faltantes foram solicitados).")

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
            current_roles = await self.db.get_command_permissions(guild.id, command.name)
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
                await self.db.set_command_permissions(guild.id, command.name, "0")
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

            await self.db.set_command_permissions(guild.id, command.name, ",".join(sorted(role_ids)))

        # Resumo final
        perms = await self.db.list_command_permissions(guild.id)
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


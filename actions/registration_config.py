import logging
from typing import Optional, Callable, Awaitable

import discord
from discord.ext import commands

from config_manager import ConfigManager
from db import Database

LOGGER = logging.getLogger(__name__)


class CreateChannelModal(discord.ui.Modal):
    """Modal genérico para criar canais de texto."""
    
    channel_name_input = discord.ui.TextInput(
        label="Nome do Canal",
        placeholder="Ex: canal-exemplo",
        required=True,
        max_length=100
    )
    
    def __init__(self, guild: discord.Guild, title: str = "Criar Novo Canal",
                 channel_name_label: str = "Nome do Canal", 
                 on_success: Optional[Callable[[discord.Interaction, discord.TextChannel], Awaitable[None]]] = None):
        super().__init__(title=title)
        self.guild = guild
        self.on_success = on_success
        # Atualiza o label se fornecido
        if channel_name_label != "Nome do Canal":
            self.channel_name_input.label = channel_name_label
    
    async def on_submit(self, interaction: discord.Interaction):
        """Cria o canal e chama o callback de sucesso."""
        try:
            channel_name = self.channel_name_input.value.strip()
            if not channel_name:
                await interaction.response.send_message(
                    "❌ O nome do canal não pode estar vazio.",
                    ephemeral=True
                )
                return
            
            try:
                channel = await self.guild.create_text_channel(
                    name=channel_name,
                    reason=f"Canal criado via Dashboard por {interaction.user}"
                )
                
                LOGGER.info(f"Canal '{channel.name}' criado no guild {self.guild.id} por {interaction.user.id}")
                
                await interaction.response.send_message(
                    f"✅ Canal **{channel.name}** criado! {channel.mention}",
                    ephemeral=True
                )
                
                # Chama callback de sucesso se fornecido
                if self.on_success:
                    await self.on_success(interaction, channel)
                    
            except discord.Forbidden:
                await interaction.response.send_message(
                    "❌ Não tenho permissão para criar canais. Verifique as permissões do bot.",
                    ephemeral=True
                )
            except Exception as exc:
                LOGGER.error("Erro ao criar canal: %s", exc, exc_info=True)
                await interaction.response.send_message(
                    "❌ Erro ao criar canal. Tente novamente.",
                    ephemeral=True
                )
        except Exception as exc:
            LOGGER.error("Erro no modal de criar canal: %s", exc, exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ Erro ao processar. Tente novamente.",
                    ephemeral=True
                )


class CreateRoleModal(discord.ui.Modal, title="Criar Novo Cargo"):
    """Modal genérico para criar cargos."""
    
    def __init__(self, guild: discord.Guild, 
                 on_success: Optional[Callable[[discord.Interaction, discord.Role], Awaitable[None]]] = None):
        super().__init__()
        self.guild = guild
        self.on_success = on_success
    
    role_name_input = discord.ui.TextInput(
        label="Nome do Cargo",
        placeholder="Ex: Cargo Exemplo",
        required=True,
        max_length=100
    )
    
    role_color_input = discord.ui.TextInput(
        label="Cor (Hex, opcional)",
        placeholder="Ex: #3498db ou deixe em branco",
        required=False,
        max_length=7
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        """Cria o cargo e chama o callback de sucesso."""
        try:
            role_name = self.role_name_input.value.strip()
            if not role_name:
                await interaction.response.send_message(
                    "❌ O nome do cargo não pode estar vazio.",
                    ephemeral=True
                )
                return
            
            # Processa cor
            color = discord.Color.default()
            color_str = self.role_color_input.value.strip()
            if color_str:
                try:
                    # Remove # se presente
                    if color_str.startswith("#"):
                        color_str = color_str[1:]
                    # Converte hex para int
                    color_value = int(color_str, 16)
                    color = discord.Color(color_value)
                except (ValueError, OverflowError):
                    await interaction.response.send_message(
                        "⚠️ Cor inválida. Usando cor padrão.",
                        ephemeral=True
                    )
            
            # Cria o cargo
            try:
                role = await self.guild.create_role(
                    name=role_name,
                    color=color,
                    reason=f"Cargo criado via Dashboard por {interaction.user}"
                )
                
                LOGGER.info(f"Cargo '{role.name}' criado no guild {self.guild.id} por {interaction.user.id}")
                
                await interaction.response.send_message(
                    f"✅ Cargo **{role.name}** criado! {role.mention}",
                    ephemeral=True
                )
                
                # Chama callback de sucesso se fornecido
                if self.on_success:
                    await self.on_success(interaction, role)
                    
            except discord.Forbidden:
                await interaction.response.send_message(
                    "❌ Não tenho permissão para criar cargos. Verifique as permissões do bot.",
                    ephemeral=True
                )
            except Exception as exc:
                LOGGER.error("Erro ao criar cargo: %s", exc, exc_info=True)
                await interaction.response.send_message(
                    "❌ Erro ao criar cargo. Tente novamente.",
                    ephemeral=True
                )
        except Exception as exc:
            LOGGER.error("Erro no modal de criar cargo: %s", exc, exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ Erro ao processar. Tente novamente.",
                    ephemeral=True
                )


class BackButton(discord.ui.Button):
    """Botão para voltar ao dashboard principal."""
    
    def __init__(self, parent_view, row=4):
        super().__init__(label="⬅️ Voltar", style=discord.ButtonStyle.secondary, row=row)
        self.parent_view = parent_view
    
    async def callback(self, interaction: discord.Interaction):
        """Retorna ao dashboard principal."""
        embed = await self.parent_view.build_embed()
        await interaction.response.edit_message(embed=embed, view=self.parent_view)


class RegistrationConfigView(discord.ui.View):
    """View para configurar o sistema de cadastro."""
    
    def __init__(self, bot: commands.Bot, db: Database, config: ConfigManager, guild_id: int, parent_view=None):
        super().__init__(timeout=300)
        self.bot = bot
        self.db = db
        self.config = config
        self.guild_id = guild_id
        self.parent_view = parent_view
        
        # Adiciona botão voltar se parent_view existir
        if self.parent_view:
            self.add_item(BackButton(self.parent_view))
    
    async def build_embed(self) -> discord.Embed:
        """Constrói a embed com as configurações atuais."""
        settings = await self.db.get_settings(self.guild_id)
        guild = self.bot.get_guild(self.guild_id)
        
        embed = discord.Embed(
            title="📝 Configuração do Sistema de Cadastro",
            description="Configure canais e cargos do sistema de cadastro.",
            color=discord.Color.blue()
        )
        
        # Canais
        channel_fields = [
            ("channel_registration_embed", "📋 Canal de Embed de Cadastro"),
            ("channel_welcome", "👋 Canal de Boas-vindas"),
            ("channel_warnings", "⚠️ Canal de Advertências"),
            ("channel_leaves", "👋 Canal de Saídas"),
            ("channel_approval", "✅ Canal de Aprovação"),
            ("channel_records", "📝 Canal de Registros"),
        ]
        
        channels_text = []
        for key, name in channel_fields:
            channel_id = settings.get(key)
            if channel_id:
                channel = guild.get_channel(int(channel_id)) if guild else None
                if channel:
                    channels_text.append(f"{name}: {channel.mention}")
                else:
                    channels_text.append(f"{name}: `{channel_id}` (não encontrado)")
            else:
                channels_text.append(f"{name}: Não configurado")
        
        embed.add_field(
            name="📢 Canais",
            value="\n".join(channels_text) if channels_text else "Nenhum canal configurado",
            inline=False
        )
        
        # Cargos
        role_fields = [
            ("role_set", "🎭 Cargo Inicial (SET)"),
            ("role_member", "👤 Cargo Membro"),
            ("role_adv1", "⚠️ Cargo ADV 1"),
            ("role_adv2", "⚠️ Cargo ADV 2"),
        ]
        
        roles_text = []
        for key, name in role_fields:
            role_id = settings.get(key)
            if role_id:
                role = guild.get_role(int(role_id)) if guild else None
                if role:
                    roles_text.append(f"{name}: {role.mention}")
                else:
                    roles_text.append(f"{name}: `{role_id}` (não encontrado)")
            else:
                roles_text.append(f"{name}: Não configurado")
        
        embed.add_field(
            name="🎭 Cargos",
            value="\n".join(roles_text) if roles_text else "Nenhum cargo configurado",
            inline=False
        )
        
        # Canais ignorados do Analytics
        ignored_channels_str = settings.get("analytics_ignored_channels")
        if ignored_channels_str:
            try:
                import json
                ignored_ids = json.loads(ignored_channels_str) if ignored_channels_str.startswith("[") else [int(cid.strip()) for cid in ignored_channels_str.split(",") if cid.strip()]
                ignored_channels_list = []
                for channel_id in ignored_ids:
                    channel = guild.get_channel(int(channel_id)) if guild else None
                    if channel:
                        ignored_channels_list.append(channel.mention)
                    else:
                        ignored_channels_list.append(f"`{channel_id}` (não encontrado)")
                ignored_text = ", ".join(ignored_channels_list) if ignored_channels_list else "Nenhum"
            except (json.JSONDecodeError, ValueError):
                ignored_text = "Erro ao carregar"
        else:
            ignored_text = "Nenhum canal ignorado"
        
        embed.add_field(
            name="📊 Analytics - Canais Ignorados",
            value=ignored_text,
            inline=False
        )
        
        embed.set_footer(text="Use os botões abaixo para configurar")
        
        return embed
    
    @discord.ui.button(label="Configurar Canais", style=discord.ButtonStyle.primary, row=0)
    async def configure_channels(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre view para configurar canais."""
        view = ChannelConfigView(self.bot, self.db, self.guild_id, self)
        embed = await view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="Configurar Cargos", style=discord.ButtonStyle.primary, row=0)
    async def configure_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre view para configurar cargos."""
        view = RoleConfigView(self.bot, self.db, self.guild_id, self)
        embed = await view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="📊 Canais Ignorados (Analytics)", style=discord.ButtonStyle.secondary, row=1)
    async def configure_analytics_channels(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre view para configurar canais ignorados do analytics."""
        view = AnalyticsIgnoredChannelsView(self.bot, self.db, self.guild_id, self)
        embed = await view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)


class ChannelConfigView(discord.ui.View):
    """View para configurar canais do sistema de cadastro."""
    
    def __init__(self, bot: commands.Bot, db: Database, guild_id: int, parent_view):
        super().__init__(timeout=300)
        self.bot = bot
        self.db = db
        self.guild_id = guild_id
        self.parent_view = parent_view
        self.guild = bot.get_guild(guild_id)
        
        # ChannelSelect para Embed de Cadastro (ocupa toda a linha - 5 slots)
        self.embed_channel_select = discord.ui.ChannelSelect(
            placeholder="Selecione o canal de Embed de Cadastro...",
            channel_types=[discord.ChannelType.text],
            min_values=0,
            max_values=1,
            row=0
        )
        self.embed_channel_select.callback = self.on_embed_channel_select
        self.add_item(self.embed_channel_select)
        
        # ChannelSelect para Welcome (ocupa toda a linha - 5 slots)
        self.welcome_channel_select = discord.ui.ChannelSelect(
            placeholder="Selecione o canal de Boas-vindas...",
            channel_types=[discord.ChannelType.text],
            min_values=0,
            max_values=1,
            row=1
        )
        self.welcome_channel_select.callback = self.on_welcome_channel_select
        self.add_item(self.welcome_channel_select)
        
        # ChannelSelect para Logs (Records) (ocupa toda a linha - 5 slots)
        self.logs_channel_select = discord.ui.ChannelSelect(
            placeholder="Selecione o canal de Logs/Registros...",
            channel_types=[discord.ChannelType.text],
            min_values=0,
            max_values=1,
            row=2
        )
        self.logs_channel_select.callback = self.on_logs_channel_select
        self.add_item(self.logs_channel_select)
        
        # ChannelSelect para Rules (Warnings) (ocupa toda a linha - 5 slots)
        self.rules_channel_select = discord.ui.ChannelSelect(
            placeholder="Selecione o canal de Advertências...",
            channel_types=[discord.ChannelType.text],
            min_values=0,
            max_values=1,
            row=3
        )
        self.rules_channel_select.callback = self.on_rules_channel_select
        self.add_item(self.rules_channel_select)
        
        # Botões na row 4
        self.more_channels_btn = discord.ui.Button(
            label="📄 Mais Canais",
            style=discord.ButtonStyle.secondary,
            row=4
        )
        self.more_channels_btn.callback = self.open_more_channels
        self.add_item(self.more_channels_btn)
        
        self.create_btn = discord.ui.Button(
            label="➕ Criar Canais",
            style=discord.ButtonStyle.success,
            row=4
        )
        self.create_btn.callback = self.open_create_channels
        self.add_item(self.create_btn)
        
        # Botão voltar
        self.add_item(BackButton(self.parent_view, row=4))
    
    async def open_create_channels(self, interaction: discord.Interaction):
        """Abre view com botões para criar canais."""
        view = ChannelConfigView2(self.bot, self.db, self.guild_id, self.parent_view)
        embed = await view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)
    
    async def open_more_channels(self, interaction: discord.Interaction):
        """Abre view com canais adicionais."""
        view = ChannelConfigView2(self.bot, self.db, self.guild_id, self.parent_view)
        embed = await view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)
    
    async def build_embed(self) -> discord.Embed:
        """Constrói embed com configurações atuais de canais."""
        settings = await self.db.get_settings(self.guild_id)
        
        embed = discord.Embed(
            title="📢 Configuração de Canais",
            description="Selecione os canais abaixo para configurar o sistema de cadastro.",
            color=discord.Color.blue()
        )
        
        channel_info = [
            ("channel_registration_embed", "📋 Canal de Embed de Cadastro"),
            ("channel_welcome", "👋 Canal de Boas-vindas"),
            ("channel_records", "📝 Canal de Logs/Registros"),
            ("channel_warnings", "⚠️ Canal de Advertências"),
            ("channel_leaves", "👋 Canal de Saídas"),
            ("channel_approval", "✅ Canal de Aprovação"),
        ]
        
        channels_text = []
        for key, name in channel_info:
            channel_id = settings.get(key)
            # Converte para string e verifica se não está vazio
            if channel_id and str(channel_id).strip() and str(channel_id).strip() != "None":
                try:
                    channel = self.guild.get_channel(int(channel_id)) if self.guild else None
                    if channel:
                        channels_text.append(f"{name}: {channel.mention}")
                    else:
                        channels_text.append(f"{name}: `{channel_id}` (não encontrado)")
                except (ValueError, TypeError):
                    channels_text.append(f"{name}: `{channel_id}` (inválido)")
            else:
                channels_text.append(f"{name}: Não configurado")
        
        embed.add_field(
            name="📢 Canais Configurados",
            value="\n".join(channels_text) if channels_text else "Nenhum canal configurado",
            inline=False
        )
        
        embed.set_footer(text="Use os seletores acima para configurar cada canal")
        
        return embed
    
    async def _save_channel(self, interaction: discord.Interaction, channel_key: str, channel_id: Optional[int], channel_name: str):
        """Salva um canal no banco de dados."""
        await self.db.upsert_settings(self.guild_id, **{channel_key: channel_id})
        LOGGER.info(f"Canal {channel_name} atualizado para guild {self.guild_id}: {channel_id}")
        
        # Atualiza embed
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)
        
        # Confirmação ephemeral
        if channel_id:
            channel = self.guild.get_channel(channel_id) if self.guild else None
            await interaction.followup.send(
                f"✅ {channel_name} configurado: {channel.mention if channel else f'ID {channel_id}'}",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"✅ {channel_name} removido.",
                ephemeral=True
            )
    
    async def on_embed_channel_select(self, interaction: discord.Interaction):
        """Callback para seleção do canal de embed."""
        channel_id = self.embed_channel_select.values[0].id if self.embed_channel_select.values else None
        await self._save_channel(interaction, "channel_registration_embed", channel_id, "Canal de Embed de Cadastro")
    
    async def on_welcome_channel_select(self, interaction: discord.Interaction):
        """Callback para seleção do canal de boas-vindas."""
        channel_id = self.welcome_channel_select.values[0].id if self.welcome_channel_select.values else None
        await self._save_channel(interaction, "channel_welcome", channel_id, "Canal de Boas-vindas")
    
    async def on_logs_channel_select(self, interaction: discord.Interaction):
        """Callback para seleção do canal de logs."""
        channel_id = self.logs_channel_select.values[0].id if self.logs_channel_select.values else None
        await self._save_channel(interaction, "channel_records", channel_id, "Canal de Logs/Registros")
    
    async def on_rules_channel_select(self, interaction: discord.Interaction):
        """Callback para seleção do canal de advertências."""
        channel_id = self.rules_channel_select.values[0].id if self.rules_channel_select.values else None
        await self._save_channel(interaction, "channel_warnings", channel_id, "Canal de Advertências")
    
    async def _create_and_save_channel(self, interaction: discord.Interaction, channel_key: str, channel_name: str):
        """Cria um canal e salva automaticamente."""
        async def on_success(inter: discord.Interaction, channel: discord.TextChannel):
            await self.db.upsert_settings(self.guild_id, **{channel_key: channel.id})
            LOGGER.info(f"Canal {channel_name} criado e configurado para guild {self.guild_id}: {channel.id}")
            # Atualiza embed
            embed = await self.build_embed()
            await inter.edit_original_response(embed=embed, view=self)
        
        modal = CreateChannelModal(
            guild=self.guild,
            title=f"Criar {channel_name}",
            channel_name_label="Nome do Canal",
            on_success=on_success
        )
        await interaction.response.send_modal(modal)
    
    async def create_embed_channel(self, interaction: discord.Interaction):
        """Abre modal para criar canal de embed de cadastro."""
        await self._create_and_save_channel(interaction, "channel_registration_embed", "Canal de Embed de Cadastro")
    
    async def create_welcome_channel(self, interaction: discord.Interaction):
        """Abre modal para criar canal de boas-vindas."""
        await self._create_and_save_channel(interaction, "channel_welcome", "Canal de Boas-vindas")
    
    async def create_logs_channel(self, interaction: discord.Interaction):
        """Abre modal para criar canal de logs."""
        await self._create_and_save_channel(interaction, "channel_records", "Canal de Logs/Registros")
    
    async def create_rules_channel(self, interaction: discord.Interaction):
        """Abre modal para criar canal de advertências."""
        await self._create_and_save_channel(interaction, "channel_warnings", "Canal de Advertências")


class ChannelConfigView2(discord.ui.View):
    """View para configurar canais adicionais do sistema de cadastro."""
    
    def __init__(self, bot: commands.Bot, db: Database, guild_id: int, parent_view):
        super().__init__(timeout=300)
        self.bot = bot
        self.db = db
        self.guild_id = guild_id
        self.parent_view = parent_view
        self.guild = bot.get_guild(guild_id)
        
        # ChannelSelect para Saídas (ocupa toda a linha - 5 slots)
        self.leaves_channel_select = discord.ui.ChannelSelect(
            placeholder="Selecione o canal de Saídas...",
            channel_types=[discord.ChannelType.text],
            min_values=0,
            max_values=1,
            row=0
        )
        self.leaves_channel_select.callback = self.on_leaves_channel_select
        self.add_item(self.leaves_channel_select)
        
        # ChannelSelect para Aprovação (ocupa toda a linha - 5 slots)
        self.approval_channel_select = discord.ui.ChannelSelect(
            placeholder="Selecione o canal de Aprovação...",
            channel_types=[discord.ChannelType.text],
            min_values=0,
            max_values=1,
            row=1
        )
        self.approval_channel_select.callback = self.on_approval_channel_select
        self.add_item(self.approval_channel_select)
        
        # Botões "Criar Novo" na row 2
        self.create_leaves_btn = discord.ui.Button(
            label="➕ Saídas",
            style=discord.ButtonStyle.success,
            row=2
        )
        self.create_leaves_btn.callback = self.create_leaves_channel
        self.add_item(self.create_leaves_btn)
        
        self.create_approval_btn = discord.ui.Button(
            label="➕ Aprovação",
            style=discord.ButtonStyle.success,
            row=2
        )
        self.create_approval_btn.callback = self.create_approval_channel
        self.add_item(self.create_approval_btn)
        
        # Botões "Criar Novo" dos canais principais na row 3
        self.create_embed_btn = discord.ui.Button(
            label="➕ Embed",
            style=discord.ButtonStyle.success,
            row=3
        )
        self.create_embed_btn.callback = self.create_embed_channel
        self.add_item(self.create_embed_btn)
        
        self.create_welcome_btn = discord.ui.Button(
            label="➕ Welcome",
            style=discord.ButtonStyle.success,
            row=3
        )
        self.create_welcome_btn.callback = self.create_welcome_channel
        self.add_item(self.create_welcome_btn)
        
        self.create_logs_btn = discord.ui.Button(
            label="➕ Logs",
            style=discord.ButtonStyle.success,
            row=3
        )
        self.create_logs_btn.callback = self.create_logs_channel
        self.add_item(self.create_logs_btn)
        
        self.create_rules_btn = discord.ui.Button(
            label="➕ Advertências",
            style=discord.ButtonStyle.success,
            row=3
        )
        self.create_rules_btn.callback = self.create_rules_channel
        self.add_item(self.create_rules_btn)
        
        # Botões de navegação na row 4
        self.back_to_main_btn = discord.ui.Button(
            label="⬅️ Voltar",
            style=discord.ButtonStyle.secondary,
            row=4
        )
        self.back_to_main_btn.callback = self.back_to_main_channels
        self.add_item(self.back_to_main_btn)
        
        self.add_item(BackButton(self.parent_view, row=4))
    
    async def build_embed(self) -> discord.Embed:
        """Constrói embed com configurações atuais de canais adicionais."""
        settings = await self.db.get_settings(self.guild_id)
        
        embed = discord.Embed(
            title="📢 Configuração de Canais (Página 2)",
            description="Configure os canais adicionais e use os botões para criar novos canais.",
            color=discord.Color.blue()
        )
        
        channel_info = [
            ("channel_leaves", "👋 Canal de Saídas"),
            ("channel_approval", "✅ Canal de Aprovação"),
        ]
        
        channels_text = []
        for key, name in channel_info:
            channel_id = settings.get(key)
            # Converte para string e verifica se não está vazio
            if channel_id and str(channel_id).strip() and str(channel_id).strip() != "None":
                try:
                    channel = self.guild.get_channel(int(channel_id)) if self.guild else None
                    if channel:
                        channels_text.append(f"{name}: {channel.mention}")
                    else:
                        channels_text.append(f"{name}: `{channel_id}` (não encontrado)")
                except (ValueError, TypeError):
                    channels_text.append(f"{name}: `{channel_id}` (inválido)")
            else:
                channels_text.append(f"{name}: Não configurado")
        
        embed.add_field(
            name="📢 Canais Adicionais",
            value="\n".join(channels_text) if channels_text else "Nenhum canal configurado",
            inline=False
        )
        
        embed.set_footer(text="Use os seletores acima para configurar cada canal")
        
        return embed
    
    async def _save_channel(self, interaction: discord.Interaction, channel_key: str, channel_id: Optional[int], channel_name: str):
        """Salva um canal no banco de dados."""
        await self.db.upsert_settings(self.guild_id, **{channel_key: channel_id})
        LOGGER.info(f"Canal {channel_name} atualizado para guild {self.guild_id}: {channel_id}")
        
        # Atualiza embed
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)
        
        # Confirmação ephemeral
        if channel_id:
            channel = self.guild.get_channel(channel_id) if self.guild else None
            await interaction.followup.send(
                f"✅ {channel_name} configurado: {channel.mention if channel else f'ID {channel_id}'}",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"✅ {channel_name} removido.",
                ephemeral=True
            )
    
    async def on_leaves_channel_select(self, interaction: discord.Interaction):
        """Callback para seleção do canal de saídas."""
        channel_id = self.leaves_channel_select.values[0].id if self.leaves_channel_select.values else None
        await self._save_channel(interaction, "channel_leaves", channel_id, "Canal de Saídas")
    
    async def on_approval_channel_select(self, interaction: discord.Interaction):
        """Callback para seleção do canal de aprovação."""
        channel_id = self.approval_channel_select.values[0].id if self.approval_channel_select.values else None
        await self._save_channel(interaction, "channel_approval", channel_id, "Canal de Aprovação")
    
    async def _create_and_save_channel(self, interaction: discord.Interaction, channel_key: str, channel_name: str):
        """Cria um canal e salva automaticamente."""
        async def on_success(inter: discord.Interaction, channel: discord.TextChannel):
            await self.db.upsert_settings(self.guild_id, **{channel_key: channel.id})
            LOGGER.info(f"Canal {channel_name} criado e configurado para guild {self.guild_id}: {channel.id}")
            # Atualiza embed
            embed = await self.build_embed()
            await inter.edit_original_response(embed=embed, view=self)
        
        modal = CreateChannelModal(
            guild=self.guild,
            title=f"Criar {channel_name}",
            channel_name_label="Nome do Canal",
            on_success=on_success
        )
        await interaction.response.send_modal(modal)
    
    async def create_leaves_channel(self, interaction: discord.Interaction):
        """Abre modal para criar canal de saídas."""
        await self._create_and_save_channel(interaction, "channel_leaves", "Canal de Saídas")
    
    async def create_approval_channel(self, interaction: discord.Interaction):
        """Abre modal para criar canal de aprovação."""
        await self._create_and_save_channel(interaction, "channel_approval", "Canal de Aprovação")
    
    async def create_embed_channel(self, interaction: discord.Interaction):
        """Abre modal para criar canal de embed de cadastro."""
        await self._create_and_save_channel(interaction, "channel_registration_embed", "Canal de Embed de Cadastro")
    
    async def create_welcome_channel(self, interaction: discord.Interaction):
        """Abre modal para criar canal de boas-vindas."""
        await self._create_and_save_channel(interaction, "channel_welcome", "Canal de Boas-vindas")
    
    async def create_logs_channel(self, interaction: discord.Interaction):
        """Abre modal para criar canal de logs."""
        await self._create_and_save_channel(interaction, "channel_records", "Canal de Logs/Registros")
    
    async def create_rules_channel(self, interaction: discord.Interaction):
        """Abre modal para criar canal de advertências."""
        await self._create_and_save_channel(interaction, "channel_warnings", "Canal de Advertências")
    
    async def back_to_main_channels(self, interaction: discord.Interaction):
        """Volta para a primeira página de canais."""
        view = ChannelConfigView(self.bot, self.db, self.guild_id, self.parent_view)
        embed = await view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)


class AnalyticsIgnoredChannelsView(discord.ui.View):
    """View para configurar canais ignorados do sistema de analytics."""
    
    def __init__(self, bot: commands.Bot, db: Database, guild_id: int, parent_view):
        super().__init__(timeout=300)
        self.bot = bot
        self.db = db
        self.guild_id = guild_id
        self.parent_view = parent_view
        self.guild = bot.get_guild(guild_id)
        
        # ChannelSelect para canais ignorados (múltipla seleção)
        self.ignored_channels_select = discord.ui.ChannelSelect(
            placeholder="Selecione os canais a ignorar no analytics...",
            channel_types=[discord.ChannelType.text],
            min_values=0,
            max_values=25,
            row=0
        )
        self.ignored_channels_select.callback = self.on_ignored_channels_select
        self.add_item(self.ignored_channels_select)
        
        # Botão para limpar canais ignorados
        clear_button = discord.ui.Button(
            label="🗑️ Limpar Canais Ignorados",
            style=discord.ButtonStyle.danger,
            row=1
        )
        clear_button.callback = self.clear_ignored_channels
        self.add_item(clear_button)
        
        # Botão voltar
        if self.parent_view:
            self.add_item(BackButton(self.parent_view))
    
    async def build_embed(self) -> discord.Embed:
        """Constrói embed com canais ignorados atuais."""
        settings = await self.db.get_settings(self.guild_id)
        ignored_channels_str = settings.get("analytics_ignored_channels")
        
        embed = discord.Embed(
            title="📊 Canais Ignorados - Analytics",
            description="Canais selecionados não serão rastreados pelo sistema de analytics.",
            color=discord.Color.orange()
        )
        
        if ignored_channels_str:
            try:
                import json
                ignored_ids = json.loads(ignored_channels_str) if ignored_channels_str.startswith("[") else [int(cid.strip()) for cid in ignored_channels_str.split(",") if cid.strip()]
                ignored_channels_list = []
                for channel_id in ignored_ids:
                    channel = self.guild.get_channel(int(channel_id)) if self.guild else None
                    if channel:
                        ignored_channels_list.append(f"{channel.mention} ({channel.name})")
                    else:
                        ignored_channels_list.append(f"`{channel_id}` (não encontrado)")
                ignored_text = "\n".join(ignored_channels_list) if ignored_channels_list else "Nenhum"
            except (json.JSONDecodeError, ValueError):
                ignored_text = "Erro ao carregar canais"
        else:
            ignored_text = "Nenhum canal ignorado"
        
        embed.add_field(
            name="Canais Ignorados",
            value=ignored_text,
            inline=False
        )
        
        embed.set_footer(text="Use o seletor abaixo para adicionar/remover canais")
        
        return embed
    
    async def on_ignored_channels_select(self, interaction: discord.Interaction):
        """Salva canais ignorados selecionados."""
        await interaction.response.defer(ephemeral=True)
        
        selected_channels = self.ignored_channels_select.values
        channel_ids = [str(channel.id) for channel in selected_channels]
        
        # Salva como JSON string
        import json
        ignored_json = json.dumps(channel_ids)
        
        await self.db.upsert_settings(
            self.guild_id,
            analytics_ignored_channels=ignored_json
        )
        
        # Limpa cache do AnalyticsCog se estiver carregado
        analytics_cog = self.bot.get_cog("AnalyticsCog")
        if analytics_cog and hasattr(analytics_cog, "_ignored_channels_cache"):
            if self.guild_id in analytics_cog._ignored_channels_cache:
                del analytics_cog._ignored_channels_cache[self.guild_id]
        
        embed = await self.build_embed()
        await interaction.followup.send(
            f"✅ {len(channel_ids)} canal(is) configurado(s) como ignorado(s).",
            ephemeral=True
        )
        await interaction.message.edit(embed=embed, view=self)
    
    async def clear_ignored_channels(self, interaction: discord.Interaction):
        """Limpa todos os canais ignorados."""
        await interaction.response.defer(ephemeral=True)
        
        await self.db.upsert_settings(
            self.guild_id,
            analytics_ignored_channels=None
        )
        
        # Limpa cache do AnalyticsCog se estiver carregado
        analytics_cog = self.bot.get_cog("AnalyticsCog")
        if analytics_cog and hasattr(analytics_cog, "_ignored_channels_cache"):
            if self.guild_id in analytics_cog._ignored_channels_cache:
                del analytics_cog._ignored_channels_cache[self.guild_id]
        
        embed = await self.build_embed()
        await interaction.followup.send(
            "✅ Canais ignorados limpos.",
            ephemeral=True
        )
        await interaction.message.edit(embed=embed, view=self)


class RoleConfigView(discord.ui.View):
    """View para configurar cargos do sistema de cadastro."""
    
    def __init__(self, bot: commands.Bot, db: Database, guild_id: int, parent_view):
        super().__init__(timeout=300)
        self.bot = bot
        self.db = db
        self.guild_id = guild_id
        self.parent_view = parent_view
        self.guild = bot.get_guild(guild_id)
        
        # RoleSelect para Cargo Membro (ocupa toda a linha - 5 slots)
        self.member_role_select = discord.ui.RoleSelect(
            placeholder="Selecione o Cargo de Membro...",
            min_values=0,
            max_values=1,
            row=0
        )
        self.member_role_select.callback = self.on_member_role_select
        self.add_item(self.member_role_select)
        
        # RoleSelect para Cargo Inicial (SET) (ocupa toda a linha - 5 slots)
        self.staff_role_select = discord.ui.RoleSelect(
            placeholder="Selecione o Cargo Inicial (SET)...",
            min_values=0,
            max_values=1,
            row=1
        )
        self.staff_role_select.callback = self.on_staff_role_select
        self.add_item(self.staff_role_select)
        
        # RoleSelect para Cargo ADV 1 (ocupa toda a linha - 5 slots)
        self.adv1_role_select = discord.ui.RoleSelect(
            placeholder="Selecione o Cargo ADV 1...",
            min_values=0,
            max_values=1,
            row=2
        )
        self.adv1_role_select.callback = self.on_adv1_role_select
        self.add_item(self.adv1_role_select)
        
        # RoleSelect para Cargo ADV 2 (ocupa toda a linha - 5 slots)
        self.adv2_role_select = discord.ui.RoleSelect(
            placeholder="Selecione o Cargo ADV 2...",
            min_values=0,
            max_values=1,
            row=3
        )
        self.adv2_role_select.callback = self.on_adv2_role_select
        self.add_item(self.adv2_role_select)
        
        # Botões "Criar Novo" e "Voltar" na última linha (row 4) - máximo 5 itens
        self.create_member_btn = discord.ui.Button(
            label="➕ Membro",
            style=discord.ButtonStyle.success,
            row=4
        )
        self.create_member_btn.callback = self.create_member_role
        self.add_item(self.create_member_btn)
        
        self.create_staff_btn = discord.ui.Button(
            label="➕ Inicial",
            style=discord.ButtonStyle.success,
            row=4
        )
        self.create_staff_btn.callback = self.create_staff_role
        self.add_item(self.create_staff_btn)
        
        self.create_adv1_btn = discord.ui.Button(
            label="➕ ADV1",
            style=discord.ButtonStyle.success,
            row=4
        )
        self.create_adv1_btn.callback = self.create_adv1_role
        self.add_item(self.create_adv1_btn)
        
        self.create_adv2_btn = discord.ui.Button(
            label="➕ ADV2",
            style=discord.ButtonStyle.success,
            row=4
        )
        self.create_adv2_btn.callback = self.create_adv2_role
        self.add_item(self.create_adv2_btn)
        
        # Botão voltar (último item na row 4 - total de 5 itens)
        self.add_item(BackButton(self.parent_view, row=4))
    
    async def build_embed(self) -> discord.Embed:
        """Constrói embed com configurações atuais de cargos."""
        settings = await self.db.get_settings(self.guild_id)
        
        embed = discord.Embed(
            title="🎭 Configuração de Cargos",
            description="Selecione os cargos abaixo para configurar o sistema de cadastro.",
            color=discord.Color.blue()
        )
        
        role_info = [
            ("role_member", "👤 Cargo Membro"),
            ("role_set", "🎭 Cargo Inicial (SET)"),
            ("role_adv1", "⚠️ Cargo ADV 1"),
            ("role_adv2", "⚠️ Cargo ADV 2"),
        ]
        
        roles_text = []
        for key, name in role_info:
            role_id = settings.get(key)
            if role_id:
                role = self.guild.get_role(int(role_id)) if self.guild else None
                if role:
                    roles_text.append(f"{name}: {role.mention}")
                else:
                    roles_text.append(f"{name}: `{role_id}` (não encontrado)")
            else:
                roles_text.append(f"{name}: Não configurado")
        
        embed.add_field(
            name="🎭 Cargos Configurados",
            value="\n".join(roles_text) if roles_text else "Nenhum cargo configurado",
            inline=False
        )
        
        embed.set_footer(text="Use os seletores acima para configurar cada cargo")
        
        return embed
    
    async def _save_role(self, interaction: discord.Interaction, role_key: str, role_id: Optional[int], role_name: str):
        """Salva um cargo no banco de dados."""
        await self.db.upsert_settings(self.guild_id, **{role_key: role_id})
        LOGGER.info(f"Cargo {role_name} atualizado para guild {self.guild_id}: {role_id}")
        
        # Atualiza embed
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)
        
        # Confirmação ephemeral
        if role_id:
            role = self.guild.get_role(role_id) if self.guild else None
            await interaction.followup.send(
                f"✅ {role_name} configurado: {role.mention if role else f'ID {role_id}'}",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"✅ {role_name} removido.",
                ephemeral=True
            )
    
    async def on_member_role_select(self, interaction: discord.Interaction):
        """Callback para seleção do cargo de membro."""
        role_id = self.member_role_select.values[0].id if self.member_role_select.values else None
        await self._save_role(interaction, "role_member", role_id, "Cargo Membro")
    
    async def on_staff_role_select(self, interaction: discord.Interaction):
        """Callback para seleção do cargo inicial."""
        role_id = self.staff_role_select.values[0].id if self.staff_role_select.values else None
        await self._save_role(interaction, "role_set", role_id, "Cargo Inicial (SET)")
    
    async def on_adv1_role_select(self, interaction: discord.Interaction):
        """Callback para seleção do cargo ADV 1."""
        role_id = self.adv1_role_select.values[0].id if self.adv1_role_select.values else None
        await self._save_role(interaction, "role_adv1", role_id, "Cargo ADV 1")
    
    async def on_adv2_role_select(self, interaction: discord.Interaction):
        """Callback para seleção do cargo ADV 2."""
        role_id = self.adv2_role_select.values[0].id if self.adv2_role_select.values else None
        await self._save_role(interaction, "role_adv2", role_id, "Cargo ADV 2")
    
    async def _create_and_save_role(self, interaction: discord.Interaction, role_key: str, role_name: str):
        """Cria um cargo e salva automaticamente."""
        async def on_success(inter: discord.Interaction, role: discord.Role):
            await self.db.upsert_settings(self.guild_id, **{role_key: role.id})
            LOGGER.info(f"Cargo {role_name} criado e configurado para guild {self.guild_id}: {role.id}")
            # Atualiza embed
            embed = await self.build_embed()
            await inter.edit_original_response(embed=embed, view=self)
        
        modal = CreateRoleModal(
            guild=self.guild,
            on_success=on_success
        )
        await interaction.response.send_modal(modal)
    
    async def create_member_role(self, interaction: discord.Interaction):
        """Abre modal para criar cargo de membro."""
        await self._create_and_save_role(interaction, "role_member", "Cargo Membro")
    
    async def create_staff_role(self, interaction: discord.Interaction):
        """Abre modal para criar cargo inicial."""
        await self._create_and_save_role(interaction, "role_set", "Cargo Inicial (SET)")
    
    async def create_adv1_role(self, interaction: discord.Interaction):
        """Abre modal para criar cargo ADV 1."""
        await self._create_and_save_role(interaction, "role_adv1", "Cargo ADV 1")
    
    async def create_adv2_role(self, interaction: discord.Interaction):
        """Abre modal para criar cargo ADV 2."""
        await self._create_and_save_role(interaction, "role_adv2", "Cargo ADV 2")

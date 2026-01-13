import logging
from typing import Optional, Callable, Awaitable

import discord
from discord.ext import commands

from db import Database
from permissions import command_guard

LOGGER = logging.getLogger(__name__)


class CreateVoiceChannelModal(discord.ui.Modal):
    """Modal para criar canais de voz."""
    
    def __init__(self, guild: discord.Guild, 
                 on_success: Optional[Callable[[discord.Interaction, discord.VoiceChannel], Awaitable[None]]] = None):
        super().__init__(title="Criar Novo Canal de Voz")
        self.guild = guild
        self.on_success = on_success
        self.channel_name_input = discord.ui.TextInput(
            label="Nome do Canal de Voz",
            placeholder="Ex: call-geral",
            required=True,
            max_length=100
        )
        self.add_item(self.channel_name_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Cria o canal de voz e chama o callback de sucesso."""
        try:
            channel_name = self.channel_name_input.value.strip()
            if not channel_name:
                await interaction.response.send_message(
                    "❌ O nome do canal não pode estar vazio.",
                    ephemeral=True
                )
                return
            
            try:
                channel = await self.guild.create_voice_channel(
                    name=channel_name,
                    reason=f"Canal de voz criado via Dashboard por {interaction.user}"
                )
                
                LOGGER.info(f"Canal de voz '{channel.name}' criado no guild {self.guild.id} por {interaction.user.id}")
                
                await interaction.response.send_message(
                    f"✅ Canal de voz **{channel.name}** criado! {channel.mention}",
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
                LOGGER.error("Erro ao criar canal de voz: %s", exc, exc_info=True)
                await interaction.response.send_message(
                    "❌ Erro ao criar canal. Tente novamente.",
                    ephemeral=True
                )
        except Exception as exc:
            LOGGER.error("Erro no modal de criar canal de voz: %s", exc, exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ Erro ao processar. Tente novamente.",
                    ephemeral=True
                )


class CreateRoleModal(discord.ui.Modal):
    """Modal genérico para criar cargos."""
    
    def __init__(self, guild: discord.Guild, 
                 on_success: Optional[Callable[[discord.Interaction, discord.Role], Awaitable[None]]] = None):
        super().__init__(title="Criar Novo Cargo")
        self.guild = guild
        self.on_success = on_success
        self.role_name_input = discord.ui.TextInput(
            label="Nome do Cargo",
            placeholder="Ex: Cargo Exemplo",
            required=True,
            max_length=100
        )
        self.role_color_input = discord.ui.TextInput(
            label="Cor (Hex, opcional)",
            placeholder="Ex: #3498db ou deixe em branco",
            required=False,
            max_length=7
        )
        self.add_item(self.role_name_input)
        self.add_item(self.role_color_input)
    
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
    
    def __init__(self, parent_view):
        super().__init__(label="⬅️ Voltar ao Dashboard", style=discord.ButtonStyle.secondary, row=4)
        self.parent_view = parent_view
    
    async def callback(self, interaction: discord.Interaction):
        """Retorna ao dashboard principal."""
        embed = await self.parent_view.build_embed()
        await interaction.response.edit_message(embed=embed, view=self.parent_view)


class VoiceChannelSelectView(discord.ui.View):
    """View para selecionar canais de voz para monitoramento."""
    
    def __init__(self, db: Database, guild_id: int, setup_view):
        super().__init__(timeout=300)
        self.db = db
        self.guild_id = guild_id
        self.setup_view = setup_view
        self.guild = setup_view.bot.get_guild(guild_id) if hasattr(setup_view, 'bot') else None
        
        self.channel_select = discord.ui.ChannelSelect(
            placeholder="Selecione os canais de voz para monitorar",
            channel_types=[discord.ChannelType.voice],
            min_values=0,
            max_values=25,
            row=0
        )
        self.channel_select.callback = self.on_channel_select
        self.add_item(self.channel_select)
        
        # Botão Criar Novo Canal de Voz
        self.create_channel_btn = discord.ui.Button(
            label="➕ Criar Novo Canal",
            style=discord.ButtonStyle.success,
            row=1
        )
        self.create_channel_btn.callback = self.create_voice_channel
        self.add_item(self.create_channel_btn)
    
    async def create_voice_channel(self, interaction: discord.Interaction):
        """Abre modal para criar um novo canal de voz."""
        if not self.guild:
            await interaction.response.send_message("❌ Servidor não encontrado.", ephemeral=True)
            return
        
        class CreateVoiceChannelModal(discord.ui.Modal, title="Criar Canal de Voz"):
            channel_name = discord.ui.TextInput(
                label="Nome do Canal",
                placeholder="ex: Sala de Voz 1",
                max_length=100,
                required=True
            )
            
            def __init__(self, view):
                super().__init__()
                self.view = view
            
            async def on_submit(self, modal_interaction: discord.Interaction):
                await modal_interaction.response.defer(ephemeral=True)
                
                try:
                    channel = await self.view.guild.create_voice_channel(
                        name=self.channel_name.value
                    )
                    
                    # Adiciona o canal à lista de monitorados
                    await self.view.db.add_monitored_channel(self.view.guild_id, channel.id)
                    
                    # Atualiza a embed
                    embed = await self.view.setup_view.build_embed()
                    await modal_interaction.edit_original_response(embed=embed, view=self.view.setup_view)
                    
                    await modal_interaction.followup.send(
                        f"✅ Canal de voz '{channel.name}' criado e adicionado à lista de monitorados!",
                        ephemeral=True
                    )
                except discord.Forbidden:
                    await modal_interaction.followup.send(
                        "❌ Não tenho permissão para criar canais de voz.",
                        ephemeral=True
                    )
                except Exception as e:
                    await modal_interaction.followup.send(
                        f"❌ Erro ao criar canal: {str(e)}",
                        ephemeral=True
                    )
        
        modal = CreateVoiceChannelModal(self)
        await interaction.response.send_modal(modal)
    
    async def on_channel_select(self, interaction: discord.Interaction):
        """Adiciona ou remove canais da lista de monitorados."""
        await interaction.response.defer(ephemeral=True)
        
        selected_channels = [ch.id for ch in self.channel_select.values]
        current_channels = set(await self.db.get_monitored_channels(self.guild_id))
        selected_set = set(selected_channels)
        
        # Adiciona novos canais
        to_add = selected_set - current_channels
        for channel_id in to_add:
            await self.db.add_monitored_channel(self.guild_id, channel_id)
        
        # Remove canais não selecionados
        to_remove = current_channels - selected_set
        for channel_id in to_remove:
            await self.db.remove_monitored_channel(self.guild_id, channel_id)
        
        # Atualiza a embed
        embed = await self.setup_view.build_embed()
        await interaction.edit_original_response(embed=embed, view=self.setup_view)
        
        changes = []
        if to_add:
            changes.append(f"✅ Adicionados: {len(to_add)} canal(is)")
        if to_remove:
            changes.append(f"❌ Removidos: {len(to_remove)} canal(is)")
        
        if changes:
            await interaction.followup.send("\n".join(changes), ephemeral=True)
        else:
            await interaction.followup.send("✅ Nenhuma alteração necessária.", ephemeral=True)


class VoiceRoleSelectView(discord.ui.View):
    """View para selecionar cargos permitidos para monitoramento."""
    
    def __init__(self, db: Database, guild_id: int, setup_view):
        super().__init__(timeout=300)
        self.db = db
        self.guild_id = guild_id
        self.setup_view = setup_view
        self.guild = setup_view.bot.get_guild(guild_id) if hasattr(setup_view, 'bot') else None
        
        self.role_select = discord.ui.RoleSelect(
            placeholder="Selecione os cargos permitidos",
            min_values=0,
            max_values=25,
            row=0
        )
        self.role_select.callback = self.on_role_select
        self.add_item(self.role_select)
        
        # Botão Criar Novo Cargo
        self.create_role_btn = discord.ui.Button(
            label="➕ Criar Novo Cargo",
            style=discord.ButtonStyle.success,
            row=1
        )
        self.create_role_btn.callback = self.create_role
        self.add_item(self.create_role_btn)
    
    async def on_role_select(self, interaction: discord.Interaction):
        """Adiciona ou remove cargos da lista de permitidos."""
        await interaction.response.defer(ephemeral=True)
        
        selected_roles = [role.id for role in self.role_select.values]
        current_roles = set(await self.db.get_allowed_roles(self.guild_id))
        selected_set = set(selected_roles)
        
        # Adiciona novos cargos
        to_add = selected_set - current_roles
        for role_id in to_add:
            await self.db.add_allowed_role(self.guild_id, role_id)
        
        # Remove cargos não selecionados
        to_remove = current_roles - selected_set
        for role_id in to_remove:
            await self.db.remove_allowed_role(self.guild_id, role_id)
        
        # Atualiza a embed
        embed = await self.setup_view.build_embed()
        await interaction.edit_original_response(embed=embed, view=self.setup_view)
        
        changes = []
        if to_add:
            changes.append(f"✅ Adicionados: {len(to_add)} cargo(s)")
        if to_remove:
            changes.append(f"❌ Removidos: {len(to_remove)} cargo(s)")
        
        if changes:
            await interaction.followup.send("\n".join(changes), ephemeral=True)
        else:
            await interaction.followup.send("✅ Nenhuma alteração necessária.", ephemeral=True)
    
    async def create_role(self, interaction: discord.Interaction):
        """Abre modal para criar cargo."""
        if not self.guild:
            await interaction.response.send_message(
                "❌ Erro: Guild não encontrado.",
                ephemeral=True
            )
            return
        
        async def on_success(inter: discord.Interaction, role: discord.Role):
            # Adiciona automaticamente à lista de permitidos
            await self.db.add_allowed_role(self.guild_id, role.id)
            LOGGER.info(f"Cargo '{role.name}' criado e adicionado aos permitidos para guild {self.guild_id}")
            # Atualiza embed
            embed = await self.setup_view.build_embed()
            await inter.edit_original_response(embed=embed, view=self.setup_view)
        
        modal = CreateRoleModal(guild=self.guild, on_success=on_success)
        await interaction.response.send_modal(modal)


class AFKChannelSelectView(discord.ui.View):
    """View para selecionar canal AFK."""
    
    def __init__(self, db: Database, guild_id: int, setup_view):
        super().__init__(timeout=300)
        self.db = db
        self.guild_id = guild_id
        self.setup_view = setup_view
        
        self.channel_select = discord.ui.ChannelSelect(
            placeholder="Selecione o canal AFK",
            channel_types=[discord.ChannelType.voice],
            min_values=0,
            max_values=1
        )
        self.channel_select.callback = self.on_channel_select
        self.add_item(self.channel_select)
    
    async def on_channel_select(self, interaction: discord.Interaction):
        """Define o canal AFK."""
        await interaction.response.defer(ephemeral=True)
        
        if self.channel_select.values:
            afk_channel_id = self.channel_select.values[0].id
            await self.db.upsert_voice_settings(self.guild_id, afk_channel_id=afk_channel_id)
            await interaction.followup.send(
                f"✅ Canal AFK definido: {self.channel_select.values[0].mention}",
                ephemeral=True
            )
        else:
            await self.db.upsert_voice_settings(self.guild_id, afk_channel_id=None)
            await interaction.followup.send("✅ Canal AFK removido.", ephemeral=True)
        
        # Atualiza a embed
        embed = await self.setup_view.build_embed()
        await interaction.edit_original_response(embed=embed, view=self.setup_view)


class VoiceSetupView(discord.ui.View):
    """View principal de configuração do sistema de pontos por voz."""
    
    def __init__(self, bot: commands.Bot, db: Database, guild_id: int, parent_view=None):
        super().__init__(timeout=300)
        self.bot = bot
        self.db = db
        self.guild_id = guild_id
        self.parent_view = parent_view
        
        # Adiciona botão voltar se parent_view existir
        if self.parent_view:
            self.add_item(BackButton(self.parent_view))
    
    async def build_embed(self) -> discord.Embed:
        """Constrói a embed com as configurações atuais."""
        settings = await self.db.get_voice_settings(self.guild_id)
        monitor_all = settings.get("monitor_all", 0) == 1
        afk_channel_id = settings.get("afk_channel_id")
        
        allowed_roles = await self.db.get_allowed_roles(self.guild_id)
        monitored_channels = await self.db.get_monitored_channels(self.guild_id)
        
        guild = self.bot.get_guild(self.guild_id)
        
        embed = discord.Embed(
            title="⚙️ Configuração do Sistema de Pontos por Voz",
            description="Configure o monitoramento de tempo em call para staff/membros.",
            color=discord.Color.blue()
        )
        
        # Monitorar Tudo
        status = "✅ Ativado" if monitor_all else "❌ Desativado"
        embed.add_field(
            name="📊 Monitorar Tudo",
            value=f"Status: {status}\n"
                  f"Quando ativado, monitora todos os canais de voz automaticamente.",
            inline=False
        )
        
        # Cargos Permitidos
        if allowed_roles:
            roles_str = []
            for role_id in allowed_roles[:10]:  # Limite de 10 para não exceder limite de embed
                role = guild.get_role(role_id) if guild else None
                if role:
                    roles_str.append(role.mention)
                else:
                    roles_str.append(f"`{role_id}` (cargo não encontrado)")
            if len(allowed_roles) > 10:
                roles_str.append(f"\n*+ {len(allowed_roles) - 10} cargo(s) adicional(is)*")
            embed.add_field(
                name=f"👥 Cargos Permitidos ({len(allowed_roles)})",
                value="\n".join(roles_str) if roles_str else "Nenhum",
                inline=False
            )
        else:
            embed.add_field(
                name="👥 Cargos Permitidos",
                value="⚠️ Nenhum cargo configurado. Configure pelo menos um cargo para o sistema funcionar.",
                inline=False
            )
        
        # Canais Monitorados
        if not monitor_all:
            if monitored_channels:
                channels_str = []
                for channel_id in monitored_channels[:10]:  # Limite de 10
                    channel = guild.get_channel(channel_id) if guild else None
                    if channel:
                        channels_str.append(channel.mention)
                    else:
                        channels_str.append(f"`{channel_id}` (canal não encontrado)")
                if len(monitored_channels) > 10:
                    channels_str.append(f"\n*+ {len(monitored_channels) - 10} canal(is) adicional(is)*")
                embed.add_field(
                    name=f"📢 Canais Monitorados ({len(monitored_channels)})",
                    value="\n".join(channels_str) if channels_str else "Nenhum",
                    inline=False
                )
            else:
                embed.add_field(
                    name="📢 Canais Monitorados",
                    value="⚠️ Nenhum canal configurado. Configure canais ou ative 'Monitorar Tudo'.",
                    inline=False
                )
        else:
            embed.add_field(
                name="📢 Canais Monitorados",
                value="✅ Todos os canais de voz (Monitorar Tudo ativado)",
                inline=False
            )
        
        # Canal AFK
        if afk_channel_id:
            afk_channel = guild.get_channel(int(afk_channel_id)) if guild else None
            if afk_channel:
                embed.add_field(
                    name="😴 Canal AFK",
                    value=f"{afk_channel.mention}\nTempo não será contabilizado quando usuários estiverem neste canal.",
                    inline=False
                )
            else:
                embed.add_field(
                    name="😴 Canal AFK",
                    value=f"`{afk_channel_id}` (canal não encontrado)",
                    inline=False
                )
        else:
            embed.add_field(
                name="😴 Canal AFK",
                value="Não configurado",
                inline=False
            )
        
        embed.set_footer(text="Use os botões abaixo para configurar")
        
        return embed
    
    @discord.ui.button(label="Ativar/Desativar Monitorar Tudo", style=discord.ButtonStyle.primary, row=0)
    async def toggle_monitor_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Alterna o estado de Monitorar Tudo."""
        await interaction.response.defer(ephemeral=True)
        
        settings = await self.db.get_voice_settings(self.guild_id)
        current_state = settings.get("monitor_all", 0) == 1
        new_state = not current_state
        
        await self.db.upsert_voice_settings(self.guild_id, monitor_all=new_state)
        
        status = "ativado" if new_state else "desativado"
        await interaction.followup.send(f"✅ Monitorar Tudo {status}.", ephemeral=True)
        
        # Atualiza a embed
        embed = await self.build_embed()
        await interaction.edit_original_response(embed=embed, view=self)
    
    @discord.ui.button(label="Configurar Canais", style=discord.ButtonStyle.secondary, row=0)
    async def configure_channels(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre a view para configurar canais."""
        view = VoiceChannelSelectView(self.db, self.guild_id, self)
        await interaction.response.send_message(
            "📢 Selecione os canais de voz para monitorar:",
            view=view,
            ephemeral=True
        )
    
    @discord.ui.button(label="Configurar Cargos Permitidos", style=discord.ButtonStyle.secondary, row=1)
    async def configure_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre a view para configurar cargos."""
        view = VoiceRoleSelectView(self.db, self.guild_id, self)
        await interaction.response.send_message(
            "👥 Selecione os cargos permitidos para monitoramento:",
            view=view,
            ephemeral=True
        )
    
    @discord.ui.button(label="Configurar Canal AFK", style=discord.ButtonStyle.secondary, row=1)
    async def configure_afk(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre a view para configurar canal AFK."""
        view = AFKChannelSelectView(self.db, self.guild_id, self)
        await interaction.response.send_message(
            "😴 Selecione o canal AFK (ou deixe vazio para remover):",
            view=view,
            ephemeral=True
        )


class VoiceConfigCog(commands.Cog):
    """Cog para configuração do sistema de pontos por voz."""
    
    def __init__(self, bot: commands.Bot, db: Database):
        self.bot = bot
        self.db = db
    
    @commands.command(name="ponto_setup")
    @command_guard("ponto_setup")
    async def ponto_setup(self, ctx: commands.Context):
        """Abre a interface de configuração do sistema de pontos por voz (apenas Staff/Admin).

Uso: !ponto_setup

Exemplos:
- !ponto_setup
"""
        if not ctx.guild:
            await ctx.reply("❌ Use este comando em um servidor.")
            return
        
        view = VoiceSetupView(self.bot, self.db, ctx.guild.id)
        embed = await view.build_embed()
        
        await ctx.reply(embed=embed, view=view)
        
        # Deleta o comando após execução
        try:
            await ctx.message.delete()
        except:
            pass


async def setup(bot):
    """Função de setup para carregamento da extensão."""
    from db import Database
    
    await bot.add_cog(VoiceConfigCog(bot, bot.db))
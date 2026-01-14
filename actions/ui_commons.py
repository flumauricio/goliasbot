"""Componentes reutilizáveis para Views de configuração do bot.

Este módulo centraliza helpers, modals e componentes UI comuns para evitar
importações circulares e garantir consistência entre todas as Views de configuração.
"""

import logging
from typing import Optional, Dict, Any, List, Tuple, Callable, Awaitable

import discord
from discord.ext import commands

LOGGER = logging.getLogger(__name__)


async def build_standard_config_embed(
    title: str,
    description: str,
    current_config: Dict[str, Any],
    guild: discord.Guild,
    footer_text: Optional[str] = None
) -> discord.Embed:
    """Cria embed padronizado para configurações.
    
    Args:
        title: Título do embed (deve incluir emoji)
        description: Descrição do módulo
        current_config: Dicionário com chave=label, valor=status/configuração
        guild: Guild do Discord
        footer_text: Texto opcional para o rodapé
        
    Returns:
        Embed padronizado com campo "Configuração Atual"
    """
    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.blue(),
        timestamp=discord.utils.utcnow()
    )
    
    # Campo "Configuração Atual"
    config_text = []
    for key, value in current_config.items():
        if value:
            config_text.append(f"✅ {key}: {value}")
        else:
            config_text.append(f"❌ {key}: Não configurado")
    
    embed.add_field(
        name="📊 Configuração Atual",
        value="\n".join(config_text) if config_text else "Nenhuma configuração",
        inline=False
    )
    
    if footer_text:
        embed.set_footer(text=footer_text)
    
    return embed


async def check_bot_permissions(
    guild: discord.Guild,
    required_perms: List[str]
) -> Tuple[bool, List[str]]:
    """Verifica se o bot tem permissões necessárias.
    
    Args:
        guild: Guild do Discord
        required_perms: Lista de nomes de permissões (ex: ["manage_channels", "manage_roles"])
        
    Returns:
        Tupla (tem_permissao, permissões_faltando)
    """
    bot_member = guild.get_member(guild.me.id)
    if not bot_member:
        return False, ["Bot member not found"]
    
    missing = []
    for perm in required_perms:
        if not getattr(bot_member.guild_permissions, perm, False):
            missing.append(perm)
    
    return len(missing) == 0, missing


async def _setup_secure_channel_permissions(
    channel: discord.TextChannel,
    staff_roles: List[discord.Role]
) -> None:
    """Configura permissões automáticas para canais sensíveis.
    
    Oculta o canal de @everyone e permite acesso apenas para staff/admin.
    
    Args:
        channel: Canal de texto a configurar
        staff_roles: Lista de cargos de staff/admin que terão acesso
    """
    overwrites = {
        channel.guild.default_role: discord.PermissionOverwrite(view_channel=False),
        channel.guild.me: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            manage_messages=True,
            read_message_history=True
        )
    }
    
    # Adiciona permissões para cargos de staff/admin
    for role in staff_roles:
        if role:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            )
    
    # Aplica as permissões
    try:
        await channel.edit(overwrites=overwrites)
    except discord.Forbidden:
        LOGGER.warning("Não foi possível configurar permissões do canal %s", channel.id)
    except Exception as e:
        LOGGER.error("Erro ao configurar permissões do canal %s: %s", channel.id, e)


class BackButton(discord.ui.Button):
    """Botão padronizado para voltar ao dashboard principal."""
    
    def __init__(self, parent_view, row: int = 4):
        super().__init__(label="⬅️ Voltar", style=discord.ButtonStyle.secondary, row=row)
        self.parent_view = parent_view
    
    async def callback(self, interaction: discord.Interaction):
        embed = await self.parent_view.build_embed()
        await interaction.response.edit_message(embed=embed, view=self.parent_view)


class CreateChannelModal(discord.ui.Modal):
    """Modal reutilizável para criar canais com verificação de idempotência."""
    
    def __init__(
        self,
        guild: discord.Guild,
        title: str = "Criar Novo Canal",
        channel_name_label: str = "Nome do Canal",
        channel_type: discord.ChannelType = discord.ChannelType.text,
        is_sensitive: bool = False,
        staff_roles: Optional[List[discord.Role]] = None,
        on_success: Optional[Callable[[discord.Interaction, discord.abc.GuildChannel], Awaitable[None]]] = None
    ):
        super().__init__(title=title)
        self.guild = guild
        self.channel_type = channel_type
        self.is_sensitive = is_sensitive
        self.staff_roles = staff_roles or []
        self.on_success = on_success
        
        self.channel_name_input = discord.ui.TextInput(
            label=channel_name_label,
            placeholder="Ex: canal-exemplo",
            required=True,
            max_length=100
        )
        self.add_item(self.channel_name_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Cria o canal com verificação de idempotência."""
        await interaction.response.defer(ephemeral=True)
        
        channel_name = self.channel_name_input.value.strip()
        if not channel_name:
            await interaction.followup.send("❌ O nome do canal não pode estar vazio.", ephemeral=True)
            return
        
        # Verificação de permissões
        has_perm, missing = await check_bot_permissions(
            self.guild,
            ["manage_channels"]
        )
        if not has_perm:
            await interaction.followup.send(
                f"❌ O bot não tem permissão 'Gerenciar Canais'. Permissões faltando: {', '.join(missing)}",
                ephemeral=True
            )
            return
        
        # Verificação de idempotência
        existing = None
        if self.channel_type == discord.ChannelType.text:
            existing = discord.utils.get(self.guild.text_channels, name=channel_name)
        elif self.channel_type == discord.ChannelType.voice:
            existing = discord.utils.get(self.guild.voice_channels, name=channel_name)
        elif self.channel_type == discord.ChannelType.category:
            existing = discord.utils.get(self.guild.categories, name=channel_name)
        
        if existing:
            await interaction.followup.send(
                f"⚠️ Canal '{channel_name}' já existe: {existing.mention}\n"
                f"Use o seletor acima para escolher este canal.",
                ephemeral=True
            )
            return
        
        # Cria o canal
        try:
            if self.channel_type == discord.ChannelType.text:
                channel = await self.guild.create_text_channel(
                    name=channel_name,
                    reason=f"Canal criado via Dashboard por {interaction.user}"
                )
            elif self.channel_type == discord.ChannelType.voice:
                channel = await self.guild.create_voice_channel(
                    name=channel_name,
                    reason=f"Canal criado via Dashboard por {interaction.user}"
                )
            elif self.channel_type == discord.ChannelType.category:
                channel = await self.guild.create_category(
                    name=channel_name,
                    reason=f"Categoria criada via Dashboard por {interaction.user}"
                )
            else:
                await interaction.followup.send("❌ Tipo de canal não suportado.", ephemeral=True)
                return
            
            # Aplica permissões automáticas se for sensível
            if self.is_sensitive and isinstance(channel, discord.TextChannel):
                await _setup_secure_channel_permissions(channel, self.staff_roles)
            
            # Chama callback de sucesso
            if self.on_success:
                await self.on_success(interaction, channel)
            
            await interaction.followup.send(
                f"✅ Canal '{channel_name}' criado com sucesso: {channel.mention}",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Não foi possível criar o canal. Verifique as permissões do bot.",
                ephemeral=True
            )
        except Exception as e:
            LOGGER.error("Erro ao criar canal: %s", e, exc_info=True)
            await interaction.followup.send(
                "❌ Erro ao criar canal. Tente novamente.",
                ephemeral=True
            )


class CreateRoleModal(discord.ui.Modal):
    """Modal reutilizável para criar cargos com verificação de hierarquia."""
    
    def __init__(
        self,
        guild: discord.Guild,
        title: str = "Criar Novo Cargo",
        role_name_label: str = "Nome do Cargo",
        on_success: Optional[Callable[[discord.Interaction, discord.Role], Awaitable[None]]] = None
    ):
        super().__init__(title=title)
        self.guild = guild
        self.on_success = on_success
        
        self.role_name_input = discord.ui.TextInput(
            label=role_name_label,
            placeholder="Ex: Moderador",
            required=True,
            max_length=100
        )
        self.add_item(self.role_name_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Cria o cargo com verificação de hierarquia."""
        await interaction.response.defer(ephemeral=True)
        
        role_name = self.role_name_input.value.strip()
        if not role_name:
            await interaction.followup.send("❌ O nome do cargo não pode estar vazio.", ephemeral=True)
            return
        
        # Verificação de permissões
        has_perm, missing = await check_bot_permissions(
            self.guild,
            ["manage_roles"]
        )
        if not has_perm:
            await interaction.followup.send(
                f"❌ O bot não tem permissão 'Gerenciar Cargos'. Permissões faltando: {', '.join(missing)}",
                ephemeral=True
            )
            return
        
        # Verificação de idempotência
        existing = discord.utils.get(self.guild.roles, name=role_name)
        if existing:
            await interaction.followup.send(
                f"⚠️ Cargo '{role_name}' já existe: {existing.mention}\n"
                f"Use o seletor acima para escolher este cargo.",
                ephemeral=True
            )
            return
        
        # Cria o cargo
        try:
            role = await self.guild.create_role(
                name=role_name,
                reason=f"Cargo criado via Dashboard por {interaction.user}"
            )
            
            # Verifica hierarquia (cargo não pode estar acima do bot)
            bot_member = self.guild.get_member(self.guild.me.id)
            if bot_member and bot_member.top_role:
                if role.position >= bot_member.top_role.position:
                    await interaction.followup.send(
                        f"❌ Não foi possível criar o cargo. O cargo '{role_name}' estaria acima do cargo do bot na hierarquia.\n"
                        f"Por favor, mova o cargo do bot acima na hierarquia ou crie um cargo com posição menor.",
                        ephemeral=True
                    )
                    # Tenta deletar o cargo criado
                    try:
                        await role.delete()
                    except:
                        pass
                    return
            
            # Chama callback de sucesso
            if self.on_success:
                await self.on_success(interaction, role)
            
            await interaction.followup.send(
                f"✅ Cargo '{role_name}' criado com sucesso: {role.mention}",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Não foi possível criar o cargo. Verifique:\n"
                "• O bot tem permissão 'Gerenciar Cargos'\n"
                "• O cargo não está acima do cargo do bot na hierarquia",
                ephemeral=True
            )
        except Exception as e:
            LOGGER.error("Erro ao criar cargo: %s", e, exc_info=True)
            await interaction.followup.send(
                "❌ Erro ao criar cargo. Tente novamente.",
                ephemeral=True
            )

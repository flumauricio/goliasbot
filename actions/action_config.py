import logging
from typing import Optional

import discord
from discord.ext import commands

from db import Database

from .action_config_channel import ChannelSelectView
from .ui_commons import BackButton, CreateChannelModal, CreateRoleModal, build_standard_config_embed, check_bot_permissions, _setup_secure_channel_permissions

LOGGER = logging.getLogger(__name__)


class ActionTypeModal(discord.ui.Modal, title="Criar Tipo de Ação"):
    """Modal para criar um novo tipo de ação."""
    
    def __init__(self, db: Database, guild_id: int, setup_view):
        super().__init__()
        self.db = db
        self.guild_id = guild_id
        self.setup_view = setup_view
    
    name_input = discord.ui.TextInput(
        label="Nome da Ação",
        placeholder="Ex: Assalto a Banco",
        required=True,
        max_length=100
    )
    
    min_players_input = discord.ui.TextInput(
        label="Mínimo de Players",
        placeholder="2",
        required=True,
        max_length=3
    )
    
    max_players_input = discord.ui.TextInput(
        label="Máximo de Players",
        placeholder="10",
        required=True,
        max_length=3
    )
    
    total_value_input = discord.ui.TextInput(
        label="Valor Total (R$)",
        placeholder="50000.00",
        required=True,
        max_length=20
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        """Valida e cria o tipo de ação."""
        try:
            # Validação de valores
            try:
                min_players = int(self.min_players_input.value)
                max_players = int(self.max_players_input.value)
                total_value = float(self.total_value_input.value.replace(",", "."))
            except ValueError:
                await interaction.response.send_message(
                    "❌ Valores inválidos. Use números válidos.",
                    ephemeral=True
                )
                return
            
            # Validações de negócio
            if min_players < 1:
                await interaction.response.send_message(
                    "❌ O mínimo de players deve ser pelo menos 1.",
                    ephemeral=True
                )
                return
            
            if max_players < min_players:
                await interaction.response.send_message(
                    "❌ O máximo de players deve ser maior ou igual ao mínimo.",
                    ephemeral=True
                )
                return
            
            if total_value <= 0:
                await interaction.response.send_message(
                    "❌ O valor total deve ser maior que zero.",
                    ephemeral=True
                )
                return
            
            # Cria o tipo de ação
            type_id = await self.db.add_action_type(
                self.guild_id,
                self.name_input.value.strip(),
                min_players,
                max_players,
                total_value
            )
            
            await interaction.response.send_message(
                f"✅ Tipo de ação **{self.name_input.value}** criado com sucesso!",
                ephemeral=True
            )
            
            # Atualiza a embed do setup
            await self.setup_view.update_embed()
            
        except Exception as exc:
            LOGGER.error("Erro ao criar tipo de ação: %s", exc, exc_info=True)
            await interaction.response.send_message(
                "❌ Erro ao criar tipo de ação. Tente novamente.",
                ephemeral=True
            )


class EditActionTypeModal(discord.ui.Modal, title="Editar Tipo de Ação"):
    """Modal para editar um tipo de ação existente."""
    
    def __init__(self, db: Database, type_id: int, action_type: dict, setup_view):
        super().__init__()
        self.db = db
        self.type_id = type_id
        self.action_type = action_type
        self.setup_view = setup_view
        
        # Cria os campos de texto com valores padrão
        self.name_input = discord.ui.TextInput(
            label="Nome da Ação",
            placeholder="Ex: Assalto a Banco",
            required=True,
            max_length=100,
            default=action_type.get('name', '')
        )
        
        self.min_players_input = discord.ui.TextInput(
            label="Mínimo de Players",
            placeholder="2",
            required=True,
            max_length=3,
            default=str(action_type.get('min_players', 1))
        )
        
        self.max_players_input = discord.ui.TextInput(
            label="Máximo de Players",
            placeholder="10",
            required=True,
            max_length=3,
            default=str(action_type.get('max_players', 1))
        )
        
        self.total_value_input = discord.ui.TextInput(
            label="Valor Total (R$)",
            placeholder="50000.00",
            required=True,
            max_length=20,
            default=str(action_type.get('total_value', 0.0))
        )
        
        # Adiciona os campos ao modal
        self.add_item(self.name_input)
        self.add_item(self.min_players_input)
        self.add_item(self.max_players_input)
        self.add_item(self.total_value_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Valida e atualiza o tipo de ação."""
        try:
            # Validação de valores
            try:
                min_players = int(self.min_players_input.value)
                max_players = int(self.max_players_input.value)
                total_value = float(self.total_value_input.value.replace(",", "."))
            except ValueError:
                await interaction.response.send_message(
                    "❌ Valores inválidos. Use números válidos.",
                    ephemeral=True
                )
                return
            
            # Validações de negócio
            if min_players < 1:
                await interaction.response.send_message(
                    "❌ O mínimo de players deve ser pelo menos 1.",
                    ephemeral=True
                )
                return
            
            if max_players < min_players:
                await interaction.response.send_message(
                    "❌ O máximo de players deve ser maior ou igual ao mínimo.",
                    ephemeral=True
                )
                return
            
            if total_value <= 0:
                await interaction.response.send_message(
                    "❌ O valor total deve ser maior que zero.",
                    ephemeral=True
                )
                return
            
            # Atualiza o tipo de ação
            await self.db.update_action_type(
                self.type_id,
                self.name_input.value.strip(),
                min_players,
                max_players,
                total_value
            )
            
            await interaction.response.send_message(
                f"✅ Tipo de ação **{self.name_input.value}** atualizado com sucesso!",
                ephemeral=True
            )
            
            # Atualiza a embed do setup
            await self.setup_view.update_embed()
            
        except Exception as exc:
            LOGGER.error("Erro ao atualizar tipo de ação: %s", exc, exc_info=True)
            await interaction.response.send_message(
                "❌ Erro ao atualizar tipo de ação. Tente novamente.",
                ephemeral=True
            )


class ManageActionView(discord.ui.View):
    """View para gerenciar (editar/deletar) um tipo de ação."""
    
    def __init__(self, db: Database, type_id: int, action_type: dict, setup_view):
        super().__init__(timeout=300)
        self.db = db
        self.type_id = type_id
        self.action_type = action_type
        self.setup_view = setup_view
    
    @discord.ui.button(label="✏️ Editar", style=discord.ButtonStyle.primary, row=0)
    async def edit_action(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre modal para editar a ação."""
        modal = EditActionTypeModal(self.db, self.type_id, self.action_type, self.setup_view)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🗑️ Deletar", style=discord.ButtonStyle.danger, row=0)
    async def delete_action(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre view de confirmação para deletar."""
        delete_view = DeleteActionView(
            self.db,
            self.type_id,
            self.action_type['name'],
            self.setup_view
        )
        embed = discord.Embed(
            title="⚠️ Confirmar Exclusão",
            description=f"Tem certeza que deseja deletar o tipo de ação **{self.action_type['name']}**?\n\nEsta ação não pode ser desfeita!",
            color=discord.Color.red()
        )
        await interaction.response.send_message(
            embed=embed,
            view=delete_view,
            ephemeral=True
        )


class DeleteActionView(discord.ui.View):
    """View de confirmação para deletar tipo de ação."""
    
    def __init__(self, db: Database, type_id: int, type_name: str, setup_view):
        super().__init__(timeout=60)
        self.db = db
        self.type_id = type_id
        self.type_name = type_name
        self.setup_view = setup_view
    
    @discord.ui.button(label="✅ Confirmar", style=discord.ButtonStyle.danger, custom_id="confirm_delete_action")
    async def confirm_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirma a exclusão."""
        try:
            await self.db.delete_action_type(self.type_id)
            await interaction.response.send_message(
                f"✅ Tipo de ação **{self.type_name}** deletado com sucesso!",
                ephemeral=True
            )
            await self.setup_view.update_embed()
        except Exception as exc:
            LOGGER.error("Erro ao deletar tipo de ação: %s", exc, exc_info=True)
            await interaction.response.send_message(
                "❌ Erro ao deletar tipo de ação.",
                ephemeral=True
            )
    
    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.secondary, custom_id="cancel_delete_action")
    async def cancel_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancela a exclusão."""
        await interaction.response.send_message("❌ Exclusão cancelada.", ephemeral=True)
        self.stop()


class DeleteAllActionsView(discord.ui.View):
    """View de confirmação para deletar todas as ações."""
    
    def __init__(self, db: Database, guild_id: int, setup_view):
        super().__init__(timeout=60)
        self.db = db
        self.guild_id = guild_id
        self.setup_view = setup_view
    
    @discord.ui.button(label="✅ Confirmar", style=discord.ButtonStyle.danger, custom_id="confirm_delete_all_actions")
    async def confirm_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirma a exclusão de todas as ações."""
        try:
            await self.db.reset_all_actions(self.guild_id)
            
            # Atualiza ranking após reset
            from .action_system import update_ranking_message
            guild = interaction.guild
            if guild and self.setup_view.bot:
                await update_ranking_message(
                    self.guild_id,
                    guild,
                    self.db,
                    self.setup_view.bot
                )
            
            await interaction.response.send_message(
                "✅ Todas as ações ativas foram removidas, estatísticas zeradas e IDs resetados!\n"
                "Os tipos de ação cadastrados foram mantidos.",
                ephemeral=True
            )
            await self.setup_view.update_embed()
        except Exception as exc:
            LOGGER.error("Erro ao deletar todas as ações: %s", exc, exc_info=True)
            await interaction.response.send_message(
                "❌ Erro ao deletar ações.",
                ephemeral=True
            )
    
    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.secondary, custom_id="cancel_delete_all_actions")
    async def cancel_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancela a exclusão."""
        await interaction.response.send_message("❌ Exclusão cancelada.", ephemeral=True)
        self.stop()


class ActionSetupView(discord.ui.View):
    """View principal de configuração de ações."""
    
    def __init__(self, bot: commands.Bot, db: Database, guild: discord.Guild, parent_view=None):
        super().__init__(timeout=None)
        self.bot = bot
        self.db = db
        self.guild = guild
        self.parent_view = parent_view
        self.selected_type_id: Optional[int] = None
        self.setup_message: Optional[discord.Message] = None
        
        # Adiciona botão voltar se parent_view existir
        if self.parent_view:
            self.add_item(BackButton(self.parent_view))
    
    async def update_embed(self, interaction: Optional[discord.Interaction] = None):
        """Atualiza a embed de configuração."""
        embed = await self.build_embed()
        try:
            # Tenta atualizar a mensagem do setup se disponível
            if self.setup_message:
                await self.setup_message.edit(embed=embed, view=self)
            elif interaction:
                if interaction.response.is_done():
                    # Interação já foi respondida, tenta buscar mensagem original
                    try:
                        message = await interaction.original_response()
                        await message.edit(embed=embed, view=self)
                    except (discord.NotFound, AttributeError):
                        # Tenta usar a mensagem da interação se disponível
                        if hasattr(interaction, 'message') and interaction.message:
                            await interaction.message.edit(embed=embed, view=self)
                        else:
                            LOGGER.warning("Não foi possível atualizar embed: mensagem não encontrada")
                else:
                    await interaction.response.edit_message(embed=embed, view=self)
        except (discord.NotFound, discord.Forbidden, AttributeError) as e:
            LOGGER.warning("Não foi possível atualizar o embed: %s", e)
        except Exception as exc:
            LOGGER.warning("Erro ao atualizar embed: %s", exc)
    
    async def build_embed(self) -> discord.Embed:
        """Constrói a embed de configuração."""
        settings = await self.db.get_action_settings(self.guild.id)
        action_types = await self.db.get_action_types(self.guild.id)
        
        embed = discord.Embed(
            title="⚙️ Configuração de Ações FiveM",
            description="Gerencie os tipos de ações e configurações do sistema.",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        
        # Cargos Responsáveis (múltiplos)
        responsible_roles = await self.db.get_responsible_roles(self.guild.id)
        if responsible_roles:
            role_mentions = []
            for role_id in responsible_roles:
                role = self.guild.get_role(role_id)
                if role:
                    role_mentions.append(role.mention)
                else:
                    role_mentions.append(f"⚠️ <@&{role_id}> (não encontrado)")
            
            embed.add_field(
                name=f"👮 Cargos Responsáveis ({len(responsible_roles)})",
                value=", ".join(role_mentions) if role_mentions else "Nenhum cargo válido",
                inline=False
            )
        else:
            embed.add_field(
                name="👮 Cargos Responsáveis",
                value="❌ Nenhum cargo configurado",
                inline=False
            )
        
        # Canal de Ações
        action_channel_id = settings.get("action_channel_id")
        if action_channel_id and str(action_channel_id).isdigit():
            channel = self.guild.get_channel(int(action_channel_id))
            if channel:
                embed.add_field(
                    name="📢 Canal de Ações",
                    value=channel.mention,
                    inline=False
                )
            else:
                embed.add_field(
                    name="📢 Canal de Ações",
                    value=f"⚠️ Canal não encontrado (ID: {action_channel_id})",
                    inline=False
                )
        else:
            embed.add_field(
                name="📢 Canal de Ações",
                value="❌ Não configurado",
                inline=False
            )
        
        # Canal de Ranking
        ranking_channel_id = settings.get("ranking_channel_id")
        if ranking_channel_id and str(ranking_channel_id).isdigit():
            channel = self.guild.get_channel(int(ranking_channel_id))
            if channel:
                embed.add_field(
                    name="📊 Canal de Ranking",
                    value=channel.mention,
                    inline=False
                )
            else:
                embed.add_field(
                    name="📊 Canal de Ranking",
                    value=f"⚠️ Canal não encontrado (ID: {ranking_channel_id})",
                    inline=False
                )
        else:
            embed.add_field(
                name="📊 Canal de Ranking",
                value="❌ Não configurado",
                inline=False
            )
        
        # Lista de tipos de ação
        if action_types:
            types_list = []
            for action_type in action_types:
                types_list.append(
                    f"**{action_type['name']}** - "
                    f"Min: {action_type['min_players']} | "
                    f"Max: {action_type['max_players']} | "
                    f"Valor: R$ {action_type['total_value']:,.2f}"
                )
            embed.add_field(
                name=f"📋 Tipos de Ação ({len(action_types)})",
                value="\n".join(types_list[:10]) + (f"\n*+ {len(types_list) - 10} mais*" if len(types_list) > 10 else ""),
                inline=False
            )
        else:
            embed.add_field(
                name="📋 Tipos de Ação",
                value="❌ Nenhuma ação cadastrada",
                inline=False
            )
        
        embed.set_footer(text="Use os menus e botões abaixo para gerenciar")
        
        return embed
    
    @discord.ui.select(
        placeholder="Selecione uma ação para gerenciar...",
        min_values=1,
        max_values=1,
        row=0
    )
    async def select_action_type(self, interaction: discord.Interaction, select: discord.ui.Select):
        """Select menu para escolher tipo de ação ou criar nova."""
        if not select.values:
            return
        
        value = select.values[0]
        
        if value == "create_new":
            # Abre modal para criar nova ação
            modal = ActionTypeModal(self.db, self.guild.id, self)
            await interaction.response.send_modal(modal)
        elif value.startswith("manage_"):
            # Abre view para editar/deletar ação
            type_id = int(value.split("_")[1])
            action_types = await self.db.get_action_types(self.guild.id)
            action_type = next((at for at in action_types if at["id"] == type_id), None)
            
            if action_type:
                manage_view = ManageActionView(self.db, type_id, action_type, self)
                embed = discord.Embed(
                    title=f"⚙️ Gerenciar: {action_type['name']}",
                    description=(
                        f"**Mínimo:** {action_type['min_players']} players\n"
                        f"**Máximo:** {action_type['max_players']} players\n"
                        f"**Valor Total:** R$ {action_type['total_value']:,.2f}"
                    ),
                    color=discord.Color.blue()
                )
                await interaction.response.send_message(
                    embed=embed,
                    view=manage_view,
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "❌ Tipo de ação não encontrado.",
                    ephemeral=True
                )
        else:
            await interaction.response.send_message(
                "ℹ️ Selecione uma opção válida.",
                ephemeral=True
            )
    
    async def _update_select_options(self):
        """Atualiza as opções do select menu dinamicamente."""
        action_types = await self.db.get_action_types(self.guild.id)
        
        options = [
            discord.SelectOption(
                label="➕ Criar Nova Ação",
                value="create_new",
                description="Criar um novo tipo de ação",
                emoji="➕"
            )
        ]
        
        for action_type in action_types:
            options.append(
                discord.SelectOption(
                    label=action_type["name"],
                    value=f"manage_{action_type['id']}",
                    description=f"Gerenciar: {action_type['name']}",
                    emoji="⚙️"
                )
            )
        
        # Atualiza o select menu
        if len(self.children) > 0 and isinstance(self.children[0], discord.ui.Select):
            self.children[0].options = options
    
    @discord.ui.button(
        label="⚙️ Gerenciar Cargos Responsáveis",
        style=discord.ButtonStyle.primary,
        row=1,
        custom_id="action_setup_role"
    )
    async def configure_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre view para gerenciar cargos responsáveis."""
        view = RoleSelectView(self.db, self.guild.id, self, self.guild)
        current_roles = await self.db.get_responsible_roles(self.guild.id)
        roles_text = ", ".join([f"<@&{r_id}>" for r_id in current_roles[:5]]) if current_roles else "Nenhum"
        if len(current_roles) > 5:
            roles_text += f" e mais {len(current_roles) - 5}"
        
        embed = discord.Embed(
            title="👮 Gerenciar Cargos Responsáveis",
            description=f"**Cargos atuais:** {roles_text}\n\nUse os menus abaixo para adicionar ou remover cargos.",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(
            embed=embed,
            view=view,
            ephemeral=True
        )
    
    @discord.ui.button(
        label="📢 Configurar Canal de Ações",
        style=discord.ButtonStyle.primary,
        row=1,
        custom_id="action_setup_channel"
    )
    async def configure_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre view para configurar canal de ações."""
        view = ChannelSelectView(self.db, self.guild.id, self, self.guild)
        await interaction.response.send_message(
            "📢 Selecione um canal existente ou crie um novo:",
            view=view,
            ephemeral=True
        )
    
    @discord.ui.button(
        label="📊 Configurar Canal de Ranking",
        style=discord.ButtonStyle.primary,
        row=2,
        custom_id="action_setup_ranking_channel"
    )
    async def configure_ranking_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre view para configurar canal de ranking."""
        from .action_config_channel import RankingChannelSelectView
        view = RankingChannelSelectView(self.db, self.guild.id, self, self.guild)
        await interaction.response.send_message(
            "📊 Selecione um canal existente ou crie um novo para o ranking:",
            view=view,
            ephemeral=True
        )
    
    @discord.ui.button(
        label="📋 Listar Ações Cadastradas",
        style=discord.ButtonStyle.secondary,
        row=2,
        custom_id="action_setup_list"
    )
    async def list_actions(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Lista todas as ações cadastradas."""
        action_types = await self.db.get_action_types(self.guild.id)
        
        if not action_types:
            await interaction.response.send_message(
                "❌ Nenhuma ação cadastrada ainda.",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="📋 Tipos de Ação Cadastrados",
            color=discord.Color.blue()
        )
        
        for action_type in action_types:
            embed.add_field(
                name=f"{action_type['name']} (ID: {action_type['id']})",
                value=(
                    f"**Mínimo:** {action_type['min_players']} players\n"
                    f"**Máximo:** {action_type['max_players']} players\n"
                    f"**Valor Total:** R$ {action_type['total_value']:,.2f}"
                ),
                inline=True
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.ui.button(
        label="🗑️ Resetar Ações Ativas",
        style=discord.ButtonStyle.danger,
        row=2,
        custom_id="action_setup_delete_all"
    )
    async def delete_all_actions(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Remove todas as ações ativas, zera stats, mas mantém tipos de ação."""
        # Verifica permissões
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Apenas administradores podem remover todas as ações.",
                ephemeral=True
            )
            return
        
        # Cria view de confirmação
        confirm_view = DeleteAllActionsView(self.db, self.guild.id, self)
        embed = discord.Embed(
            title="⚠️ Confirmar Exclusão",
            description=(
                "Tem certeza que deseja **resetar todas as ações ativas**?\n\n"
                "Esta ação irá:\n"
                "• Deletar todas as ações ativas (em andamento)\n"
                "• Zerar estatísticas de todos os usuários\n"
                "• Resetar os IDs das ações (começar do zero)\n"
                "• **Manter os tipos de ação cadastrados intactos**\n\n"
                "**Esta ação não pode ser desfeita!**"
            ),
            color=discord.Color.red()
        )
        await interaction.response.send_message(
            embed=embed,
            view=confirm_view,
            ephemeral=True
        )
    
    @discord.ui.button(
        label="✅ Finalizar",
        style=discord.ButtonStyle.success,
        row=2,
        custom_id="action_setup_finish"
    )
    async def finish_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Finaliza a configuração."""
        await interaction.response.send_message(
            "✅ Configuração finalizada! Use `!acao` para criar ações.",
            ephemeral=True
        )


class CreateRoleModal(discord.ui.Modal, title="Criar Novo Cargo"):
    """Modal para criar um novo cargo responsável."""
    
    def __init__(self, db: Database, guild_id: int, setup_view, guild: discord.Guild):
        super().__init__()
        self.db = db
        self.guild_id = guild_id
        self.setup_view = setup_view
        self.guild = guild
    
    role_name_input = discord.ui.TextInput(
        label="Nome do Cargo",
        placeholder="Ex: Responsável por Ações",
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
        """Cria o cargo e configura como responsável."""
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
                    reason=f"Cargo criado via !acao_setup por {interaction.user}"
                )
                
                # Adiciona como cargo responsável
                await self.db.add_responsible_role(self.guild_id, role.id)
                
                await interaction.response.send_message(
                    f"✅ Cargo **{role.name}** criado e configurado como responsável! {role.mention}",
                    ephemeral=True
                )
                
                # Atualiza embed do setup (sem passar interaction)
                await self.setup_view.update_embed()
                
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
            await interaction.response.send_message(
                "❌ Erro ao processar. Tente novamente.",
                ephemeral=True
            )


class RoleSelectView(discord.ui.View):
    """View para gerenciar múltiplos cargos responsáveis."""
    
    def __init__(self, db: Database, guild_id: int, setup_view, guild: discord.Guild):
        super().__init__(timeout=300)
        self.db = db
        self.guild_id = guild_id
        self.setup_view = setup_view
        self.guild = guild
    
    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="Selecione cargos para adicionar...",
        min_values=0,
        max_values=25,
        row=0
    )
    async def add_roles(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        """Adiciona cargos responsáveis - salvamento automático."""
        await interaction.response.defer(ephemeral=True)
        
        if not select.values:
            await interaction.followup.send(
                "❌ Nenhum cargo selecionado.",
                ephemeral=True
            )
            return
        
        # Filtra @everyone (cargo com ID igual ao guild_id)
        filtered_roles = [role for role in select.values if role.id != self.guild.id]
        if not filtered_roles:
            await interaction.followup.send(
                "⚠️ O cargo @everyone não pode ser usado. Selecione outros cargos.",
                ephemeral=True
            )
            return
        
        added = []
        already_existing = []
        current_roles = await self.db.get_responsible_roles(self.guild_id)
        
        for role in filtered_roles:
            if role.id in current_roles:
                already_existing.append(role.mention)
            else:
                await self.db.add_responsible_role(self.guild_id, role.id)
                added.append(role.mention)
        
        # Atualiza embed imediatamente
        await self.setup_view.update_embed(interaction)
        
        # Confirmação efêmera
        message_parts = []
        if added:
            message_parts.append(f"✅ Adicionados: {', '.join(added)}")
        if already_existing:
            message_parts.append(f"ℹ️ Já existiam: {', '.join(already_existing)}")
        
        await interaction.followup.send(
            "\n".join(message_parts) if message_parts else "✅ Configurado",
            ephemeral=True
        )
    
    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="Selecione cargos para remover...",
        min_values=0,
        max_values=25,
        row=1
    )
    async def remove_roles(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        """Remove cargos responsáveis - salvamento automático."""
        await interaction.response.defer(ephemeral=True)
        
        if not select.values:
            await interaction.followup.send(
                "❌ Nenhum cargo selecionado.",
                ephemeral=True
            )
            return
        
        # Filtra @everyone (cargo com ID igual ao guild_id)
        filtered_roles = [role for role in select.values if role.id != self.guild.id]
        
        removed = []
        not_found = []
        current_roles = await self.db.get_responsible_roles(self.guild_id)
        
        for role in filtered_roles:
            if role.id in current_roles:
                await self.db.remove_responsible_role(self.guild_id, role.id)
                removed.append(role.mention)
            else:
                not_found.append(role.mention)
        
        # Atualiza embed imediatamente
        await self.setup_view.update_embed(interaction)
        
        # Confirmação efêmera
        message_parts = []
        if removed:
            message_parts.append(f"✅ Removidos: {', '.join(removed)}")
        if not_found:
            message_parts.append(f"ℹ️ Não estavam configurados: {', '.join(not_found)}")
        
        await interaction.followup.send(
            "\n".join(message_parts) if message_parts else "✅ Configurado",
            ephemeral=True
        )
    
    @discord.ui.button(
        label="➕ Criar Novo Cargo",
        style=discord.ButtonStyle.success,
        row=3,
        emoji="➕"
    )
    async def create_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre modal para criar novo cargo."""
        modal = CreateRoleModal(self.db, self.guild_id, self.setup_view, self.guild)
        await interaction.response.send_modal(modal)


class ActionConfigCog(commands.Cog):
    """Cog para configuração do sistema de ações."""
    
    def __init__(self, bot: commands.Bot, db: Database):
        self.bot = bot
        self.db = db
    
    async def _check_permissions(self, member: discord.Member) -> bool:
        """Verifica se o membro tem permissão (admin ou cargo responsável)."""
        if member.guild_permissions.administrator:
            return True
        
        settings = await self.db.get_action_settings(member.guild.id)
        responsible_role_id = settings.get("responsible_role_id")
        
        if responsible_role_id and str(responsible_role_id).isdigit():
            role = member.guild.get_role(int(responsible_role_id))
            if role and role in member.roles:
                return True
        
        return False
    
    @commands.command(name="acao_setup")
    async def action_setup(self, ctx: commands.Context):
        """Abre interface de configuração do sistema de ações FiveM (apenas administradores).

Uso: !acao_setup

Exemplos:
- !acao_setup
"""
        if not ctx.guild:
            await ctx.reply("❌ Use este comando em um servidor.")
            return
        
        if not await self._check_permissions(ctx.author):
            await ctx.reply(
                "❌ Você não tem permissão para usar este comando.\n"
                "É necessário ser administrador ou ter o cargo responsável configurado.",
                delete_after=10
            )
            return
        
        view = ActionSetupView(self.bot, self.db, ctx.guild)
        await view._update_select_options()
        embed = await view.build_embed()
        
        message = await ctx.reply(embed=embed, view=view)
        view.setup_message = message
        
        # Deleta o comando
        try:
            await ctx.message.delete()
        except:
            pass


async def setup(bot):
    """Função de setup para carregamento da extensão."""
    from db import Database
    
    await bot.add_cog(ActionConfigCog(bot, bot.db))
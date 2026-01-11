import logging
from typing import Optional, Callable, Awaitable

import discord
from discord.ext import commands

from db import Database

LOGGER = logging.getLogger(__name__)


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
    
    def __init__(self, parent_view, row=4):
        super().__init__(label="⬅️ Voltar", style=discord.ButtonStyle.secondary, row=row)
        self.parent_view = parent_view
    
    async def callback(self, interaction: discord.Interaction):
        """Retorna ao dashboard principal."""
        embed = await self.parent_view.build_embed()
        await interaction.response.edit_message(embed=embed, view=self.parent_view)


class CommandSelectView(discord.ui.View):
    """View para selecionar um comando para configurar."""
    
    def __init__(self, bot: commands.Bot, db: Database, guild: discord.Guild, permissions_view):
        super().__init__(timeout=300)
        self.bot = bot
        self.db = db
        self.guild = guild
        self.permissions_view = permissions_view
        
        # Cria select menu com comandos
        self.command_select = discord.ui.Select(
            placeholder="Selecione um comando para configurar",
            min_values=1,
            max_values=1,
            row=0
        )
        self._update_options()
        self.command_select.callback = self.on_command_select
        self.add_item(self.command_select)
        
        # Botão voltar
        if self.permissions_view.parent_view:
            self.add_item(BackButton(self.permissions_view.parent_view, row=4))
        else:
            self.add_item(BackButton(self.permissions_view, row=4))
    
    def _update_options(self):
        """Atualiza as opções do select com comandos configuráveis."""
        configurable = [
            cmd for cmd in self.bot.commands
            if not cmd.hidden and cmd.name not in ("setup", "setup_cargos")
        ]
        
        options = []
        for cmd in configurable[:25]:  # Limite de 25 opções
            options.append(
                discord.SelectOption(
                    label=f"!{cmd.name}",
                    value=cmd.name,
                    description=cmd.brief or cmd.description[:100] if cmd.description else None
                )
            )
        
        self.command_select.options = options
    
    async def on_command_select(self, interaction: discord.Interaction):
        """Abre view para configurar permissões do comando selecionado."""
        command_name = self.command_select.values[0]
        view = CommandPermissionsView(self.bot, self.db, self.guild, command_name, self.permissions_view)
        embed = await view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)


class CommandPermissionsView(discord.ui.View):
    """View para configurar permissões de um comando específico."""
    
    def __init__(self, bot: commands.Bot, db: Database, guild: discord.Guild, command_name: str, permissions_view):
        super().__init__(timeout=300)
        self.bot = bot
        self.db = db
        self.guild = guild
        self.command_name = command_name
        self.permissions_view = permissions_view
        
        # Role select
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
        
        # Botão voltar (se permissions_view tiver parent_view, volta para dashboard)
        if self.permissions_view.parent_view:
            self.add_item(BackButton(self.permissions_view.parent_view, row=4))
        else:
            self.add_item(BackButton(self.permissions_view, row=4))
    
    async def build_embed(self) -> discord.Embed:
        """Constrói embed com permissões atuais do comando."""
        command = self.bot.get_command(self.command_name)
        if not command:
            return discord.Embed(title="❌ Comando não encontrado", color=discord.Color.red())
        
        role_ids = await self.db.get_command_permissions(self.guild.id, self.command_name)
        
        embed = discord.Embed(
            title=f"⚙️ Permissões do Comando: !{self.command_name}",
            description=command.description or command.brief or "Sem descrição",
            color=discord.Color.blue()
        )
        
        if not role_ids or role_ids.strip() == "0" or not role_ids.strip():
            embed.add_field(
                name="📋 Permissões Atuais",
                value="Apenas administradores",
                inline=False
            )
        else:
            role_ids_list = [rid.strip() for rid in role_ids.split(",") if rid.strip()]
            roles_mentions = []
            for rid in role_ids_list:
                role = self.guild.get_role(int(rid))
                if role:
                    roles_mentions.append(role.mention)
                else:
                    roles_mentions.append(f"`{rid}` (não encontrado)")
            
            embed.add_field(
                name="📋 Permissões Atuais",
                value="\n".join(roles_mentions) if roles_mentions else "Nenhum cargo configurado",
                inline=False
            )
        
        embed.add_field(
            name="💡 Como usar",
            value="Selecione os cargos abaixo para permitir acesso ao comando.\n"
                  "Deixe vazio para apenas administradores.",
            inline=False
        )
        
        return embed
    
    async def on_role_select(self, interaction: discord.Interaction):
        """Atualiza permissões do comando com os cargos selecionados."""
        await interaction.response.defer(ephemeral=True)
        
        selected_roles = [role.id for role in self.role_select.values]
        
        if not selected_roles:
            # Apenas administradores
            await self.db.set_command_permissions(self.guild.id, self.command_name, "0")
            LOGGER.info(f"Permissões do comando '{self.command_name}' atualizadas para guild {self.guild.id}: Apenas administradores")
            await interaction.followup.send("✅ Permissões atualizadas: Apenas administradores", ephemeral=True)
        else:
            role_ids_str = ",".join(str(rid) for rid in selected_roles)
            await self.db.set_command_permissions(self.guild.id, self.command_name, role_ids_str)
            LOGGER.info(f"Permissões do comando '{self.command_name}' atualizadas para guild {self.guild.id}: {len(selected_roles)} cargo(s) - {role_ids_str}")
            await interaction.followup.send(f"✅ Permissões atualizadas: {len(selected_roles)} cargo(s)", ephemeral=True)
        
        # Atualiza embed
        embed = await self.build_embed()
        await interaction.edit_original_response(embed=embed, view=self)
    
    async def create_role(self, interaction: discord.Interaction):
        """Abre modal para criar cargo."""
        async def on_success(inter: discord.Interaction, role: discord.Role):
            # Adiciona automaticamente às permissões do comando
            role_ids = await self.db.get_command_permissions(self.guild.id, self.command_name)
            if not role_ids or role_ids.strip() == "0" or not role_ids.strip():
                role_ids_list = [role.id]
            else:
                role_ids_list = [int(rid.strip()) for rid in role_ids.split(",") if rid.strip()]
                if role.id not in role_ids_list:
                    role_ids_list.append(role.id)
            
            role_ids_str = ",".join(str(rid) for rid in role_ids_list)
            await self.db.set_command_permissions(self.guild.id, self.command_name, role_ids_str)
            LOGGER.info(f"Cargo '{role.name}' criado e adicionado às permissões do comando '{self.command_name}' no guild {self.guild.id}")
            # Atualiza embed
            embed = await self.build_embed()
            await inter.edit_original_response(embed=embed, view=self)
        
        modal = CreateRoleModal(guild=self.guild, on_success=on_success)
        await interaction.response.send_modal(modal)


class PermissionsView(discord.ui.View):
    """View principal para configurar permissões de comandos."""
    
    def __init__(self, bot: commands.Bot, db: Database, guild: discord.Guild, parent_view=None):
        super().__init__(timeout=300)
        self.bot = bot
        self.db = db
        self.guild = guild
        self.parent_view = parent_view
        
        # Adiciona botão voltar se parent_view existir
        if self.parent_view:
            self.add_item(BackButton(self.parent_view))
    
    async def build_embed(self) -> discord.Embed:
        """Constrói embed com resumo de permissões."""
        all_permissions = await self.db.list_command_permissions(self.guild.id)
        
        embed = discord.Embed(
            title="⚙️ Configuração de Permissões de Comandos",
            description="Gerencie quais cargos podem usar cada comando do bot.",
            color=discord.Color.blue()
        )
        
        if not all_permissions:
            embed.add_field(
                name="📋 Permissões Configuradas",
                value="Nenhuma permissão configurada.\nTodos os comandos estão disponíveis apenas para administradores.",
                inline=False
            )
        else:
            perms_text = []
            for perm in all_permissions[:10]:  # Limite de 10
                command_name = perm["command_name"]
                role_ids = perm["role_ids"].strip()
                
                if not role_ids or role_ids == "0":
                    perms_text.append(f"`!{command_name}`: Apenas administradores")
                else:
                    role_ids_list = [rid.strip() for rid in role_ids.split(",") if rid.strip()]
                    roles_mentions = []
                    for rid in role_ids_list[:3]:  # Limite de 3 menções
                        role = self.guild.get_role(int(rid))
                        if role:
                            roles_mentions.append(role.mention)
                    if len(role_ids_list) > 3:
                        roles_mentions.append(f"+ {len(role_ids_list) - 3} outro(s)")
                    
                    perms_text.append(f"`!{command_name}`: {', '.join(roles_mentions) if roles_mentions else 'Nenhum cargo'}")
            
            if len(all_permissions) > 10:
                perms_text.append(f"\n*+ {len(all_permissions) - 10} comando(s) adicional(is)*")
            
            embed.add_field(
                name="📋 Permissões Configuradas",
                value="\n".join(perms_text) if perms_text else "Nenhuma",
                inline=False
            )
        
        embed.set_footer(text="Use o botão abaixo para configurar um comando")
        
        return embed
    
    @discord.ui.button(label="Configurar Comando", style=discord.ButtonStyle.primary, row=0)
    async def configure_command(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre view para selecionar comando."""
        view = CommandSelectView(self.bot, self.db, self.guild, self)
        embed = discord.Embed(
            title="⚙️ Selecione um Comando",
            description="Escolha o comando que deseja configurar as permissões.",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=view)

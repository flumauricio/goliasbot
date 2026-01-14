import asyncio
import json
import logging
from typing import Optional, Dict, Callable, Any, List, Tuple

import discord
from discord.ext import commands

from config_manager import ConfigManager
from db import Database
from .voice_config import VoiceSetupView
from .action_config import ActionSetupView
from .ticket_command import TicketSetupView
from .registration_config import RegistrationConfigView
from .permissions_config import PermissionsView
from .ui_commons import BackButton, CreateChannelModal, build_standard_config_embed, check_bot_permissions, _setup_secure_channel_permissions

LOGGER = logging.getLogger(__name__)

# Usa o set global do bot para prevenir execução duplicada


class NavalSetupView(discord.ui.View):
    """View para configurar o sistema de Batalha Naval."""
    
    def __init__(self, bot: commands.Bot, db: Database, guild: discord.Guild, parent_view=None):
        super().__init__(timeout=300)
        self.bot = bot
        self.db = db
        self.guild = guild
        self.parent_view = parent_view
        
        # Adiciona botão voltar se parent_view existir
        if self.parent_view:
            self.add_item(BackButton(self.parent_view))
        
        # ChannelSelect para Canal de Batalha Naval
        self.naval_channel_select = discord.ui.ChannelSelect(
            placeholder="Selecione o canal para partidas de Batalha Naval...",
            channel_types=[discord.ChannelType.text],
            min_values=0,
            max_values=1,
            row=0
        )
        self.naval_channel_select.callback = self.on_naval_channel_select
        self.add_item(self.naval_channel_select)
        
        # Botão Criar Novo Canal (linha 3 conforme padrão)
        self.create_channel_btn = discord.ui.Button(
            label="➕ Criar Novo Canal",
            style=discord.ButtonStyle.success,
            row=3
        )
        self.create_channel_btn.callback = self.create_naval_channel
        self.add_item(self.create_channel_btn)
    
    async def build_embed(self) -> discord.Embed:
        """Constrói a embed com as configurações atuais."""
        settings = await self.db.get_settings(self.guild.id)
        
        # Canal de Batalha Naval
        channel_naval_id = settings.get("channel_naval")
        if channel_naval_id:
            channel = self.guild.get_channel(int(channel_naval_id))
            if channel:
                channel_text = f"{channel.mention} (`{channel.id}`)"
            else:
                channel_text = f"`{channel_naval_id}` (canal não encontrado)"
        else:
            channel_text = None
        
        # Usa helper padronizado
        current_config = {
            "Canal de Batalha Naval": channel_text
        }
        
        embed = await build_standard_config_embed(
            title="⚓ Configuração do Sistema de Batalha Naval",
            description="Configure o canal onde as partidas de Batalha Naval serão criadas.",
            current_config=current_config,
            guild=self.guild,
            footer_text="Selecione um canal abaixo para configurar"
        )
        
        return embed
    
    async def on_naval_channel_select(self, interaction: discord.Interaction):
        """Callback quando um canal é selecionado - salvamento automático."""
        await interaction.response.defer(ephemeral=True)
        
        selected_channels = interaction.data.get("values", [])
        if not selected_channels:
            await interaction.followup.send("❌ Nenhum canal selecionado.", ephemeral=True)
            return
        
        channel_id = int(selected_channels[0])
        channel = self.guild.get_channel(channel_id)
        
        if not channel:
            await interaction.followup.send("❌ Canal não encontrado.", ephemeral=True)
            return
        
        # Salvamento automático imediato
        await self.db.upsert_settings(self.guild.id, channel_naval=channel.id)
        
        # Atualiza a embed imediatamente
        embed = await self.build_embed()
        try:
            await interaction.message.edit(embed=embed, view=self)
        except discord.NotFound:
            pass
        
        # Confirmação efêmera
        await interaction.followup.send(
            f"✅ Configurado: Canal de Batalha Naval {channel.mention}",
            ephemeral=True
        )
    
    async def create_naval_channel(self, interaction: discord.Interaction):
        """Abre modal para criar canal de Batalha Naval."""
        async def on_success(inter: discord.Interaction, channel: discord.TextChannel):
            await self.db.upsert_settings(self.guild.id, channel_naval=channel.id)
            LOGGER.info(f"Canal de Batalha Naval '{channel.name}' criado e configurado no guild {self.guild.id}")
            embed = await self.build_embed()
            try:
                await inter.message.edit(embed=embed, view=self)
            except:
                pass
        
        modal = CreateChannelModal(
            guild=self.guild,
            title="Criar Canal de Batalha Naval",
            channel_name_label="Nome do Canal de Batalha Naval",
            on_success=on_success
        )
        await interaction.response.send_modal(modal)


# Configuração modular de módulos
MODULE_CONFIGS: Dict[str, Dict[str, Any]] = {
    "tickets": {
        "name": "🎫 Tickets",
        "view_class": TicketSetupView,
        "check_configured": "tickets",
    },
    "registration": {
        "name": "📝 Geral",
        "view_class": RegistrationConfigView,
        "check_configured": "registration",
    },
    "actions": {
        "name": "🎭 Ações",
        "view_class": ActionSetupView,
        "check_configured": "actions",
    },
    "voice_points": {
        "name": "⏱️ Ponto",
        "view_class": VoiceSetupView,
        "check_configured": "voice_points",
    },
    "permissions": {
        "name": "⚙️ Permissões",
        "view_class": PermissionsView,
        "check_configured": "permissions",
    },
    "naval": {
        "name": "⚓ Batalha Naval",
        "view_class": NavalSetupView,
        "check_configured": "naval",
    },
}


async def _check_tickets_configured(db: Database, guild_id: int) -> bool:
    """Verifica se o sistema de tickets está configurado."""
    settings = await db.get_ticket_settings(guild_id)
    return bool(settings.get("category_id") or settings.get("ticket_channel_id"))


async def _check_registration_configured(db: Database, guild_id: int) -> bool:
    """Verifica se o sistema de cadastro está configurado."""
    settings = await db.get_settings(guild_id)
    return bool(settings.get("channel_registration_embed") and settings.get("role_member"))


async def _check_actions_configured(db: Database, guild_id: int) -> bool:
    """Verifica se o sistema de ações está configurado."""
    action_types = await db.get_action_types(guild_id)
    return len(action_types) > 0


async def _check_voice_configured(db: Database, guild_id: int) -> bool:
    """Verifica se o sistema de pontos por voz está configurado."""
    allowed_roles = await db.get_allowed_roles(guild_id)
    monitored_channels = await db.get_monitored_channels(guild_id)
    settings = await db.get_voice_settings(guild_id)
    monitor_all = settings.get("monitor_all", 0) == 1
    return bool(allowed_roles and (monitor_all or monitored_channels))


async def _check_naval_configured(db: Database, guild_id: int) -> bool:
    """Verifica se o sistema de Batalha Naval está configurado."""
    settings = await db.get_settings(guild_id)
    return bool(settings.get("channel_naval"))


# ===== Funções Helper =====

def _generate_progress_bar(current_step: int, total_steps: int) -> str:
    """Gera barra de progresso visual com blocos coloridos."""
    completed = "🟩" * current_step
    remaining = "⬜" * (total_steps - current_step)
    return f"[{completed}{remaining}]"


async def _generate_wizard_report(guild: discord.Guild, db: Database) -> Dict[str, Any]:
    """Gera relatório completo do que foi/não foi configurado."""
    settings = await db.get_settings(guild.id)
    configured = {"channels": [], "roles": [], "modules": []}
    missing = {"channels": [], "roles": [], "modules": []}
    alerts = {"permission_issues": [], "missing_items": []}
    
    bot_member = guild.get_member(guild.me.id) if guild.me else None
    
    # Verifica canais
    channel_configs = {
        "Canal de Registro": settings.get("channel_registration_embed"),
        "Canal de Boas-vindas": settings.get("channel_welcome"),
        "Canal de Saídas": settings.get("channel_leaves"),
        "Canal de Advertências": settings.get("channel_warnings"),
        "Canal de Aprovação": settings.get("channel_approval"),
        "Canal de Registros": settings.get("channel_records"),
        "Canal de Batalha Naval": settings.get("channel_naval"),
    }
    
    for name, channel_id in channel_configs.items():
        if channel_id:
            try:
                channel = guild.get_channel(int(channel_id))
                if channel:
                    # Verifica permissões
                    perms = channel.permissions_for(bot_member) if bot_member else None
                    if perms:
                        if not perms.view_channel:
                            alerts["permission_issues"].append(f"{name}: Sem permissão 'Ver Canal'")
                        elif not perms.send_messages:
                            alerts["permission_issues"].append(f"{name}: Sem permissão 'Enviar Mensagens'")
                        else:
                            configured["channels"].append(f"{name}: {channel.mention}")
                    else:
                        configured["channels"].append(f"{name}: {channel.mention}")
                else:
                    alerts["missing_items"].append(f"{name}: Configurado mas não existe (ID: {channel_id})")
            except (ValueError, TypeError):
                alerts["missing_items"].append(f"{name}: ID inválido (ID: {channel_id})")
        else:
            missing["channels"].append(name)
    
    # Verifica cargos
    role_configs = {
        "Cargo SET": settings.get("role_set"),
        "Cargo Membro": settings.get("role_member"),
        "Cargo ADV1": settings.get("role_adv1"),
        "Cargo ADV2": settings.get("role_adv2"),
    }
    
    for name, role_id in role_configs.items():
        if role_id:
            try:
                role = guild.get_role(int(role_id))
                if role:
                    configured["roles"].append(f"{name}: {role.mention}")
                else:
                    alerts["missing_items"].append(f"{name}: Configurado mas não existe (ID: {role_id})")
            except (ValueError, TypeError):
                alerts["missing_items"].append(f"{name}: ID inválido (ID: {role_id})")
        else:
            missing["roles"].append(name)
    
    # Verifica módulos
    module_configs = {
        "Tickets": ("ticket_settings", "category_id"),
        "Ações": ("action_settings", "action_channel_id"),
        "Ponto/Voz": ("voice_settings", "voice_category_id"),
        "Batalha Naval": ("settings", "channel_naval"),
    }
    
    for module_name, (table, key) in module_configs.items():
        try:
            if table == "settings":
                module_data = settings
            elif table == "ticket_settings":
                module_data = await db.get_ticket_settings(guild.id)
            elif table == "action_settings":
                module_data = await db.get_action_settings(guild.id)
            elif table == "voice_settings":
                module_data = await db.get_voice_settings(guild.id)
            else:
                module_data = {}
            
            if module_data and module_data.get(key):
                configured["modules"].append(f"{module_name}: Configurado")
            else:
                missing["modules"].append(module_name)
        except Exception as e:
            LOGGER.warning("Erro ao verificar módulo %s: %s", module_name, e)
            missing["modules"].append(module_name)
    
    return {
        "configured": configured,
        "missing": missing,
        "alerts": alerts,
        "total_configured": sum(len(v) for v in configured.values()),
        "total_missing": sum(len(v) for v in missing.values()),
        "total_alerts": sum(len(v) for v in alerts.values())
    }


async def _health_check_config(
    guild: discord.Guild,
    db: Database
) -> Dict[str, Any]:
    """Verifica se canais e cargos configurados ainda existem."""
    missing_items = []
    critical_missing = []
    
    # Busca todas as configurações
    settings = await db.get_settings(guild.id)
    ticket_settings = await db.get_ticket_settings(guild.id)
    action_settings = await db.get_action_settings(guild.id)
    
    # Canais críticos
    critical_channels = {
        "channel_registration_embed": "Canal de Registro",
        "channel_warnings": "Canal de Advertências",
    }
    
    # Canais não críticos
    non_critical_channels = {
        "channel_welcome": "Canal de Boas-vindas",
        "channel_leaves": "Canal de Saídas",
        "channel_approval": "Canal de Aprovação",
        "channel_records": "Canal de Registros",
        "channel_naval": "Canal de Batalha Naval",
    }
    
    # Cargos críticos
    critical_roles = {
        "role_set": "Cargo SET",
        "role_member": "Cargo Membro",
    }
    
    # Cargos não críticos
    non_critical_roles = {
        "role_adv1": "Cargo ADV1",
        "role_adv2": "Cargo ADV2",
    }
    
    # Verifica canais críticos
    for key, name in critical_channels.items():
        channel_id = settings.get(key)
        if channel_id:
            channel = guild.get_channel(int(channel_id))
            if not channel:
                item = {"type": "canal", "name": name, "id": channel_id, "key": key}
                missing_items.append(item)
                critical_missing.append(item)
    
    # Verifica canais não críticos
    for key, name in non_critical_channels.items():
        channel_id = settings.get(key)
        if channel_id:
            channel = guild.get_channel(int(channel_id))
            if not channel:
                item = {"type": "canal", "name": name, "id": channel_id, "key": key}
                missing_items.append(item)
    
    # Verifica cargos críticos
    for key, name in critical_roles.items():
        role_id = settings.get(key)
        if role_id:
            role = guild.get_role(int(role_id))
            if not role:
                item = {"type": "cargo", "name": name, "id": role_id, "key": key}
                missing_items.append(item)
                critical_missing.append(item)
    
    # Verifica cargos não críticos
    for key, name in non_critical_roles.items():
        role_id = settings.get(key)
        if role_id:
            role = guild.get_role(int(role_id))
            if not role:
                item = {"type": "cargo", "name": name, "id": role_id, "key": key}
                missing_items.append(item)
    
    # Verifica configurações de tickets
    if ticket_settings.get("category_id"):
        category = guild.get_channel(int(ticket_settings["category_id"]))
        if not category:
            item = {"type": "categoria", "name": "Categoria de Tickets", "id": ticket_settings["category_id"], "key": "category_id"}
            missing_items.append(item)
    
    if ticket_settings.get("log_channel_id"):
        log_channel = guild.get_channel(int(ticket_settings["log_channel_id"]))
        if not log_channel:
            item = {"type": "canal", "name": "Canal de Logs de Tickets", "id": ticket_settings["log_channel_id"], "key": "log_channel_id"}
            missing_items.append(item)
    
    # Verifica configurações de ações
    if action_settings.get("action_channel_id"):
        action_channel = guild.get_channel(int(action_settings["action_channel_id"]))
        if not action_channel:
            item = {"type": "canal", "name": "Canal de Ações", "id": action_settings["action_channel_id"], "key": "action_channel_id"}
            missing_items.append(item)
    
    is_healthy = len(critical_missing) == 0
    
    return {
        "is_healthy": is_healthy,
        "missing_items": missing_items,
        "critical_missing": critical_missing
    }


async def _is_new_server(db: Database, guild_id: int) -> bool:
    """Verifica se o servidor é novo (sem configuração)."""
    settings = await db.get_settings(guild_id)
    has_registration = bool(settings.get("channel_registration_embed"))
    has_member_role = bool(settings.get("role_member"))
    
    # Verifica se algum módulo está configurado
    has_tickets = await _check_tickets_configured(db, guild_id)
    has_actions = await _check_actions_configured(db, guild_id)
    has_voice = await _check_voice_configured(db, guild_id)
    has_naval = await _check_naval_configured(db, guild_id)
    
    has_any_module = has_tickets or has_actions or has_voice or has_naval
    
    # Servidor é novo se não tem configuração básica E nenhum módulo
    return not (has_registration and has_member_role) and not has_any_module


async def _create_backup_snapshot(guild_id: int, db: Database) -> Dict[str, Any]:
    """Cria snapshot completo de todas as configurações."""
    snapshot = {}
    
    # Configurações básicas
    snapshot["settings"] = await db.get_settings(guild_id)
    
    # Configurações de tickets
    snapshot["ticket_settings"] = await db.get_ticket_settings(guild_id)
    
    # Configurações de ações
    snapshot["action_settings"] = await db.get_action_settings(guild_id)
    
    # Configurações de voz
    snapshot["voice_settings"] = await db.get_voice_settings(guild_id)
    
    # Permissões de comandos
    snapshot["command_permissions"] = list(await db.list_command_permissions(guild_id))
    
    # Tipos de ações
    snapshot["action_types"] = list(await db.get_action_types(guild_id))
    
    # Tópicos de tickets
    snapshot["ticket_topics"] = list(await db.get_ticket_topics(guild_id))
    
    return snapshot


class MainDashboardView(discord.ui.View):
    """View principal do Dashboard Central."""
    
    def __init__(self, bot: commands.Bot, db: Database, config: ConfigManager, guild: discord.Guild):
        super().__init__(timeout=300)
        self.bot = bot
        self.db = db
        self.config = config
        self.guild = guild
        self.health_check_result = None
    
    async def _add_dynamic_buttons(self):
        """Adiciona botões dinamicamente baseado no estado."""
        # Verifica progresso do wizard
        wizard_progress = None
        try:
            wizard_progress = await self.db.get_wizard_progress(self.guild.id)
        except:
            pass
        
        if wizard_progress:
            continue_btn = discord.ui.Button(
                label="🔄 Continuar de onde parei",
                style=discord.ButtonStyle.primary,
                row=0
            )
            continue_btn.callback = self.continue_wizard
            self.add_item(continue_btn)
        
        wizard_btn = discord.ui.Button(
            label="🧙 Wizard de Configuração",
            style=discord.ButtonStyle.success,
            row=0
        )
        wizard_btn.callback = self.start_wizard
        self.add_item(wizard_btn)
        
        backup_btn = discord.ui.Button(
            label="💾 Criar Backup",
            style=discord.ButtonStyle.secondary,
            row=0
        )
        backup_btn.callback = self.create_backup
        self.add_item(backup_btn)
        
        # Verifica se há problemas ou backups para mostrar botão Restaurar
        try:
            health = await _health_check_config(self.guild, self.db)
            backups = await self.db.list_backups(self.guild.id, limit=1)
            if not health["is_healthy"] or len(backups) > 0:
                restore_btn = discord.ui.Button(
                    label="🔄 Restaurar",
                    style=discord.ButtonStyle.danger,
                    row=0
                )
                restore_btn.callback = self.open_restore
                self.add_item(restore_btn)
        except:
            pass
    
    def get_module_status_emoji(self, module_name: str, is_active: bool, is_configured: bool) -> str:
        """Retorna emoji de status do módulo."""
        if not is_active:
            return "⚪"
        return "✅" if is_configured else "❌"
    
    async def build_embed(self) -> discord.Embed:
        """Constrói a embed de resumo do dashboard."""
        # Executa health check silenciosamente
        self.health_check_result = await _health_check_config(self.guild, self.db)
        
        # Verifica se há progresso do wizard
        wizard_progress = await self.db.get_wizard_progress(self.guild.id)
        has_wizard_progress = wizard_progress is not None
        
        # Verifica se é servidor novo
        is_new = await _is_new_server(self.db, self.guild.id)
        
        # Verifica se há backups
        backups = await self.db.list_backups(self.guild.id, limit=1)
        has_backups = len(backups) > 0
        
        # Define cor da embed baseado no health check
        if not self.health_check_result["is_healthy"]:
            color = discord.Color.red()
        elif is_new:
            color = discord.Color.orange()
        else:
            color = discord.Color.blue()
        
        embed = discord.Embed(
            title="⚙️ Dashboard Central - Configuração do Bot",
            description="Gerencie todos os módulos do bot a partir deste painel central.",
            color=color
        )
        
        # Alerta de configurações corrompidas
        if not self.health_check_result["is_healthy"]:
            critical_items = self.health_check_result["critical_missing"]
            missing_text = "\n".join([f"• {item['name']} (ID: {item['id']})" for item in critical_items[:5]])
            if len(critical_items) > 5:
                missing_text += f"\n• + {len(critical_items) - 5} item(ns) adicional(is)"
            
            embed.add_field(
                name="⚠️ **ALERTA: Configurações Corrompidas Detectadas!**",
                value=f"Os seguintes itens críticos não foram encontrados:\n{missing_text}\n\nUse o botão **🔄 Restaurar** para corrigir automaticamente.",
                inline=False
            )
        
        # Sugestão de wizard para servidor novo
        if is_new and not has_wizard_progress:
            embed.add_field(
                name="🧙 Servidor Novo Detectado",
                value="Este servidor ainda não está configurado. Use o **Wizard de Configuração** para configurar tudo rapidamente!",
                inline=False
            )
        
        # Busca status de todos os módulos
        all_modules_status = await self.db.get_all_modules_status(self.guild.id)
        
        # Constrói campos para cada módulo
        modules_text = []
        for module_name, module_config in MODULE_CONFIGS.items():
            is_active = all_modules_status.get(module_name, True)  # Padrão: ativo
            check_func_name = module_config["check_configured"]
            if check_func_name == "tickets":
                is_configured = await _check_tickets_configured(self.db, self.guild.id)
            elif check_func_name == "registration":
                is_configured = await _check_registration_configured(self.db, self.guild.id)
            elif check_func_name == "actions":
                is_configured = await _check_actions_configured(self.db, self.guild.id)
            elif check_func_name == "voice_points":
                is_configured = await _check_voice_configured(self.db, self.guild.id)
            elif check_func_name == "naval":
                is_configured = await _check_naval_configured(self.db, self.guild.id)
            else:  # permissions
                is_configured = True
            emoji = self.get_module_status_emoji(module_name, is_active, is_configured)
            
            status_text = "Configurado e Ativo" if (is_active and is_configured) else \
                         "Pendente de Configuração" if (is_active and not is_configured) else \
                         "Desativado"
            
            modules_text.append(f"{emoji} {module_config['name']}: {status_text}")
        
        embed.add_field(
            name="📊 Status dos Módulos",
            value="\n".join(modules_text),
            inline=False
        )
        
        # Informações de backup
        if has_backups:
            latest_backup = backups[0]
            backup_date = latest_backup.get("created_at", "Desconhecido")
            embed.add_field(
                name="💾 Backup Disponível",
                value=f"Último backup: {backup_date}",
                inline=True
            )
        
        embed.set_footer(text="Use os botões abaixo para navegar entre os módulos")
        
        return embed
    
    
    async def start_wizard(self, interaction: discord.Interaction):
        """Inicia o wizard de configuração."""
        view = WizardView(self.bot, self.db, self.config, self.guild, parent_view=self)
        embed = await view.build_embed()
        await view._update_view_buttons()
        await interaction.response.edit_message(embed=embed, view=view)
    
    async def continue_wizard(self, interaction: discord.Interaction):
        """Continua o wizard de onde parou."""
        wizard_progress = await self.db.get_wizard_progress(self.guild.id)
        if wizard_progress:
            view = WizardView(self.bot, self.db, self.config, self.guild, parent_view=self)
            await view.load_progress()
            embed = await view.build_embed()
            await view._update_view_buttons()
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            await interaction.response.send_message("❌ Nenhum progresso salvo encontrado.", ephemeral=True)
    
    async def create_backup(self, interaction: discord.Interaction):
        """Cria backup das configurações."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            snapshot = await _create_backup_snapshot(self.guild.id, self.db)
            backup_id = await self.db.save_backup(self.guild.id, snapshot)
            
            await interaction.followup.send(
                f"✅ Backup criado com sucesso! (ID: {backup_id})\n"
                f"📦 {len(snapshot)} configurações salvas.",
                ephemeral=True
            )
            
            # Reconstroi view completamente para evitar duplicação
            embed = await self.build_embed()
            # Limpa e readiciona botões dinâmicos
            await self._add_dynamic_buttons()
            await interaction.message.edit(embed=embed, view=self)
        except Exception as e:
            LOGGER.error("Erro ao criar backup: %s", e, exc_info=True)
            await interaction.followup.send(
                "❌ Erro ao criar backup. Tente novamente.",
                ephemeral=True
            )
    
    async def open_restore(self, interaction: discord.Interaction):
        """Abre interface de restauração."""
        view = RestoreView(self.bot, self.db, self.guild, parent_view=self)
        embed = await view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="⚙️ Configurar Tickets", style=discord.ButtonStyle.primary, row=1)
    async def open_tickets(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre configuração de tickets."""
        if not interaction.guild:
            await interaction.response.send_message("❌ Use este comando em um servidor.", ephemeral=True)
            return
        
        view = TicketSetupView(self.bot, self.db, interaction.guild, parent_view=self)
        await view.load_existing_settings()
        embed = await view.update_embed()
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="⚙️ Configurar Cadastro", style=discord.ButtonStyle.primary, row=1)
    async def open_registration(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre configuração de cadastro."""
        if not interaction.guild:
            await interaction.response.send_message("❌ Use este comando em um servidor.", ephemeral=True)
            return
        
        view = RegistrationConfigView(self.bot, self.db, self.config, interaction.guild.id, parent_view=self)
        embed = await view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="⚙️ Configurar Ações", style=discord.ButtonStyle.primary, row=1)
    async def open_actions(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre configuração de ações."""
        if not interaction.guild:
            await interaction.response.send_message("❌ Use este comando em um servidor.", ephemeral=True)
            return
        
        view = ActionSetupView(self.bot, self.db, interaction.guild, parent_view=self)
        await view._update_select_options()
        embed = await view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="⚙️ Configurar Ponto", style=discord.ButtonStyle.primary, row=2)
    async def open_voice(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre configuração de pontos por voz."""
        if not interaction.guild:
            await interaction.response.send_message("❌ Use este comando em um servidor.", ephemeral=True)
            return
        
        view = VoiceSetupView(self.bot, self.db, interaction.guild.id, parent_view=self)
        embed = await view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="⚙️ Configurar Permissões", style=discord.ButtonStyle.primary, row=2)
    async def open_permissions(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre configuração de permissões."""
        if not interaction.guild:
            await interaction.response.send_message("❌ Use este comando em um servidor.", ephemeral=True)
            return
        
        view = PermissionsView(self.bot, self.db, interaction.guild, parent_view=self)
        embed = await view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="⚙️ Configurar Naval", style=discord.ButtonStyle.primary, row=2)
    async def open_naval(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre configuração de Batalha Naval."""
        if not interaction.guild:
            await interaction.response.send_message("❌ Use este comando em um servidor.", ephemeral=True)
            return
        
        view = NavalSetupView(self.bot, self.db, interaction.guild, parent_view=self)
        embed = await view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)


# ===== Wizard Views =====

class WizardView(discord.ui.View):
    """View principal do Wizard de Configuração."""
    
    # Ordem estrita das etapas
    STEP_ORDER = [
        "WELCOME",
        "BASIC_CONFIG", 
        "MODULE_SELECTION",
        "MODULE_CONFIG",
        "PERMISSIONS",
        "SUMMARY"
    ]
    
    WELCOME = "WELCOME"
    BASIC_CONFIG = "BASIC_CONFIG"
    MODULE_SELECTION = "MODULE_SELECTION"
    MODULE_CONFIG = "MODULE_CONFIG"
    PERMISSIONS = "PERMISSIONS"
    SUMMARY = "SUMMARY"
    
    TOTAL_STEPS = len(STEP_ORDER) - 1  # Exclui SUMMARY da contagem
    
    def __init__(self, bot: commands.Bot, db: Database, config: ConfigManager, guild: discord.Guild, parent_view=None):
        super().__init__(timeout=None)  # Views persistentes
        self.bot = bot
        self.db = db
        self.config = config
        self.guild = guild
        self.parent_view = parent_view
        self.current_step = self.WELCOME
        self.selected_modules = []
        self.config_data = {}
    
    async def load_progress(self):
        """Carrega progresso salvo do banco."""
        progress = await self.db.get_wizard_progress(self.guild.id)
        if progress:
            self.current_step = progress.get("current_step", self.WELCOME)
            selected_modules_str = progress.get("selected_modules")
            if selected_modules_str:
                self.selected_modules = json.loads(selected_modules_str)
            config_data_str = progress.get("config_data")
            if config_data_str:
                self.config_data = json.loads(config_data_str)
    
    async def save_progress(self):
        """Salva progresso atual no banco."""
        selected_modules_str = json.dumps(self.selected_modules) if self.selected_modules else None
        config_data_str = json.dumps(self.config_data) if self.config_data else None
        await self.db.save_wizard_progress(
            self.guild.id,
            self.current_step,
            selected_modules_str,
            config_data_str
        )
    
    def get_step_number(self) -> int:
        """Retorna número da etapa atual usando STEP_ORDER (exclui SUMMARY da contagem)."""
        try:
            index = self.STEP_ORDER.index(self.current_step)
            # Se for SUMMARY, retorna TOTAL_STEPS (última etapa contada, que é PERMISSIONS)
            if self.current_step == self.SUMMARY:
                return self.TOTAL_STEPS
            # PERMISSIONS é a última etapa contada (índice 4 = etapa 4/5)
            # Para outras etapas, retorna índice + 1
            # Mas se for PERMISSIONS (índice 4), retorna 4, não 5
            if self.current_step == self.PERMISSIONS:
                return 4
            # Para outras etapas (WELCOME, BASIC_CONFIG, MODULE_SELECTION, MODULE_CONFIG), retorna índice + 1
            return index + 1
        except ValueError:
            return 1
    
    def get_next_step(self) -> Optional[str]:
        """Retorna próxima etapa ou None se for a última."""
        try:
            current_index = self.STEP_ORDER.index(self.current_step)
            if current_index < len(self.STEP_ORDER) - 1:
                return self.STEP_ORDER[current_index + 1]
        except ValueError:
            pass
        return None
    
    def get_previous_step(self) -> Optional[str]:
        """Retorna etapa anterior ou None se for a primeira."""
        try:
            current_index = self.STEP_ORDER.index(self.current_step)
            if current_index > 0:
                return self.STEP_ORDER[current_index - 1]
        except ValueError:
            pass
        return None
    
    async def build_embed(self) -> discord.Embed:
        """Constrói embed da etapa atual."""
        step_num = self.get_step_number()
        progress_bar = _generate_progress_bar(step_num, self.TOTAL_STEPS)
        
        if self.current_step == self.WELCOME:
            embed = discord.Embed(
                title="🧙 Wizard de Configuração",
                description=f"Bem-vindo ao assistente de configuração do bot!\n\n{progress_bar}\n\n**Etapa {step_num}/{self.TOTAL_STEPS}**: Boas-vindas",
                color=discord.Color.blue()
            )
            embed.add_field(
                name="📋 O que este wizard faz?",
                value="Este wizard irá guiá-lo através da configuração completa do bot:\n"
                      "1. Configuração básica (canais e cargos essenciais)\n"
                      "2. Seleção de módulos opcionais\n"
                      "3. Configuração de cada módulo escolhido\n"
                      "4. Permissões (opcional)\n"
                      "5. Resumo final",
                inline=False
            )
            embed.add_field(
                name="⏱️ Tempo estimado",
                value="5-10 minutos",
                inline=True
            )
            embed.add_field(
                name="💾 Progresso salvo",
                value="Seu progresso é salvo automaticamente. Você pode continuar de onde parou a qualquer momento!",
                inline=True
            )
        
        elif self.current_step == self.BASIC_CONFIG:
            embed = discord.Embed(
                title="⚙️ Configuração Básica",
                description=f"{progress_bar}\n\n**Etapa {step_num}/{self.TOTAL_STEPS}**: Configure os canais e cargos essenciais",
                color=discord.Color.blue()
            )
            embed.add_field(
                name="📝 O que configurar",
                value="• Canal de Registro\n• Canal de Boas-vindas\n• Canal de Saídas\n• Canal de Advertências\n• Cargo SET\n• Cargo Membro\n• Cargo ADV1\n• Cargo ADV2",
                inline=False
            )
        
        elif self.current_step == self.MODULE_SELECTION:
            embed = discord.Embed(
                title="🎯 Seleção de Módulos",
                description=f"{progress_bar}\n\n**Etapa {step_num}/{self.TOTAL_STEPS}**: Escolha quais módulos deseja habilitar",
                color=discord.Color.blue()
            )
            embed.add_field(
                name="📦 Módulos disponíveis",
                value="• 🎫 Tickets - Sistema de tickets de suporte\n"
                      "• 🎭 Ações - Sistema de ações FiveM\n"
                      "• ⏱️ Ponto - Monitoramento de tempo em voz\n"
                      "• ⚓ Batalha Naval - Jogo de batalha naval",
                inline=False
            )
        
        elif self.current_step == self.MODULE_CONFIG:
            embed = discord.Embed(
                title="⚙️ Configuração de Módulos",
                description=f"{progress_bar}\n\n**Etapa {step_num}/{self.TOTAL_STEPS}**: Configure cada módulo selecionado",
                color=discord.Color.blue()
            )
            if self.selected_modules:
                modules_text = "\n".join([f"• {m}" for m in self.selected_modules])
                embed.add_field(
                    name="✅ Módulos selecionados",
                    value=modules_text,
                    inline=False
                )
            else:
                embed.add_field(
                    name="ℹ️ Nenhum módulo selecionado",
                    value="Você pode pular esta etapa.",
                    inline=False
                )
        
        elif self.current_step == self.PERMISSIONS:
            embed = discord.Embed(
                title="🔐 Permissões",
                description=f"{progress_bar}\n\n**Etapa {step_num}/{self.TOTAL_STEPS}**: Configure permissões de comandos (opcional)",
                color=discord.Color.blue()
            )
            embed.add_field(
                name="ℹ️ Esta etapa é opcional",
                value="Você pode configurar permissões agora ou depois usando o dashboard principal.",
                inline=False
            )
            embed.add_field(
                name="⚙️ Configurar Permissões",
                value="Use o botão abaixo para abrir a interface de configuração de permissões.",
                inline=False
            )
        
        else:  # SUMMARY
            embed = discord.Embed(
                title="✅ Configuração Concluída!",
                description=f"{progress_bar}\n\n**Etapa {step_num}/{self.TOTAL_STEPS}**: Resumo da configuração",
                color=discord.Color.green()
            )
            embed.add_field(
                name="🎉 Parabéns!",
                value="Sua configuração foi concluída com sucesso!",
                inline=False
            )
        
        return embed
    
    async def _update_view_buttons(self):
        """Atualiza visibilidade dos botões baseado na etapa atual."""
        # Remove todos os botões dinâmicos primeiro
        items_to_remove = []
        for item in self.children:
            if hasattr(item, 'custom_id') and item.custom_id in ["wizard_permissions", "wizard_next", "wizard_previous", "wizard_finish"]:
                items_to_remove.append(item)
        
        for item in items_to_remove:
            self.remove_item(item)
        
        # Adiciona botão de permissões apenas na etapa PERMISSIONS
        if self.current_step == self.PERMISSIONS:
            permissions_btn = discord.ui.Button(
                label="⚙️ Configurar Permissões",
                style=discord.ButtonStyle.primary,
                row=3,
                custom_id="wizard_permissions"
            )
            permissions_btn.callback = self.open_permissions
            self.add_item(permissions_btn)
        
        # Adiciona botão 'Próximo' apenas se não for SUMMARY
        # Na etapa PERMISSIONS, também adiciona o botão 'Próximo' para ir para SUMMARY
        if self.current_step != self.SUMMARY:
            next_btn = discord.ui.Button(
                label="⏭️ Próximo",
                style=discord.ButtonStyle.primary,
                row=4,
                custom_id="wizard_next"
            )
            next_btn.callback = self.next_step
            self.add_item(next_btn)
        
        # Adiciona botão 'Anterior' se não for WELCOME (inclui PERMISSIONS)
        if self.current_step != self.WELCOME:
            previous_btn = discord.ui.Button(
                label="⬅️ Anterior",
                style=discord.ButtonStyle.secondary,
                row=4,
                custom_id="wizard_previous"
            )
            previous_btn.callback = self.previous_step
            self.add_item(previous_btn)
        
        # Adiciona botão 'Concluir' apenas na etapa SUMMARY
        if self.current_step == self.SUMMARY:
            finish_btn = discord.ui.Button(
                label="✅ Concluir",
                style=discord.ButtonStyle.success,
                row=4,
                custom_id="wizard_finish"
            )
            finish_btn.callback = self.finish
            self.add_item(finish_btn)
    
    async def open_permissions(self, interaction: discord.Interaction):
        """Abre interface de configuração de permissões."""
        if self.current_step != self.PERMISSIONS:
            await interaction.response.send_message("❌ Esta ação só está disponível na etapa de Permissões.", ephemeral=True)
            return
        
        view = PermissionsView(self.bot, self.db, self.guild, parent_view=self)
        embed = await view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)
    
    async def next_step(self, interaction: discord.Interaction):
        """Avança para próxima etapa usando STEP_ORDER."""
        next_step_name = self.get_next_step()
        if not next_step_name or next_step_name == self.SUMMARY:
            # Se próxima etapa é SUMMARY ou não há próxima, vai para SUMMARY
            self.current_step = self.SUMMARY
            await self.save_progress()
            embed = await self.build_embed()
            await self._update_view_buttons()
            await interaction.response.edit_message(embed=embed, view=self)
            return
        
        # Atualiza current_step antes de navegar
        self.current_step = next_step_name
        
        if self.current_step == self.BASIC_CONFIG:
            # Abre view de configuração básica
            basic_view = WizardBasicConfigView(self.bot, self.db, self.config, self.guild, self)
            embed = await basic_view.build_embed()
            await interaction.response.edit_message(embed=embed, view=basic_view)
            await self.save_progress()
            return
        elif self.current_step == self.MODULE_SELECTION:
            # Abre view de seleção de módulos
            module_selection_view = WizardModuleSelectionView(self.bot, self.db, self.config, self.guild, self)
            embed = await module_selection_view.build_embed()
            await interaction.response.edit_message(embed=embed, view=module_selection_view)
            await self.save_progress()
            return
        elif self.current_step == self.MODULE_CONFIG:
            # Abre view de configuração de módulos
            if self.selected_modules:
                module_config_view = WizardModuleConfigView(self.bot, self.db, self.config, self.guild, self, self.selected_modules)
                embed = await module_config_view.build_embed()
                await interaction.response.edit_message(embed=embed, view=module_config_view)
                await self.save_progress()
                return
            else:
                # Se não há módulos selecionados, pula para permissões
                self.current_step = self.PERMISSIONS
                embed = await self.build_embed()
                await self._update_view_buttons()
                await interaction.response.edit_message(embed=embed, view=self)
                await self.save_progress()
                return
        elif self.current_step == self.PERMISSIONS:
            # Permanece na view de permissões (já tem botão para abrir)
            embed = await self.build_embed()
            await self._update_view_buttons()
            await interaction.response.edit_message(embed=embed, view=self)
            await self.save_progress()
            return
        
        # Para SUMMARY, apenas atualiza embed
        await self.save_progress()
        embed = await self.build_embed()
        await self._update_view_buttons()
        await interaction.response.edit_message(embed=embed, view=self)
    
    async def previous_step(self, interaction: discord.Interaction):
        """Volta para etapa anterior usando STEP_ORDER."""
        previous_step_name = self.get_previous_step()
        if not previous_step_name:
            await interaction.response.send_message("❌ Já está na primeira etapa.", ephemeral=True)
            return
        
        # Atualiza current_step antes de navegar
        self.current_step = previous_step_name
        
        if self.current_step == self.BASIC_CONFIG:
            basic_view = WizardBasicConfigView(self.bot, self.db, self.config, self.guild, self)
            embed = await basic_view.build_embed()
            await interaction.response.edit_message(embed=embed, view=basic_view)
            await self.save_progress()
            return
        elif self.current_step == self.MODULE_SELECTION:
            module_selection_view = WizardModuleSelectionView(self.bot, self.db, self.config, self.guild, self)
            embed = await module_selection_view.build_embed()
            await interaction.response.edit_message(embed=embed, view=module_selection_view)
            await self.save_progress()
            return
        elif self.current_step == self.MODULE_CONFIG:
            if self.selected_modules:
                module_config_view = WizardModuleConfigView(self.bot, self.db, self.config, self.guild, self, self.selected_modules)
                embed = await module_config_view.build_embed()
                await interaction.response.edit_message(embed=embed, view=module_config_view)
            else:
                # Se não há módulos, volta para seleção
                self.current_step = self.MODULE_SELECTION
                module_selection_view = WizardModuleSelectionView(self.bot, self.db, self.config, self.guild, self)
                embed = await module_selection_view.build_embed()
                await interaction.response.edit_message(embed=embed, view=module_selection_view)
            await self.save_progress()
            return
        
        # Para WELCOME, apenas atualiza embed
        await self.save_progress()
        embed = await self.build_embed()
        await self._update_view_buttons()
        await interaction.response.edit_message(embed=embed, view=self)
    
    async def finish(self, interaction: discord.Interaction):
        """Conclui o wizard e exibe relatório."""
        if self.current_step != self.SUMMARY:
            await interaction.response.send_message("❌ Conclua todas as etapas primeiro.", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        # Gera relatório
        report = await _generate_wizard_report(self.guild, self.db)
        
        # Deleta mensagem original (com verificação de permissão)
        if interaction.channel.permissions_for(interaction.guild.me).manage_messages:
            try:
                await interaction.message.delete()
            except discord.NotFound:
                pass  # Mensagem já foi deletada
            except discord.Forbidden:
                LOGGER.warning("Sem permissão para deletar mensagem em %s", interaction.channel.id)
        
        # Cria embed de relatório elegante
        report_embed = discord.Embed(
            title="📊 Relatório de Configuração",
            description="Resumo completo do que foi configurado no servidor.",
            color=discord.Color.green() if report["total_missing"] == 0 and report["total_alerts"] == 0 else discord.Color.orange()
        )
        
        # Seção Configurado
        configured_text = []
        if report["configured"]["channels"]:
            configured_text.append("**📢 Canais:**\n" + "\n".join(report["configured"]["channels"][:10]))
        if report["configured"]["roles"]:
            configured_text.append("**👥 Cargos:**\n" + "\n".join(report["configured"]["roles"][:10]))
        if report["configured"]["modules"]:
            configured_text.append("**📦 Módulos:**\n" + "\n".join(report["configured"]["modules"][:10]))
        
        if configured_text:
            report_embed.add_field(
                name="✅ Configurado",
                value="\n\n".join(configured_text) or "Nenhum item configurado",
                inline=False
            )
        
        # Seção Pendente
        missing_text = []
        if report["missing"]["channels"]:
            missing_text.append("**📢 Canais:**\n" + "\n".join([f"• {c}" for c in report["missing"]["channels"][:10]]))
        if report["missing"]["roles"]:
            missing_text.append("**👥 Cargos:**\n" + "\n".join([f"• {r}" for r in report["missing"]["roles"][:10]]))
        if report["missing"]["modules"]:
            missing_text.append("**📦 Módulos:**\n" + "\n".join([f"• {m}" for m in report["missing"]["modules"][:10]]))
        
        if missing_text:
            report_embed.add_field(
                name="❌ Pendente",
                value="\n\n".join(missing_text) or "Nada pendente",
                inline=False
            )
        
        # Seção Alertas
        if report["alerts"]["permission_issues"] or report["alerts"]["missing_items"]:
            alerts_text = []
            if report["alerts"]["permission_issues"]:
                alerts_text.append("**⚠️ Problemas de Permissão:**\n" + "\n".join([f"• {a}" for a in report["alerts"]["permission_issues"][:10]]))
            if report["alerts"]["missing_items"]:
                alerts_text.append("**⚠️ Itens Não Encontrados:**\n" + "\n".join([f"• {a}" for a in report["alerts"]["missing_items"][:10]]))
            
            if alerts_text:
                report_embed.add_field(
                    name="⚠️ Alertas",
                    value="\n\n".join(alerts_text),
                    inline=False
                )
        
        # Resumo
        report_embed.add_field(
            name="📊 Resumo",
            value=f"✅ Configurado: {report['total_configured']}\n"
                  f"❌ Pendente: {report['total_missing']}\n"
                  f"⚠️ Alertas: {report['total_alerts']}",
            inline=True
        )
        
        report_embed.set_footer(text="Use !setup para configurar itens pendentes.")
        
        # Envia relatório
        await interaction.followup.send(embed=report_embed)
        
        # Limpa progresso
        await self.db.clear_wizard_progress(self.guild.id)


class WizardBasicConfigView(discord.ui.View):
    """View para configuração básica no wizard."""
    
    def __init__(self, bot: commands.Bot, db: Database, config: ConfigManager, guild: discord.Guild, wizard_view):
        super().__init__(timeout=None)  # View persistente
        self.bot = bot
        self.db = db
        self.config = config
        self.guild = guild
        self.wizard_view = wizard_view
        
        # Seletores de canais (ChannelSelect ocupa toda a linha - 5 slots)
        self.reg_channel_select = discord.ui.ChannelSelect(
            placeholder="Canal de Registro...",
            channel_types=[discord.ChannelType.text],
            min_values=0,
            max_values=1,
            row=0
        )
        self.reg_channel_select.callback = self.on_reg_channel_select
        self.add_item(self.reg_channel_select)
        
        self.welcome_channel_select = discord.ui.ChannelSelect(
            placeholder="Canal de Boas-vindas...",
            channel_types=[discord.ChannelType.text],
            min_values=0,
            max_values=1,
            row=1
        )
        self.welcome_channel_select.callback = self.on_welcome_channel_select
        self.add_item(self.welcome_channel_select)
        
        self.leaves_channel_select = discord.ui.ChannelSelect(
            placeholder="Canal de Saídas...",
            channel_types=[discord.ChannelType.text],
            min_values=0,
            max_values=1,
            row=2
        )
        self.leaves_channel_select.callback = self.on_leaves_channel_select
        self.add_item(self.leaves_channel_select)
        
        self.warnings_channel_select = discord.ui.ChannelSelect(
            placeholder="Canal de Advertências...",
            channel_types=[discord.ChannelType.text],
            min_values=0,
            max_values=1,
            row=3
        )
        self.warnings_channel_select.callback = self.on_warnings_channel_select
        self.add_item(self.warnings_channel_select)
        
        # Botão para configurar cargos (abre view separada)
        self.configure_roles_btn = discord.ui.Button(
            label="⚙️ Configurar Cargos",
            style=discord.ButtonStyle.primary,
            row=4
        )
        self.configure_roles_btn.callback = self.open_role_config
        self.add_item(self.configure_roles_btn)
    
    async def build_embed(self) -> discord.Embed:
        """Constrói embed de configuração básica."""
        # Garante que current_step está atualizado
        self.wizard_view.current_step = self.wizard_view.BASIC_CONFIG
        step_num = self.wizard_view.get_step_number()
        progress_bar = _generate_progress_bar(step_num, self.wizard_view.TOTAL_STEPS)
        
        settings = await self.db.get_settings(self.guild.id)
        
        embed = discord.Embed(
            title="⚙️ Configuração Básica",
            description=f"{progress_bar}\n\n**Etapa {step_num}/{self.wizard_view.TOTAL_STEPS}**: Configure os canais e cargos essenciais",
            color=discord.Color.blue()
        )
        
        # Status dos canais
        reg_channel = self.guild.get_channel(int(settings.get("channel_registration_embed", 0) or 0))
        welcome_channel = self.guild.get_channel(int(settings.get("channel_welcome", 0) or 0))
        leaves_channel = self.guild.get_channel(int(settings.get("channel_leaves", 0) or 0))
        warnings_channel = self.guild.get_channel(int(settings.get("channel_warnings", 0) or 0))
        
        channels_status = []
        channels_status.append(f"{'✅' if reg_channel else '❌'} Canal de Registro: {reg_channel.mention if reg_channel else 'Não configurado'}")
        channels_status.append(f"{'✅' if welcome_channel else '❌'} Canal de Boas-vindas: {welcome_channel.mention if welcome_channel else 'Não configurado'}")
        channels_status.append(f"{'✅' if leaves_channel else '❌'} Canal de Saídas: {leaves_channel.mention if leaves_channel else 'Não configurado'}")
        channels_status.append(f"{'✅' if warnings_channel else '❌'} Canal de Advertências: {warnings_channel.mention if warnings_channel else 'Não configurado'}")
        
        embed.add_field(
            name="📢 Canais",
            value="\n".join(channels_status),
            inline=False
        )
        
        # Status dos cargos
        set_role = self.guild.get_role(int(settings.get("role_set", 0) or 0))
        member_role = self.guild.get_role(int(settings.get("role_member", 0) or 0))
        adv1_role = self.guild.get_role(int(settings.get("role_adv1", 0) or 0))
        adv2_role = self.guild.get_role(int(settings.get("role_adv2", 0) or 0))
        
        roles_status = []
        roles_status.append(f"{'✅' if set_role else '❌'} Cargo SET: {set_role.mention if set_role else 'Não configurado'}")
        roles_status.append(f"{'✅' if member_role else '❌'} Cargo Membro: {member_role.mention if member_role else 'Não configurado'}")
        roles_status.append(f"{'✅' if adv1_role else '❌'} Cargo ADV1: {adv1_role.mention if adv1_role else 'Não configurado'}")
        roles_status.append(f"{'✅' if adv2_role else '❌'} Cargo ADV2: {adv2_role.mention if adv2_role else 'Não configurado'}")
        
        embed.add_field(
            name="👥 Cargos",
            value="\n".join(roles_status),
            inline=False
        )
        
        embed.set_footer(text="Use os seletores abaixo para configurar. Clique em 'Próximo' quando terminar.")
        
        return embed
    
    async def on_reg_channel_select(self, interaction: discord.Interaction):
        """Callback para seleção do canal de registro."""
        await interaction.response.defer(ephemeral=True)
        if self.reg_channel_select.values:
            channel = self.reg_channel_select.values[0]
            await self.db.upsert_settings(self.guild.id, channel_registration_embed=channel.id)
            embed = await self.build_embed()
            await interaction.followup.send(f"✅ Canal de Registro configurado: {channel.mention}", ephemeral=True)
            await interaction.message.edit(embed=embed, view=self)
    
    async def on_welcome_channel_select(self, interaction: discord.Interaction):
        """Callback para seleção do canal de boas-vindas."""
        await interaction.response.defer(ephemeral=True)
        if self.welcome_channel_select.values:
            channel = self.welcome_channel_select.values[0]
            await self.db.upsert_settings(self.guild.id, channel_welcome=channel.id)
            embed = await self.build_embed()
            await interaction.followup.send(f"✅ Canal de Boas-vindas configurado: {channel.mention}", ephemeral=True)
            await interaction.message.edit(embed=embed, view=self)
    
    async def on_leaves_channel_select(self, interaction: discord.Interaction):
        """Callback para seleção do canal de saídas."""
        await interaction.response.defer(ephemeral=True)
        if self.leaves_channel_select.values:
            channel = self.leaves_channel_select.values[0]
            await self.db.upsert_settings(self.guild.id, channel_leaves=channel.id)
            embed = await self.build_embed()
            await interaction.followup.send(f"✅ Canal de Saídas configurado: {channel.mention}", ephemeral=True)
            await interaction.message.edit(embed=embed, view=self)
    
    async def on_warnings_channel_select(self, interaction: discord.Interaction):
        """Callback para seleção do canal de advertências."""
        await interaction.response.defer(ephemeral=True)
        if self.warnings_channel_select.values:
            channel = self.warnings_channel_select.values[0]
            # Aplica permissões automáticas para canal sensível
            bot_member = self.guild.get_member(self.bot.user.id)
            staff_roles = [role for role in bot_member.roles if role.permissions.administrator] if bot_member else []
            await _setup_secure_channel_permissions(channel, staff_roles)
            await self.db.upsert_settings(self.guild.id, channel_warnings=channel.id)
            embed = await self.build_embed()
            await interaction.followup.send(f"✅ Canal de Advertências configurado: {channel.mention} (permissões aplicadas automaticamente)", ephemeral=True)
            await interaction.message.edit(embed=embed, view=self)
    
    async def open_role_config(self, interaction: discord.Interaction):
        """Abre view para configurar cargos."""
        view = WizardRoleConfigView(self.bot, self.db, self.config, self.guild, self)
        embed = await view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)
    
    async def create_reg_channel(self, interaction: discord.Interaction):
        """Cria canal de registro."""
        async def on_success(inter: discord.Interaction, channel: discord.TextChannel):
            await self.db.upsert_settings(self.guild.id, channel_registration_embed=channel.id)
            embed = await self.build_embed()
            await inter.message.edit(embed=embed, view=self)
        
        modal = CreateChannelModal(
            guild=self.guild,
            title="Criar Canal de Registro",
            channel_name_label="Nome do Canal de Registro",
            on_success=on_success
        )
        await interaction.response.send_modal(modal)
    
    async def create_warnings_channel(self, interaction: discord.Interaction):
        """Cria canal de advertências com permissões automáticas."""
        async def on_success(inter: discord.Interaction, channel: discord.TextChannel):
            # Aplica permissões automáticas
            bot_member = self.guild.get_member(self.bot.user.id)
            staff_roles = [role for role in bot_member.roles if role.permissions.administrator] if bot_member else []
            await _setup_secure_channel_permissions(channel, staff_roles)
            await self.db.upsert_settings(self.guild.id, channel_warnings=channel.id)
            embed = await self.build_embed()
            await inter.message.edit(embed=embed, view=self)
        
        modal = CreateChannelModal(
            guild=self.guild,
            title="Criar Canal de Advertências",
            channel_name_label="Nome do Canal de Advertências",
            on_success=on_success
        )
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="⏭️ Próximo", style=discord.ButtonStyle.primary, row=4)
    async def next_step(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Avança para próxima etapa."""
        self.wizard_view.current_step = self.wizard_view.MODULE_SELECTION
        await self.wizard_view.save_progress()
        module_selection_view = WizardModuleSelectionView(self.bot, self.db, self.config, self.guild, self.wizard_view)
        embed = await module_selection_view.build_embed()
        await interaction.response.edit_message(embed=embed, view=module_selection_view)
    
    @discord.ui.button(label="⬅️ Anterior", style=discord.ButtonStyle.secondary, row=4)
    async def previous_step(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Volta para etapa anterior."""
        self.wizard_view.current_step = self.wizard_view.WELCOME
        await self.wizard_view.save_progress()
        embed = await self.wizard_view.build_embed()
        await interaction.response.edit_message(embed=embed, view=self.wizard_view)


class WizardRoleConfigView(discord.ui.View):
    """View para configurar cargos no wizard."""
    
    def __init__(self, bot: commands.Bot, db: Database, config: ConfigManager, guild: discord.Guild, parent_view):
        super().__init__(timeout=None)  # View persistente
        self.bot = bot
        self.db = db
        self.config = config
        self.guild = guild
        self.parent_view = parent_view
        
        # Seletores de cargos (cada um ocupa uma linha)
        self.set_role_select = discord.ui.RoleSelect(
            placeholder="Cargo SET...",
            min_values=0,
            max_values=1,
            row=0
        )
        self.set_role_select.callback = self.on_set_role_select
        self.add_item(self.set_role_select)
        
        self.member_role_select = discord.ui.RoleSelect(
            placeholder="Cargo Membro...",
            min_values=0,
            max_values=1,
            row=1
        )
        self.member_role_select.callback = self.on_member_role_select
        self.add_item(self.member_role_select)
        
        self.adv1_role_select = discord.ui.RoleSelect(
            placeholder="Cargo ADV1...",
            min_values=0,
            max_values=1,
            row=2
        )
        self.adv1_role_select.callback = self.on_adv1_role_select
        self.add_item(self.adv1_role_select)
        
        self.adv2_role_select = discord.ui.RoleSelect(
            placeholder="Cargo ADV2...",
            min_values=0,
            max_values=1,
            row=3
        )
        self.adv2_role_select.callback = self.on_adv2_role_select
        self.add_item(self.adv2_role_select)
    
    async def build_embed(self) -> discord.Embed:
        """Constrói embed de configuração de cargos."""
        settings = await self.db.get_settings(self.guild.id)
        
        embed = discord.Embed(
            title="👥 Configuração de Cargos",
            description="Selecione os cargos essenciais do sistema.",
            color=discord.Color.blue()
        )
        
        # Status dos cargos
        set_role = self.guild.get_role(int(settings.get("role_set", 0) or 0))
        member_role = self.guild.get_role(int(settings.get("role_member", 0) or 0))
        adv1_role = self.guild.get_role(int(settings.get("role_adv1", 0) or 0))
        adv2_role = self.guild.get_role(int(settings.get("role_adv2", 0) or 0))
        
        roles_status = []
        roles_status.append(f"{'✅' if set_role else '❌'} Cargo SET: {set_role.mention if set_role else 'Não configurado'}")
        roles_status.append(f"{'✅' if member_role else '❌'} Cargo Membro: {member_role.mention if member_role else 'Não configurado'}")
        roles_status.append(f"{'✅' if adv1_role else '❌'} Cargo ADV1: {adv1_role.mention if adv1_role else 'Não configurado'}")
        roles_status.append(f"{'✅' if adv2_role else '❌'} Cargo ADV2: {adv2_role.mention if adv2_role else 'Não configurado'}")
        
        embed.add_field(
            name="👥 Cargos",
            value="\n".join(roles_status),
            inline=False
        )
        
        embed.set_footer(text="Use os seletores abaixo para configurar. Clique em 'Voltar' quando terminar.")
        
        return embed
    
    async def on_set_role_select(self, interaction: discord.Interaction):
        """Callback para seleção do cargo SET."""
        await interaction.response.defer(ephemeral=True)
        if self.set_role_select.values:
            role = self.set_role_select.values[0]
            await self.db.upsert_settings(self.guild.id, role_set=role.id)
            embed = await self.build_embed()
            await interaction.followup.send(f"✅ Cargo SET configurado: {role.mention}", ephemeral=True)
            await interaction.message.edit(embed=embed, view=self)
    
    async def on_member_role_select(self, interaction: discord.Interaction):
        """Callback para seleção do cargo Membro."""
        await interaction.response.defer(ephemeral=True)
        if self.member_role_select.values:
            role = self.member_role_select.values[0]
            await self.db.upsert_settings(self.guild.id, role_member=role.id)
            embed = await self.build_embed()
            await interaction.followup.send(f"✅ Cargo Membro configurado: {role.mention}", ephemeral=True)
            await interaction.message.edit(embed=embed, view=self)
    
    async def on_adv1_role_select(self, interaction: discord.Interaction):
        """Callback para seleção do cargo ADV1."""
        await interaction.response.defer(ephemeral=True)
        if self.adv1_role_select.values:
            role = self.adv1_role_select.values[0]
            await self.db.upsert_settings(self.guild.id, role_adv1=role.id)
            embed = await self.build_embed()
            await interaction.followup.send(f"✅ Cargo ADV1 configurado: {role.mention}", ephemeral=True)
            await interaction.message.edit(embed=embed, view=self)
    
    async def on_adv2_role_select(self, interaction: discord.Interaction):
        """Callback para seleção do cargo ADV2."""
        await interaction.response.defer(ephemeral=True)
        if self.adv2_role_select.values:
            role = self.adv2_role_select.values[0]
            await self.db.upsert_settings(self.guild.id, role_adv2=role.id)
            embed = await self.build_embed()
            await interaction.followup.send(f"✅ Cargo ADV2 configurado: {role.mention}", ephemeral=True)
            await interaction.message.edit(embed=embed, view=self)
    
    @discord.ui.button(label="⬅️ Voltar", style=discord.ButtonStyle.secondary, row=4)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Volta para configuração básica."""
        embed = await self.parent_view.build_embed()
        await interaction.response.edit_message(embed=embed, view=self.parent_view)


class WizardModuleSelectionView(discord.ui.View):
    """View para seleção de módulos no wizard."""
    
    def __init__(self, bot: commands.Bot, db: Database, config: ConfigManager, guild: discord.Guild, wizard_view):
        super().__init__(timeout=None)  # View persistente
        self.bot = bot
        self.db = db
        self.config = config
        self.guild = guild
        self.wizard_view = wizard_view
        
        # Carrega módulos selecionados do wizard
        self.selected_modules = self.wizard_view.selected_modules.copy() if self.wizard_view.selected_modules else []
        
        # Botões toggle para cada módulo
        self.tickets_toggle = discord.ui.Button(
            label="🎫 Tickets" + (" ✅" if "tickets" in self.selected_modules else ""),
            style=discord.ButtonStyle.success if "tickets" in self.selected_modules else discord.ButtonStyle.secondary,
            row=0
        )
        self.tickets_toggle.callback = lambda i: self.toggle_module(i, "tickets", self.tickets_toggle)
        self.add_item(self.tickets_toggle)
        
        self.actions_toggle = discord.ui.Button(
            label="🎭 Ações" + (" ✅" if "actions" in self.selected_modules else ""),
            style=discord.ButtonStyle.success if "actions" in self.selected_modules else discord.ButtonStyle.secondary,
            row=0
        )
        self.actions_toggle.callback = lambda i: self.toggle_module(i, "actions", self.actions_toggle)
        self.add_item(self.actions_toggle)
        
        self.voice_toggle = discord.ui.Button(
            label="⏱️ Ponto" + (" ✅" if "voice_points" in self.selected_modules else ""),
            style=discord.ButtonStyle.success if "voice_points" in self.selected_modules else discord.ButtonStyle.secondary,
            row=1
        )
        self.voice_toggle.callback = lambda i: self.toggle_module(i, "voice_points", self.voice_toggle)
        self.add_item(self.voice_toggle)
        
        self.naval_toggle = discord.ui.Button(
            label="⚓ Batalha Naval" + (" ✅" if "naval" in self.selected_modules else ""),
            style=discord.ButtonStyle.success if "naval" in self.selected_modules else discord.ButtonStyle.secondary,
            row=1
        )
        self.naval_toggle.callback = lambda i: self.toggle_module(i, "naval", self.naval_toggle)
        self.add_item(self.naval_toggle)
    
    async def toggle_module(self, interaction: discord.Interaction, module_name: str, button: discord.ui.Button):
        """Alterna estado do módulo."""
        if module_name in self.selected_modules:
            self.selected_modules.remove(module_name)
            button.label = button.label.replace(" ✅", "")
            button.style = discord.ButtonStyle.secondary
        else:
            self.selected_modules.append(module_name)
            if " ✅" not in button.label:
                button.label += " ✅"
            button.style = discord.ButtonStyle.success
        
        # Atualiza no wizard_view
        self.wizard_view.selected_modules = self.selected_modules
        await self.wizard_view.save_progress()
        
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    async def build_embed(self) -> discord.Embed:
        """Constrói embed de seleção de módulos."""
        # Garante que current_step está atualizado
        self.wizard_view.current_step = self.wizard_view.MODULE_SELECTION
        step_num = self.wizard_view.get_step_number()
        progress_bar = _generate_progress_bar(step_num, self.wizard_view.TOTAL_STEPS)
        
        embed = discord.Embed(
            title="🎯 Seleção de Módulos",
            description=f"{progress_bar}\n\n**Etapa {step_num}/{self.wizard_view.TOTAL_STEPS}**: Escolha quais módulos deseja habilitar",
            color=discord.Color.blue()
        )
        
        modules_info = {
            "tickets": "Sistema de tickets de suporte",
            "actions": "Sistema de ações FiveM",
            "voice_points": "Monitoramento de tempo em voz",
            "naval": "Jogo de batalha naval"
        }
        
        selected_text = []
        for module in self.selected_modules:
            selected_text.append(f"• {MODULE_CONFIGS.get(module, {}).get('name', module)}: {modules_info.get(module, '')}")
        
        if selected_text:
            embed.add_field(
                name="✅ Módulos Selecionados",
                value="\n".join(selected_text),
                inline=False
            )
        else:
            embed.add_field(
                name="ℹ️ Nenhum módulo selecionado",
                value="Clique nos botões abaixo para ativar/desativar módulos.",
                inline=False
            )
        
        embed.set_footer(text="Use os botões abaixo para selecionar módulos. Clique em 'Próximo' quando terminar.")
        
        return embed
    
    @discord.ui.button(label="⏭️ Próximo", style=discord.ButtonStyle.primary, row=4)
    async def next_step(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Avança para próxima etapa."""
        self.wizard_view.current_step = self.wizard_view.MODULE_CONFIG
        self.wizard_view.selected_modules = self.selected_modules
        await self.wizard_view.save_progress()
        
        if self.selected_modules:
            module_config_view = WizardModuleConfigView(self.bot, self.db, self.config, self.guild, self.wizard_view, self.selected_modules)
            embed = await module_config_view.build_embed()
            await interaction.response.edit_message(embed=embed, view=module_config_view)
        else:
            # Pula para permissões se nenhum módulo selecionado
            self.wizard_view.current_step = self.wizard_view.PERMISSIONS
            embed = await self.wizard_view.build_embed()
            await self.wizard_view._update_view_buttons()
            await interaction.response.edit_message(embed=embed, view=self.wizard_view)
    
    @discord.ui.button(label="⬅️ Anterior", style=discord.ButtonStyle.secondary, row=4)
    async def previous_step(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Volta para etapa anterior."""
        self.wizard_view.current_step = self.wizard_view.BASIC_CONFIG
        await self.wizard_view.save_progress()
        basic_view = WizardBasicConfigView(self.bot, self.db, self.config, self.guild, self.wizard_view)
        embed = await basic_view.build_embed()
        await interaction.response.edit_message(embed=embed, view=basic_view)


class WizardModuleConfigView(discord.ui.View):
    """View para configurar módulos selecionados no wizard."""
    
    def __init__(self, bot: commands.Bot, db: Database, config: ConfigManager, guild: discord.Guild, wizard_view, selected_modules: List[str]):
        super().__init__(timeout=None)  # View persistente
        self.bot = bot
        self.db = db
        self.config = config
        self.guild = guild
        self.wizard_view = wizard_view
        self.selected_modules = selected_modules
        self.current_module_index = 0
    
    def get_current_module(self) -> Optional[str]:
        """Retorna módulo atual sendo configurado."""
        if self.current_module_index < len(self.selected_modules):
            return self.selected_modules[self.current_module_index]
        return None
    
    async def build_embed(self) -> discord.Embed:
        """Constrói embed de configuração de módulos."""
        # Garante que current_step está atualizado
        self.wizard_view.current_step = self.wizard_view.MODULE_CONFIG
        step_num = self.wizard_view.get_step_number()
        progress_bar = _generate_progress_bar(step_num, self.wizard_view.TOTAL_STEPS)
        
        current_module = self.get_current_module()
        
        embed = discord.Embed(
            title="⚙️ Configuração de Módulos",
            description=f"{progress_bar}\n\n**Etapa {step_num}/{self.wizard_view.TOTAL_STEPS}**: Configure cada módulo selecionado",
            color=discord.Color.blue()
        )
        
        if current_module:
            module_config = MODULE_CONFIGS.get(current_module, {})
            module_name = module_config.get("name", current_module)
            embed.add_field(
                name=f"📦 Configurando: {module_name}",
                value=f"Módulo {self.current_module_index + 1} de {len(self.selected_modules)}",
                inline=False
            )
            embed.add_field(
                name="ℹ️ Instruções",
                value="Use o botão abaixo para abrir a configuração completa deste módulo. Você pode configurá-lo agora ou depois pelo dashboard principal.",
                inline=False
            )
        else:
            embed.add_field(
                name="✅ Todos os módulos configurados",
                value="Você pode avançar para a próxima etapa.",
                inline=False
            )
        
        return embed
    
    @discord.ui.button(label="⚙️ Configurar Módulo Atual", style=discord.ButtonStyle.primary, row=0)
    async def configure_current_module(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre configuração do módulo atual."""
        current_module = self.get_current_module()
        if not current_module:
            await interaction.response.send_message("❌ Todos os módulos já foram configurados.", ephemeral=True)
            return
        
        module_config = MODULE_CONFIGS.get(current_module, {})
        view_class = module_config.get("view_class")
        
        if not view_class:
            await interaction.response.send_message("❌ Módulo não encontrado.", ephemeral=True)
            return
        
        # Cria view do módulo
        if current_module == "tickets":
            view = view_class(self.bot, self.db, self.guild, parent_view=self)
            await view.load_existing_settings()
            embed = await view.update_embed()
        elif current_module == "registration":
            view = view_class(self.bot, self.db, self.config, self.guild.id, parent_view=self)
            embed = await view.build_embed()
        elif current_module == "actions":
            view = view_class(self.bot, self.db, self.guild, parent_view=self)
            await view._update_select_options()
            embed = await view.build_embed()
        elif current_module == "voice_points":
            view = view_class(self.bot, self.db, self.guild.id, parent_view=self)
            embed = await view.build_embed()
        elif current_module == "naval":
            view = view_class(self.bot, self.db, self.guild, parent_view=self)
            embed = await view.build_embed()
        else:
            await interaction.response.send_message("❌ Módulo não suportado.", ephemeral=True)
            return
        
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="⏭️ Próximo Módulo", style=discord.ButtonStyle.primary, row=0)
    async def next_module(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Avança para próximo módulo."""
        self.current_module_index += 1
        
        if self.current_module_index >= len(self.selected_modules):
            # Todos os módulos configurados, avança para permissões
            self.wizard_view.current_step = self.wizard_view.PERMISSIONS
            await self.wizard_view.save_progress()
            embed = await self.wizard_view.build_embed()
            await interaction.response.edit_message(embed=embed, view=self.wizard_view)
        else:
            # Próximo módulo
            embed = await self.build_embed()
            await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="⏭️ Pular", style=discord.ButtonStyle.secondary, row=0)
    async def skip_module(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Pula módulo atual."""
        # Simula avanço para próximo módulo
        self.current_module_index += 1
        
        if self.current_module_index >= len(self.selected_modules):
            # Todos os módulos pulados, avança para permissões
            next_step_name = self.wizard_view.get_next_step()
            if next_step_name:
                self.wizard_view.current_step = next_step_name
            else:
                self.wizard_view.current_step = self.wizard_view.PERMISSIONS
            
            await self.wizard_view.save_progress()
            embed = await self.wizard_view.build_embed()
            await self.wizard_view._update_view_buttons()
            await interaction.response.edit_message(embed=embed, view=self.wizard_view)
        else:
            embed = await self.build_embed()
            await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="⬅️ Anterior", style=discord.ButtonStyle.secondary, row=4)
    async def previous_step(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Volta para etapa anterior."""
        self.wizard_view.current_step = self.wizard_view.MODULE_SELECTION
        await self.wizard_view.save_progress()
        module_selection_view = WizardModuleSelectionView(self.bot, self.db, self.config, self.guild, self.wizard_view)
        embed = await module_selection_view.build_embed()
        await interaction.response.edit_message(embed=embed, view=module_selection_view)


class RestoreView(discord.ui.View):
    """View para restaurar configurações de backup."""
    
    def __init__(self, bot: commands.Bot, db: Database, guild: discord.Guild, parent_view=None):
        super().__init__(timeout=300)
        self.bot = bot
        self.db = db
        self.guild = guild
        self.parent_view = parent_view
        self.selected_backup = None
        
        if self.parent_view:
            self.add_item(BackButton(self.parent_view))
    
    async def build_embed(self) -> discord.Embed:
        """Constrói embed de restauração."""
        backups = await self.db.list_backups(self.guild.id, limit=10)
        
        embed = discord.Embed(
            title="🔄 Restaurar Configurações",
            description="Selecione um backup para restaurar ou criar novos itens automaticamente.",
            color=discord.Color.blue()
        )
        
        if backups:
            backup_list = []
            for i, backup in enumerate(backups[:5], 1):
                backup_date = backup.get("created_at", "Desconhecido")
                backup_id = backup.get("id", "?")
                backup_list.append(f"{i}. Backup #{backup_id} - {backup_date}")
            
            embed.add_field(
                name="💾 Backups Disponíveis",
                value="\n".join(backup_list) if backup_list else "Nenhum backup encontrado.",
                inline=False
            )
        else:
            embed.add_field(
                name="❌ Nenhum backup encontrado",
                value="Crie um backup primeiro usando o botão '💾 Criar Backup' no dashboard.",
                inline=False
            )
        
        # Health check
        health = await _health_check_config(self.guild, self.db)
        if not health["is_healthy"]:
            missing_text = "\n".join([f"• {item['name']}" for item in health["missing_items"][:5]])
            embed.add_field(
                name="⚠️ Itens Faltantes",
                value=missing_text,
                inline=False
            )
        
        return embed
    
    @discord.ui.button(label="🔄 Restaurar do Último Backup", style=discord.ButtonStyle.primary, row=0)
    async def restore_latest(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Restaura do backup mais recente."""
        await interaction.response.defer(ephemeral=True)
        
        backup = await self.db.get_latest_backup(self.guild.id)
        if not backup:
            await interaction.followup.send("❌ Nenhum backup encontrado.", ephemeral=True)
            return
        
        await self._restore_backup(interaction, backup)
    
    async def _restore_backup(self, interaction: discord.Interaction, backup: Dict[str, Any]):
        """Restaura um backup específico com lógica de criação automática."""
        backup_data = backup.get("backup_data", {})
        created_items = []
        restored_items = []
        failed_items = []
        
        # Restaura configurações básicas
        settings = backup_data.get("settings", {})
        if settings:
            # Processa canais
            channel_mapping = {
                "channel_registration_embed": "Canal de Registro",
                "channel_welcome": "Canal de Boas-vindas",
                "channel_leaves": "Canal de Saídas",
                "channel_warnings": "Canal de Advertências",
                "channel_approval": "Canal de Aprovação",
                "channel_records": "Canal de Registros",
                "channel_naval": "Canal de Batalha Naval",
            }
            
            settings_to_update = {}
            
            for key, value in settings.items():
                if key.startswith("channel_") and value:
                    channel_id = int(value) if str(value).isdigit() else None
                    if channel_id:
                        channel = self.guild.get_channel(channel_id)
                        if channel:
                            # Canal existe, usa o ID
                            settings_to_update[key] = channel.id
                            restored_items.append(f"Canal: {channel_mapping.get(key, key)}")
                        else:
                            # Canal não existe, tenta criar
                            # Mapeia nomes mais amigáveis para criação
                            name_mapping = {
                                "channel_registration_embed": "cadastro",
                                "channel_welcome": "boas-vindas",
                                "channel_leaves": "saidas",
                                "channel_warnings": "advertencias",
                                "channel_approval": "aprovacao",
                                "channel_records": "registros",
                                "channel_naval": "batalha-naval",
                            }
                            channel_name_short = name_mapping.get(key, key.replace("channel_", "").replace("_", "-"))
                            channel_name_display = channel_mapping.get(key, key)
                            
                            try:
                                new_channel = await self.guild.create_text_channel(
                                    name=channel_name_short.lower(),
                                    reason=f"Canal restaurado do backup por {interaction.user}"
                                )
                                
                                # Se for canal sensível, aplica permissões
                                if key in ["channel_warnings", "channel_approval"]:
                                    bot_member = self.guild.get_member(self.bot.user.id)
                                    staff_roles = [role for role in bot_member.roles if role.permissions.administrator] if bot_member else []
                                    await _setup_secure_channel_permissions(new_channel, staff_roles)
                                
                                settings_to_update[key] = new_channel.id
                                created_items.append(f"{channel_name_display} (criado)")
                            except Exception as e:
                                LOGGER.error("Erro ao criar canal %s: %s", channel_name_short, e)
                                failed_items.append(channel_name_display)
                
                elif key.startswith("role_") and value:
                    role_id = int(value) if str(value).isdigit() else None
                    if role_id:
                        role = self.guild.get_role(role_id)
                        if role:
                            # Cargo existe, usa o ID
                            settings_to_update[key] = role.id
                            restored_items.append(f"Cargo: {key.replace('role_', '').upper()}")
                        else:
                            # Cargo não existe, tenta criar
                            role_name = key.replace("role_", "").upper()
                            try:
                                new_role = await self.guild.create_role(
                                    name=role_name,
                                    reason=f"Cargo restaurado do backup por {interaction.user}"
                                )
                                settings_to_update[key] = new_role.id
                                created_items.append(f"Cargo: {role_name} (criado)")
                            except Exception as e:
                                LOGGER.error("Erro ao criar cargo %s: %s", role_name, e)
                                failed_items.append(f"Cargo: {role_name}")
                
                elif not key.startswith("channel_") and not key.startswith("role_"):
                    # Outros campos (message_set_embed, etc)
                    settings_to_update[key] = value
            
            # Atualiza settings
            if settings_to_update:
                await self.db.upsert_settings(self.guild.id, **settings_to_update)
        
        # Restaura outras configurações
        ticket_settings = backup_data.get("ticket_settings", {})
        if ticket_settings:
            await self.db.upsert_ticket_settings(self.guild.id, **ticket_settings)
        
        action_settings = backup_data.get("action_settings", {})
        if action_settings:
            await self.db.upsert_action_settings(self.guild.id, **action_settings)
        
        voice_settings = backup_data.get("voice_settings", {})
        if voice_settings:
            await self.db.upsert_voice_settings(self.guild.id, **voice_settings)
        
        # Monta mensagem de resultado
        result_parts = []
        if restored_items:
            result_parts.append(f"✅ Restaurados: {len(restored_items)} item(ns)")
        if created_items:
            result_parts.append(f"🆕 Criados: {len(created_items)} item(ns)")
        if failed_items:
            result_parts.append(f"❌ Falhas: {len(failed_items)} item(ns)")
        
        result_text = "\n".join(result_parts) if result_parts else "✅ Backup restaurado!"
        
        if created_items:
            result_text += f"\n\n**Itens criados automaticamente:**\n" + "\n".join(created_items[:5])
            if len(created_items) > 5:
                result_text += f"\n+ {len(created_items) - 5} item(ns) adicional(is)"
        
        await interaction.followup.send(
            result_text,
            ephemeral=True
        )
        
        # Atualiza embed
        embed = await self.build_embed()
        await interaction.message.edit(embed=embed, view=self)


class SetupCog(commands.Cog):
    """Cog para o Dashboard Central de configuração."""
    
    def __init__(self, bot: commands.Bot, db: Database, config: ConfigManager):
        self.bot = bot
        self.db = db
        self.config = config
    
    @commands.command(name="setup")
    @commands.has_permissions(administrator=True)
    async def interactive_setup(self, ctx: commands.Context):
        """Abre o Dashboard Central de configuração do bot (apenas administradores).

Uso: !setup

Exemplos:
- !setup
"""
        # Verifica se já está sendo processado (prevenção de duplicação) - thread-safe
        msg_id = ctx.message.id
        with self.bot._processing_lock:
            if msg_id in self.bot._processing_messages:
                return
            
            # Marca como em processamento IMEDIATAMENTE (antes de qualquer await)
            self.bot._processing_messages.add(msg_id)
        
        try:
            LOGGER.info("[TRACE] !setup RECEBIDO - Usuario: %s, Guild: %s, Msg_ID: %s, Channel: %s", 
                        ctx.author.id, ctx.guild.id, ctx.message.id, ctx.channel.id)
        
            guild = ctx.guild
            if not guild:
                await ctx.send("❌ Use este comando em um servidor.")
                return
            
            LOGGER.info("[EXEC] !setup INICIADO - Usuario: %s (ID: %s), Guild: %s (ID: %s)", 
                        ctx.author.name, ctx.author.id, guild.name, guild.id)
            
            view = MainDashboardView(self.bot, self.db, self.config, guild)
            await view._add_dynamic_buttons()
            embed = await view.build_embed()
            
            # Deleta o comando após execução
            try:
                # Verifica permissão antes de deletar
                if ctx.channel.permissions_for(ctx.me).manage_messages:
                    await ctx.message.delete()
                else:
                    LOGGER.debug("Sem permissão para deletar mensagem em %s", ctx.channel.id)
            except discord.errors.HTTPException as e:
                LOGGER.warning("Erro HTTP ao deletar mensagem: %s", e)
            except Exception as e:
                LOGGER.warning("Erro ao deletar mensagem do comando: %s", e)
            
            # Usa ctx.send ao invés de ctx.reply para evitar erro quando mensagem foi deletada
            reply_msg = await ctx.send(embed=embed, view=view)
            
            LOGGER.info("[SUCCESS] Dashboard enviado (msg_id: %s) para %s", reply_msg.id, guild.name)
            LOGGER.info("[FINALIZED] !setup concluído para %s", ctx.author.name)
        finally:
            # Remove do set de processamento após 2 segundos
            await asyncio.sleep(2)
            with self.bot._processing_lock:
                self.bot._processing_messages.discard(msg_id)


async def setup(bot):
    """Função de setup para carregamento da extensão."""
    from config_manager import ConfigManager
    from db import Database
    
    await bot.add_cog(SetupCog(bot, bot.db, bot.config_manager))

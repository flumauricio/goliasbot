"""Motor de Promoção Automática do Sistema de Hierarquia."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple

import discord
from discord.ext import commands, tasks

from db import Database
from .repository import HierarchyRepository
from .cache import HierarchyCache
from .models import HierarchyConfig, HierarchyUserStatus
from .utils import check_bot_hierarchy

LOGGER = logging.getLogger(__name__)


@dataclass
class RequirementCheck:
    """Resultado de verificação de um requisito."""
    name: str
    current: int
    required: int
    met: bool
    emoji: str = ""
    
    @property
    def progress_percentage(self) -> int:
        """Calcula porcentagem de progresso."""
        if self.required == 0:
            return 100
        return min(100, int((self.current / self.required) * 100))


@dataclass
class PromotionEligibility:
    """Resultado completo de verificação de elegibilidade."""
    is_eligible: bool
    requirements: List[RequirementCheck]
    min_required: int
    total_defined: int
    
    @property
    def overall_progress(self) -> int:
        """Progresso médio de todos requisitos."""
        if not self.requirements:
            return 0
        percentages = [req.progress_percentage for req in self.requirements]
        return int(sum(percentages) / len(percentages))
    
    @property
    def summary(self) -> str:
        """Resumo textual da elegibilidade."""
        met_count = len([r for r in self.requirements if r.met])
        if self.min_required == self.total_defined:
            return f"{'✅' if self.is_eligible else '❌'} Requisitos: {met_count}/{self.total_defined}"
        else:
            return f"{'✅' if self.is_eligible else '❌'} Requisitos: {met_count}/{self.total_defined} (mín: {self.min_required})"


class HierarchyPromotionCog(commands.Cog):
    """Cog para gerenciar promoções automáticas de hierarquia."""
    
    def __init__(self, bot: commands.Bot, db: Database):
        self.bot = bot
        self.db = db
        
        # Inicializa repository e cache
        cache = HierarchyCache()
        self.repository = HierarchyRepository(db, cache)
        
        # Semáforo para controlar concorrência (máximo 10 verificações simultâneas)
        self._semaphore = asyncio.Semaphore(10)
        
        # Lock para proteger _analytics_cache de race conditions
        self._analytics_cache_lock = asyncio.Lock()
        
        # Cache de analytics por usuário (TTL: 5 minutos)
        self._analytics_cache: Dict[Tuple[int, int], Tuple[Dict[str, Any], datetime]] = {}
        self._analytics_cache_ttl = timedelta(minutes=5)
        
        # Locks para controle de vagas (evita race conditions)
        self._vacancy_locks: Dict[Tuple[int, int], asyncio.Lock] = {}
        
        # Task de verificação periódica
        self._check_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def cog_load(self):
        """Inicializa task loop ao carregar o cog."""
        self._running = True
        # Cria task sem aguardar bot estar pronto (será aguardado no loop)
        self._check_task = asyncio.create_task(self._check_loop())
        LOGGER.info("HierarchyPromotionCog carregado - task loop iniciado")
    
    async def cog_unload(self):
        """Cancela task loop ao descarregar o cog."""
        self._running = False
        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass
        LOGGER.info("HierarchyPromotionCog descarregado")
    
    async def _check_loop(self):
        """Loop customizado que verifica promoções com intervalo configurável por servidor."""
        await self.bot.wait_until_ready()
        
        # Cria uma task separada para cada servidor com seu próprio intervalo
        tasks = []
        for guild in self.bot.guilds:
            task = asyncio.create_task(self._check_guild_loop(guild))
            tasks.append(task)
        
        # Aguarda todas as tasks (ou até serem canceladas)
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        except Exception:
            pass
    
    async def _check_guild_loop(self, guild: discord.Guild):
        """Loop de verificação para um servidor específico com intervalo configurável."""
        await self.bot.wait_until_ready()
        
        while self._running:
            try:
                # Busca intervalo configurado para este servidor
                settings = await self.db.get_settings(guild.id)
                interval = settings.get("hierarchy_check_interval_hours", 1)
                if isinstance(interval, str):
                    try:
                        interval = int(interval)
                    except ValueError:
                        interval = 1
                
                if interval < 1:
                    interval = 1
                
                # Verifica se há cargos configurados
                configs = await self.repository.get_all_configs(guild.id)
                if configs:
                    # Verifica promoções do servidor
                    await self._check_guild_promotions(guild, configs)
                
                # Aguarda o intervalo configurado antes da próxima verificação
                await asyncio.sleep(interval * 3600)  # Converte horas para segundos
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                LOGGER.error(
                    "Erro no loop de verificação para servidor %s: %s",
                    guild.id, e, exc_info=True
                )
                await asyncio.sleep(3600)  # Espera 1 hora em caso de erro
    
    async def check_promotions_now(self, guild_id: Optional[int] = None, check_all_members: bool = True) -> Dict[str, Any]:
        """
        Executa verificação de promoções imediatamente.
        
        Args:
            guild_id: ID do servidor (None = todos os servidores)
            check_all_members: Se True, verifica todos os membros. Se False, apenas ativos recentemente.
            
        Returns:
            Dict com resultado da verificação
        """
        results = {
            "checked_guilds": 0,
            "promotions": 0,
            "approval_requests": 0,
            "checked_users": 0,
            "errors": []
        }
        
        try:
            if guild_id:
                guild = self.bot.get_guild(guild_id)
                if guild:
                    configs = await self.repository.get_all_configs(guild.id)
                    if configs:
                        result = await self._check_guild_promotions(guild, configs, check_all_members=check_all_members)
                        results["checked_guilds"] = 1
                        results["checked_users"] = result.get("checked_users", 0)
                        results["promotions"] = result.get("promotions", 0)
                        results["approval_requests"] = result.get("approval_requests", 0)
                else:
                    results["errors"].append(f"Servidor {guild_id} não encontrado")
            else:
                # Verifica todos os servidores
                for guild in self.bot.guilds:
                    try:
                        configs = await self.repository.get_all_configs(guild.id)
                        if configs:
                            result = await self._check_guild_promotions(guild, configs, check_all_members=check_all_members)
                            results["checked_guilds"] += 1
                            results["checked_users"] += result.get("checked_users", 0)
                            results["promotions"] += result.get("promotions", 0)
                            results["approval_requests"] += result.get("approval_requests", 0)
                    except Exception as e:
                        results["errors"].append(f"Servidor {guild.id}: {str(e)}")
                        LOGGER.error(
                            "Erro ao verificar promoções no servidor %s: %s",
                            guild.id, e, exc_info=True
                        )
        except Exception as e:
            results["errors"].append(str(e))
            LOGGER.error("Erro ao executar verificação imediata: %s", e, exc_info=True)
        
        return results
    
    async def _check_guild_promotions(
        self, guild: discord.Guild, configs: List[HierarchyConfig], check_all_members: bool = False
    ) -> Dict[str, Any]:
        """
        Verifica promoções para um servidor específico.
        
        Args:
            guild: Servidor Discord
            configs: Lista de configurações de hierarquia
            check_all_members: Se True, verifica todos os membros. Se False, apenas ativos recentemente.
            
        Returns:
            Dict com estatísticas da verificação
        """
        result = {
            "checked_users": 0,
            "promotions": 0,
            "approval_requests": 0
        }
        
        # Verifica se cargos configurados ainda existem (evita erros de cargo deletado)
        valid_configs = []
        missing_roles = []
        for config in configs:
            role = guild.get_role(config.role_id)
            if role:
                valid_configs.append(config)
            else:
                missing_roles.append(config)
                LOGGER.warning(
                    "Cargo de hierarquia não encontrado: %s (ID: %d) no servidor %s",
                    config.role_name, config.role_id, guild.id
                )
        
        # Se houver cargos faltando, envia aviso no canal de logs
        if missing_roles:
            settings = await self.db.get_settings(guild.id)
            log_channel_id = settings.get("rank_log_channel")
            if log_channel_id:
                log_channel = guild.get_channel(int(log_channel_id))
                if log_channel and isinstance(log_channel, discord.TextChannel):
                    missing_names = ", ".join([c.role_name for c in missing_roles[:5]])
                    if len(missing_roles) > 5:
                        missing_names += f" e mais {len(missing_roles) - 5}"
                    
                    embed = discord.Embed(
                        title="⚠️ Aviso: Cargos de Hierarquia Não Encontrados",
                        description=f"Os seguintes cargos foram deletados do servidor:\n{missing_names}\n\nUse `!setup` para remover ou atualizar essas configurações.",
                        color=discord.Color.orange(),
                        timestamp=discord.utils.utcnow()
                    )
                    try:
                        await log_channel.send(embed=embed)
                    except Exception:
                        pass  # Ignora se não tiver permissão
        
        if not valid_configs:
            LOGGER.debug("Nenhum cargo válido configurado no servidor %s", guild.id)
            return result  # Nenhum cargo válido configurado
        
        # Usa apenas configs válidos
        configs = valid_configs
        
        # Busca usuários para verificar
        if check_all_members:
            # Verifica usuários ligados à hierarquia:
            # - membros que possuem algum cargo de hierarquia no Discord
            # - usuários que possuem status registrado no banco (cobre casos de remoção manual)
            LOGGER.debug("Verificando usuários com cargos de hierarquia + status no banco (modo manual) no servidor %s", guild.id)

            hierarchy_role_ids = [c.role_id for c in configs]
            users_set: set[int] = set()

            # 1) Membros dos cargos de hierarquia (Discord)
            for role_id in hierarchy_role_ids:
                role = guild.get_role(role_id)
                if not role:
                    continue
                for m in role.members:
                    if not m.bot:
                        users_set.add(m.id)

            # 2) Usuários presentes no banco (para pegar quem teve cargo removido manualmente)
            try:
                db_user_ids = await self.db.get_hierarchy_user_status_user_ids(guild.id)
                for uid in db_user_ids:
                    users_set.add(uid)
            except Exception as e:
                LOGGER.warning("Erro ao buscar user_ids da hierarchy_user_status: %s", e)

            users_to_check = sorted(users_set)
        else:
            # Busca apenas usuários ativos recentemente (últimos 30 minutos)
            LOGGER.debug("Verificando apenas usuários ativos recentemente no servidor %s", guild.id)
            active_users = await self._get_active_users(guild.id, minutes=30)
            users_to_check = active_users
        
        if not users_to_check:
            LOGGER.debug("Nenhum usuário para verificar no servidor %s", guild.id)
            return result
        
        LOGGER.debug("Verificando %d usuários no servidor %s", len(users_to_check), guild.id)
        
        # Processa em lotes de 50 usuários
        batch_size = 50
        for i in range(0, len(users_to_check), batch_size):
            batch = users_to_check[i:i + batch_size]
            
            # Processa batch com semáforo
            tasks_list = [
                self._check_user_with_semaphore(guild, user_id, configs)
                for user_id in batch
            ]
            
            # Executa até 10 simultaneamente
            batch_results = await asyncio.gather(*tasks_list, return_exceptions=True)
            
            # Conta promoções e pedidos de aprovação
            for task_result in batch_results:
                result["checked_users"] += 1
                if isinstance(task_result, dict):
                    if task_result.get("action") == "promoted":
                        result["promotions"] += 1
                    elif task_result.get("action") == "approval_request":
                        result["approval_requests"] += 1
                    elif task_result.get("error"):
                        # Loga erro mas não conta como promoção
                        LOGGER.warning(
                            "Erro ao verificar usuário: %s",
                            task_result.get("error")
                        )
                elif isinstance(task_result, Exception):
                    # Exceção capturada pelo gather
                    LOGGER.warning(
                        "Exceção ao verificar usuário: %s",
                        task_result,
                        exc_info=True
                    )
            
            # Limpa cache de analytics expirado após cada batch
            self._cleanup_analytics_cache()
            
            # Pequeno delay entre batches para não sobrecarregar
            await asyncio.sleep(1)
        
        # Mantém apenas um resumo final (info)
        LOGGER.info(
            "Verificação concluída no servidor %s: %d verificados, %d promoções, %d aprovações pendentes",
            guild.id, result["checked_users"], result["promotions"], result["approval_requests"]
        )
        
        return result
    
    async def _check_user_with_semaphore(
        self, guild: discord.Guild, user_id: int, configs: List[HierarchyConfig]
    ):
        """Verifica usuário com controle de concorrência."""
        async with self._semaphore:
            return await self._check_user_for_promotion(guild, user_id, configs)
    
    async def _get_active_users(self, guild_id: int, minutes: int = 30) -> List[int]:
        """Busca usuários ativos recentemente usando analytics."""
        try:
            # Busca usuários com last_active nos últimos N minutos
            cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
            cutoff_str = cutoff_time.strftime("%Y-%m-%d %H:%M:%S")
            
            async with self.db._conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT DISTINCT user_id FROM user_analytics
                    WHERE guild_id = ? AND last_active >= ?
                    """,
                    (str(guild_id), cutoff_str)
                )
                rows = await cur.fetchall()
                return [int(row[0]) for row in rows]
        except Exception as e:
            LOGGER.error("Erro ao buscar usuários ativos: %s", e, exc_info=True)
            return []
    
    async def _check_user_for_promotion(
        self, guild: discord.Guild, user_id: int, configs: List[HierarchyConfig]
    ) -> Optional[Dict[str, Any]]:
        """
        Verifica se usuário pode ser promovido (lógica de precedência).
        
        Args:
            guild: Servidor Discord
            user_id: ID do usuário
            configs: Lista de todas as configurações de hierarquia
            
        Returns:
            Dict com resultado da verificação ou None
        """
        try:
            # Verifica se membro existe no servidor
            member = guild.get_member(user_id)
            if not member:
                LOGGER.debug("Usuário %s não encontrado no servidor %s", user_id, guild.id)
                return None
            
            if member.bot:
                LOGGER.debug("Usuário %s é um bot, ignorando", user_id)
                return None
            
            # Busca status atual do usuário
            user_status = await self.repository.get_user_status(guild.id, user_id)
            
            # Verifica cooldown
            if user_status and user_status.promotion_cooldown_until:
                if datetime.utcnow() < user_status.promotion_cooldown_until:
                    LOGGER.debug("Usuário %s em cooldown até %s", user_id, user_status.promotion_cooldown_until)
                    return None  # Ainda em cooldown
            
            # Verifica se deve ignorar promoção automática
            if user_status and user_status.ignore_auto_promote_until:
                if datetime.utcnow() < user_status.ignore_auto_promote_until:
                    LOGGER.debug("Usuário %s ignorado para promoção automática até %s", user_id, user_status.ignore_auto_promote_until)
                    return None  # Ignorar promoção automática
            
            # Busca cargo atual do usuário (verifica tanto no banco quanto no Discord)
            # IMPORTANTE: Sincroniza estado do Discord com o banco antes de verificar promoção
            current_role_id = None
            current_level = 0
            
            # Obtém lista de IDs de cargos do membro no Discord
            member_role_ids = [role.id for role in member.roles]
            
            # Primeiro verifica no banco
            if user_status and user_status.current_role_id:
                stored_role_id = user_status.current_role_id
                
                # Verifica se o cargo ainda existe no Discord E se o membro ainda tem esse cargo
                role_exists = guild.get_role(stored_role_id) is not None
                member_has_role = stored_role_id in member_role_ids
                
                if role_exists and member_has_role:
                    # Cargo existe e membro tem: encontra level_order
                    for config in configs:
                        if config.role_id == stored_role_id:
                            current_role_id = stored_role_id
                            current_level = config.level_order
                            break
                else:
                    # Cargo foi removido manualmente do Discord OU cargo não existe mais
                    if not member_has_role:
                        LOGGER.info(
                            "🔄 Sincronização: usuário %s tinha cargo %s no banco mas não tem mais no Discord. Limpando banco...",
                            user_id, stored_role_id
                        )
                    else:
                        LOGGER.info(
                            "🔄 Sincronização: cargo %s do usuário %s não existe mais no servidor. Limpando banco...",
                            stored_role_id, user_id
                        )
                    
                    # Limpa o cargo atual no banco E remove cooldowns para permitir nova verificação
                    LOGGER.info(
                        "🔄 Limpando cargo e cooldowns do usuário %s para permitir nova verificação",
                        user_id
                    )
                    try:
                        await self.repository.update_user_status(
                            guild.id,
                            user_id,
                            current_role_id=None,
                            promotion_cooldown_until=None,  # Remove cooldown
                            ignore_auto_promote_until=None  # Remove flag de ignorar
                        )
                        # Invalida cache para garantir que mudanças sejam refletidas
                        self.repository.cache.invalidate_user_status(guild.id, user_id)
                        LOGGER.info("✅ Sincronização concluída: banco atualizado para usuário %s", user_id)
                    except Exception as e:
                        LOGGER.warning(
                            "⚠️ Erro ao atualizar banco durante sincronização para usuário %s: %s. Continuando verificação...",
                            user_id, e
                        )
                        # Mesmo com erro, continua a verificação com estado limpo
                    
                    current_role_id = None
                    current_level = 0
            
            # Se não encontrou no banco (ou foi limpo), verifica no Discord (sincronização)
            if not current_role_id:
                # Verifica se o membro tem algum cargo de hierarquia no Discord
                for config in configs:
                    if config.role_id in member_role_ids:
                        current_role_id = config.role_id
                        current_level = config.level_order
                        LOGGER.info(
                            "🔄 Sincronização: usuário %s tem cargo %s (level %d) no Discord mas não no banco. Atualizando banco...",
                            user_id, config.role_name, config.level_order
                        )
                        # Atualiza banco para refletir o estado do Discord
                        try:
                            await self.repository.update_user_status(
                                guild.id,
                                user_id,
                                current_role_id=config.role_id
                            )
                            LOGGER.info("✅ Sincronização concluída: banco atualizado para usuário %s", user_id)
                        except Exception as e:
                            LOGGER.warning(
                                "⚠️ Erro ao atualizar banco durante sincronização para usuário %s: %s. Continuando verificação...",
                                user_id, e
                            )
                            # Mesmo com erro, usa o cargo encontrado no Discord
                        
                        break
            
            LOGGER.info(
                "🔍 Iniciando verificação - Usuário: %s | Cargo Atual: %s | Level Atual: %d",
                user_id, current_role_id or "Nenhum", current_level
            )
            
            # Se após sincronização o usuário não tem cargo (current_level = 0),
            # ele será verificado para o cargo mais baixo (maior level_order)
            if current_level == 0:
                LOGGER.info(
                    "📋 Usuário %s não tem cargo de hierarquia (após sincronização). Será verificado para o cargo mais baixo disponível.",
                    user_id
                )
            
            # LÓGICA DE PRECEDÊNCIA: 
            # - Nível 1 = Mais alto (Comandante Geral)
            # - Nível N = Mais baixo (Tenente)
            # - Se current_level = 0 (sem cargo): busca o MAIOR level_order (nível mais baixo)
            # - Se current_level > 0 (tem cargo): busca level_order = current_level - 1 (um nível acima, número menor)
            next_config = None
            
            if current_level == 0:
                # Usuário sem cargo: busca o cargo com o MAIOR level_order (nível mais baixo)
                max_level = 0
                for config in configs:
                    if config.level_order > max_level:
                        role = guild.get_role(config.role_id)
                        if role:
                            max_level = config.level_order
                            next_config = config
                
                if next_config:
                    LOGGER.info(
                        "🎯 Próximo cargo encontrado (sem cargo): %s (Level %d - mais baixo) | ID: %d",
                        next_config.role_name, next_config.level_order, next_config.role_id
                    )
            else:
                # Usuário com cargo: busca o cargo com level_order = current_level - 1 (um nível acima)
                target_level = current_level - 1
                if target_level < 1:
                    # Já está no nível 1 (topo), não há promoção possível
                    LOGGER.debug("Usuário %s já está no nível máximo (Level 1)", user_id)
                    return None
                
                for config in configs:
                    if config.level_order == target_level:
                        # Verifica se cargo ainda existe antes de usar (evita erro de cargo deletado)
                        role = guild.get_role(config.role_id)
                        if role:
                            next_config = config
                            LOGGER.info(
                                "🎯 Próximo cargo encontrado: %s (Level %d) | ID: %d",
                                config.role_name, config.level_order, config.role_id
                            )
                            break
                        else:
                            LOGGER.warning(
                                "Cargo de hierarquia não encontrado: %s (ID: %d) no servidor %s",
                                config.role_name, config.role_id, guild.id
                            )
            
            # Se não há próximo cargo válido, usuário está no topo ou cargo foi deletado
            if not next_config:
                LOGGER.info("❌ Usuário %s não tem próximo cargo disponível (level atual: %d)", user_id, current_level)
                return None
            
            # Verifica se auto_promote está habilitado
            if not next_config.auto_promote:
                LOGGER.debug(
                    "Usuário %s não pode ser promovido: auto_promote desabilitado para cargo %s",
                    user_id, next_config.role_name
                )
                return None
            
            # Verifica requisitos
            meets_requirements, detailed_reason = await self._check_requirements(
                guild, user_id, next_config
            )
            
            # Log INFO para diagnóstico (aparece sempre, não apenas em modo debug)
            LOGGER.info(
                "🔍 Verificação de Promoção - Usuário: %s | Cargo: %s (Level %d) | Status: %s",
                user_id, next_config.role_name, next_config.level_order,
                "✅ ATENDE" if meets_requirements else "❌ NÃO ATENDE"
            )
            LOGGER.info(
                "📋 Detalhes dos Requisitos:\n%s",
                detailed_reason
            )
            LOGGER.info(
                "⚙️ Configuração do Cargo: auto_promote=%s, requires_approval=%s, req_min_any=%d",
                next_config.auto_promote, next_config.requires_approval, next_config.req_min_any
            )
            
            if not meets_requirements:
                LOGGER.info("❌ Usuário %s NÃO será promovido: requisitos não atendidos", user_id)
                return None
            
            LOGGER.debug("Usuário %s atende requisitos. Prosseguindo com promoção/solicitação...", user_id)
            
            # Verifica se cargo alvo ainda existe (evita erro de cargo deletado)
            target_role = guild.get_role(next_config.role_id)
            if not target_role:
                LOGGER.warning(
                    "Cargo alvo não encontrado para promoção: role_id=%d, user_id=%d, guild_id=%d",
                    next_config.role_id, user_id, guild.id
                )
                # Envia aviso no canal de logs se configurado
                settings = await self.db.get_settings(guild.id)
                log_channel_id = settings.get("rank_log_channel")
                if log_channel_id:
                    log_channel = guild.get_channel(int(log_channel_id))
                    if log_channel and isinstance(log_channel, discord.TextChannel):
                        try:
                            embed = discord.Embed(
                                title="⚠️ Erro: Cargo de Hierarquia Não Encontrado",
                                description=f"Tentativa de promoção falhou: cargo `{next_config.role_name}` (ID: {next_config.role_id}) foi deletado.\n\nUse `!setup` para atualizar a configuração.",
                                color=discord.Color.orange(),
                                timestamp=discord.utils.utcnow()
                            )
                            await log_channel.send(embed=embed)
                        except Exception:
                            pass
                return None  # Cargo não existe, não pode promover
            
            # Verifica vagas disponíveis - COM LOCK para evitar race condition
            if next_config.max_vacancies > 0:
                lock = self._get_vacancy_lock(guild.id, next_config.role_id)
                async with lock:
                    # Re-verifica vagas dentro do lock (double-check pattern)
                    current_count = await self._count_users_with_role(
                        guild, next_config.role_id
                    )
                    if current_count >= next_config.max_vacancies:
                        return None  # Sem vagas disponíveis
                    
                    # Se requires_approval, cria pedido (ainda dentro do lock)
                    if next_config.requires_approval:
                        LOGGER.info(
                            "🔔 Cargo requer aprovação! Criando pedido de aprovação para usuário %s → cargo %s",
                            user_id, next_config.role_name
                        )
                        result = await self._create_approval_request(
                            guild, user_id, current_role_id, next_config, detailed_reason
                        )
                        LOGGER.info(
                            "📝 Pedido de aprovação criado: request_id=%s, action=%s",
                            result.get("request_id"), result.get("action")
                        )
                        # Delay para evitar rate limit
                        await asyncio.sleep(0.5)
                        return result
                    
                    # Promove diretamente (ainda dentro do lock)
                    result = await self._promote_user(
                        guild, user_id, current_role_id, next_config, detailed_reason, "system"
                    )
                    # Delay para evitar rate limit global do Discord
                    await asyncio.sleep(0.5)
                    return result
            else:
                # Sem limite de vagas, não precisa de lock
                # Se requires_approval, cria pedido
                if next_config.requires_approval:
                    LOGGER.info(
                        "🔔 Cargo requer aprovação! Criando pedido de aprovação para usuário %s → cargo %s",
                        user_id, next_config.role_name
                    )
                    result = await self._create_approval_request(
                        guild, user_id, current_role_id, next_config, detailed_reason
                    )
                    LOGGER.info(
                        "📝 Pedido de aprovação criado: request_id=%s, action=%s",
                        result.get("request_id"), result.get("action")
                    )
                    await asyncio.sleep(0.5)
                    return result
                
                # Promove diretamente
                result = await self._promote_user(
                    guild, user_id, current_role_id, next_config, detailed_reason, "system"
                )
                # Delay para evitar rate limit global do Discord
                await asyncio.sleep(0.5)
                return result
            
        except Exception as e:
            LOGGER.error(
                "Erro ao verificar promoção para usuário %s: %s",
                user_id, e, exc_info=True
            )
            return None
    
    async def _check_requirements(
        self, guild: discord.Guild, user_id: int, config: HierarchyConfig
    ) -> Tuple[bool, str]:
        """
        Verifica se usuário atende requisitos do cargo.
        
        Returns:
            Tupla (atende_requisitos, razão_detalhada)
        """
        # Busca analytics do usuário (com cache)
        analytics = await self._get_user_analytics(guild.id, user_id)
        
        # Busca tempo de voz
        voice_time = await self.db.get_total_voice_time(guild.id, user_id)
        
        # Busca data de entrada no servidor
        member = guild.get_member(user_id)
        if not member:
            return False, "Membro não encontrado no servidor"
        
        join_date = member.joined_at
        if not join_date:
            return False, "Data de entrada não disponível"
        
        # Calcula dias no servidor (timezone-aware)
        now = datetime.now(join_date.tzinfo) if join_date.tzinfo else datetime.utcnow()
        days_in_server = (now - join_date).days
        
        # Verifica cada requisito
        requirements_met = []
        requirements_failed = []
        
        # Mensagens
        if config.req_messages > 0:
            msg_count = analytics.get("msg_count", 0)
            if msg_count >= config.req_messages:
                requirements_met.append(f"Mensagens: {msg_count}/{config.req_messages} ✅")
            else:
                requirements_failed.append(f"Mensagens: {msg_count}/{config.req_messages} ❌")
        
        # Call Time
        if config.req_call_time > 0:
            call_hours = voice_time // 3600
            req_hours = config.req_call_time // 3600
            if voice_time >= config.req_call_time:
                requirements_met.append(f"Call Time: {call_hours}h/{req_hours}h ✅")
            else:
                requirements_failed.append(f"Call Time: {call_hours}h/{req_hours}h ❌")
        
        # Reações
        if config.req_reactions > 0:
            reactions = analytics.get("reactions_given", 0) + analytics.get("reactions_received", 0)
            if reactions >= config.req_reactions:
                requirements_met.append(f"Reações: {reactions}/{config.req_reactions} ✅")
            else:
                requirements_failed.append(f"Reações: {reactions}/{config.req_reactions} ❌")
        
        # Dias no servidor
        if config.req_min_days > 0:
            if days_in_server >= config.req_min_days:
                requirements_met.append(f"Dias no Servidor: {days_in_server}/{config.req_min_days} ✅")
            else:
                requirements_failed.append(f"Dias no Servidor: {days_in_server}/{config.req_min_days} ❌")
        
        # Dias no cargo atual
        if config.min_days_in_role > 0:
            # Busca quando o usuário recebeu o cargo atual
            user_status = await self.repository.get_user_status(guild.id, user_id)
            days_in_current_role = 0
            
            if user_status and user_status.current_role_id:
                # Tenta buscar a última promoção na history
                history_entry = await self.db.get_latest_hierarchy_history(
                    guild.id, user_id, action_type='promoted', to_role_id=user_status.current_role_id
                )
                
                if history_entry and history_entry.get('created_at'):
                    # Converte string para datetime se necessário
                    promotion_date = history_entry.get('created_at')
                    if isinstance(promotion_date, str):
                        try:
                            promotion_date = datetime.strptime(promotion_date, "%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            try:
                                promotion_date = datetime.fromisoformat(promotion_date.replace('Z', '+00:00'))
                            except (ValueError, AttributeError):
                                promotion_date = None
                    
                    if promotion_date:
                        if isinstance(promotion_date, datetime):
                            now_utc = datetime.utcnow()
                            days_in_current_role = (now_utc - promotion_date.replace(tzinfo=None)).days
                
                # Fallback: usa updated_at do user_status se não encontrou na history
                if days_in_current_role == 0 and user_status.promoted_at:
                    now_utc = datetime.utcnow()
                    days_in_current_role = (now_utc - user_status.promoted_at.replace(tzinfo=None) if user_status.promoted_at.tzinfo else now_utc - user_status.promoted_at).days
            
            # Verifica se atende o requisito
            if days_in_current_role >= config.min_days_in_role:
                requirements_met.append(f"Tempo no Cargo: {days_in_current_role}/{config.min_days_in_role} dias ✅")
            else:
                requirements_failed.append(f"Tempo no Cargo: {days_in_current_role}/{config.min_days_in_role} dias ❌")
        
        # Cargos externos necessários
        if config.req_other_roles:
            member_roles = [r.id for r in member.roles]
            missing_roles = [r_id for r_id in config.req_other_roles if r_id not in member_roles]
            if not missing_roles:
                requirements_met.append(f"Cargos Base: Presentes ✅")
            else:
                requirements_failed.append(f"Cargos Base: Faltando {len(missing_roles)} ❌")
        
        # Verifica se atende mínimo necessário (req_min_any)
        total_met = len(requirements_met)
        total_defined = len(requirements_met) + len(requirements_failed)
        min_required = config.req_min_any
        
        # Log detalhado para diagnóstico
        LOGGER.info(
            "📊 Contagem de Requisitos - Cargo: %s | Atendidos: %d | Mínimo necessário: %d | Total definidos: %d",
            config.role_name, total_met, min_required, total_defined
        )
        
        if total_met < min_required:
            detailed_reason = "\n".join(requirements_met + requirements_failed)
            if total_defined > 0:
                detailed_reason += f"\n\n❌ Requisitos atendidos: {total_met}/{total_defined} (mínimo necessário: {min_required})"
            else:
                detailed_reason += f"\n\n❌ Nenhum requisito configurado para este cargo"
            LOGGER.info(
                "❌ Requisitos INSUFICIENTES: %d atendidos de %d necessários (total definidos: %d)",
                total_met, min_required, total_defined
            )
            return False, detailed_reason
        
        # Todos os requisitos necessários foram atendidos
        detailed_reason = "\n".join(requirements_met)
        if requirements_failed:
            detailed_reason += "\n" + "\n".join(requirements_failed)
        
        if total_defined > 0:
            if min_required == total_defined:
                # Se precisa atender todos, mostra apenas total
                detailed_reason += f"\n\n✅ Requisitos atendidos: {total_met}/{total_defined}"
            else:
                # Se aceita um mínimo, deixa claro
                detailed_reason += f"\n\n✅ Requisitos atendidos: {total_met}/{total_defined} (mínimo necessário: {min_required})"
        
        LOGGER.info(
            "✅ Requisitos SUFICIENTES: %d atendidos de %d necessários (total definidos: %d)",
            total_met, min_required, total_defined
        )
        
        return True, detailed_reason
    
    async def check_requirements_structured(
        self,
        guild: discord.Guild,
        user_id: int,
        config: HierarchyConfig
    ) -> PromotionEligibility:
        """
        Versão estruturada que retorna dados tipados, não string.
        
        Args:
            guild: Servidor Discord
            user_id: ID do usuário
            config: Configuração do cargo a verificar
            
        Returns:
            PromotionEligibility com requisitos estruturados
        """
        analytics = await self._get_user_analytics(guild.id, user_id)
        voice_time = await self.db.get_total_voice_time(guild.id, user_id)
        
        member = guild.get_member(user_id)
        if not member:
            return PromotionEligibility(False, [], 0, 0)
        
        join_date = member.joined_at
        now = datetime.now(join_date.tzinfo) if join_date and join_date.tzinfo else datetime.utcnow()
        days_in_server = (now - join_date).days if join_date else 0
        
        requirements = []
        
        # Mensagens
        if config.req_messages > 0:
            current = analytics.get("msg_count", 0) if analytics else 0
            requirements.append(RequirementCheck(
                name="Mensagens",
                current=current,
                required=config.req_messages,
                met=current >= config.req_messages,
                emoji="💬"
            ))
        
        # Call Time
        if config.req_call_time > 0:
            current_hours = voice_time // 3600
            required_hours = config.req_call_time // 3600
            requirements.append(RequirementCheck(
                name="Call",
                current=current_hours,
                required=required_hours,
                met=voice_time >= config.req_call_time,
                emoji="📞"
            ))
        
        # Reações
        if config.req_reactions > 0:
            current = analytics.get("reactions_given", 0) + analytics.get("reactions_received", 0) if analytics else 0
            requirements.append(RequirementCheck(
                name="Reações",
                current=current,
                required=config.req_reactions,
                met=current >= config.req_reactions,
                emoji="⭐"
            ))
        
        # Dias no servidor
        if config.req_min_days > 0:
            requirements.append(RequirementCheck(
                name="Dias no Servidor",
                current=days_in_server,
                required=config.req_min_days,
                met=days_in_server >= config.req_min_days,
                emoji="📅"
            ))
        
        # Tempo no cargo
        if config.min_days_in_role > 0:
            user_status = await self.repository.get_user_status(guild.id, user_id)
            days_in_role = 0
            
            if user_status and user_status.current_role_id:
                history_entry = await self.db.get_latest_hierarchy_history(
                    guild.id, user_id, action_type='promoted', to_role_id=user_status.current_role_id
                )
                
                if history_entry and history_entry.get('created_at'):
                    promotion_date = history_entry.get('created_at')
                    if isinstance(promotion_date, str):
                        try:
                            promotion_date = datetime.strptime(promotion_date, "%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            try:
                                promotion_date = datetime.fromisoformat(promotion_date.replace('Z', '+00:00'))
                            except (ValueError, AttributeError):
                                promotion_date = None
                    
                    if promotion_date and isinstance(promotion_date, datetime):
                        now_utc = datetime.utcnow()
                        days_in_role = (now_utc - promotion_date.replace(tzinfo=None)).days
                
                if days_in_role == 0 and user_status.promoted_at:
                    now_utc = datetime.utcnow()
                    days_in_role = (now_utc - user_status.promoted_at.replace(tzinfo=None) if user_status.promoted_at.tzinfo else now_utc - user_status.promoted_at).days
            
            requirements.append(RequirementCheck(
                name="Tempo no Cargo",
                current=days_in_role,
                required=config.min_days_in_role,
                met=days_in_role >= config.min_days_in_role,
                emoji="⏳"
            ))
        
        met_count = len([r for r in requirements if r.met])
        is_eligible = met_count >= config.req_min_any
        
        return PromotionEligibility(
            is_eligible=is_eligible,
            requirements=requirements,
            min_required=config.req_min_any,
            total_defined=len(requirements)
        )
    
    async def _get_user_analytics(
        self, guild_id: int, user_id: int
    ) -> Dict[str, Any]:
        """Busca analytics do usuário (com cache)."""
        cache_key = (guild_id, user_id)
        
        # Acesso protegido ao cache com lock
        async with self._analytics_cache_lock:
            if cache_key in self._analytics_cache:
                data, expiry = self._analytics_cache[cache_key]
                if datetime.utcnow() < expiry:
                    return data
                else:
                    # Expirou, remove
                    self._analytics_cache.pop(cache_key, None)
        
        # Busca do banco
        analytics = await self.db.get_user_analytics(guild_id, user_id)
        if not analytics:
            analytics = {
                "msg_count": 0,
                "img_count": 0,
                "mentions_sent": 0,
                "mentions_received": 0,
                "reactions_given": 0,
                "reactions_received": 0
            }
        
        # Armazena no cache (protegido)
        expiry = datetime.utcnow() + self._analytics_cache_ttl
        async with self._analytics_cache_lock:
            self._analytics_cache[cache_key] = (analytics, expiry)
        
        return analytics
    
    def _cleanup_analytics_cache(self) -> None:
        """Remove entradas expiradas do cache de analytics para evitar vazamento de memória."""
        # Usa copy() para evitar RuntimeError durante iteração
        now = datetime.utcnow()
        async def _cleanup():
            async with self._analytics_cache_lock:
                # Cria cópia do dicionário para iterar com segurança
                cache_copy = dict(self._analytics_cache)
                keys_to_remove = [
                    k for k, (_, expiry) in cache_copy.items()
                    if now >= expiry
                ]
                for key in keys_to_remove:
                    self._analytics_cache.pop(key, None)
        
        # Executa limpeza de forma assíncrona segura
        asyncio.create_task(_cleanup())
    
    def _get_vacancy_lock(self, guild_id: int, role_id: int) -> asyncio.Lock:
        """Obtém ou cria lock para um cargo específico (evita race conditions)."""
        key = (guild_id, role_id)
        if key not in self._vacancy_locks:
            self._vacancy_locks[key] = asyncio.Lock()
        return self._vacancy_locks[key]
    
    async def _count_users_with_role(self, guild: discord.Guild, role_id: int) -> int:
        """Conta quantos usuários têm o cargo (excluindo bots)."""
        role = guild.get_role(role_id)
        if not role:
            return 0
        
        count = 0
        for member in role.members:
            if not member.bot:
                count += 1
        
        return count
    
    async def _create_approval_request(
        self,
        guild: discord.Guild,
        user_id: int,
        current_role_id: Optional[int],
        target_config: HierarchyConfig,
        detailed_reason: str
    ) -> Dict[str, Any]:
        """Cria pedido de aprovação para promoção e envia para canal de aprovação de hierarquia."""
        LOGGER.info(
            "🔔 Iniciando criação de pedido de aprovação - Usuário: %s | Cargo: %s | Guild: %s",
            user_id, target_config.role_name, guild.id
        )
        
        # Busca canal de aprovação de hierarquia (campo específico)
        settings = await self.db.get_settings(guild.id)
        staff_channel_id = settings.get("hierarchy_approval_channel")
        
        LOGGER.info(
            "📋 Canal de aprovação configurado: %s",
            staff_channel_id or "Não configurado"
        )
        
        # Fallback: se não configurado, usa canal de log de hierarquia
        if not staff_channel_id:
            staff_channel_id = settings.get("rank_log_channel")
            LOGGER.info(
                "📋 Usando canal de log como fallback: %s",
                staff_channel_id or "Não configurado"
            )
        
        if not staff_channel_id:
            LOGGER.warning(
                "❌ Canal de staff não configurado para aprovações em %s. "
                "Criando pedido no banco mas sem enviar mensagem.",
                guild.id
            )
            # Cria pedido mesmo assim, mas não envia mensagem
            request_id = await self.repository.create_promotion_request(
                guild.id,
                user_id,
                target_config.role_id,
                request_type='auto',
                current_role_id=current_role_id,
                reason="Atende todos os requisitos",
                message_id=None
            )
            return {
                "action": "approval_request",
                "request_id": request_id,
                "user_id": user_id,
                "target_role_id": target_config.role_id
            }
        
        staff_channel = guild.get_channel(int(staff_channel_id))
        if not staff_channel or not isinstance(staff_channel, discord.TextChannel):
            LOGGER.warning(
                "❌ Canal de staff não encontrado para aprovações em %s (ID: %s). "
                "Criando pedido no banco mas sem enviar mensagem.",
                guild.id, staff_channel_id
            )
            # Cria pedido mesmo assim
            request_id = await self.repository.create_promotion_request(
                guild.id,
                user_id,
                target_config.role_id,
                request_type='auto',
                current_role_id=current_role_id,
                reason="Atende todos os requisitos",
                message_id=None
            )
            return {
                "action": "approval_request",
                "request_id": request_id,
                "user_id": user_id,
                "target_role_id": target_config.role_id
            }
        
        # Verifica permissão para enviar
        if not staff_channel.permissions_for(guild.me).send_messages:
            LOGGER.warning(
                "❌ Sem permissão para enviar no canal de staff em %s (canal: %s). "
                "Criando pedido no banco mas sem enviar mensagem.",
                guild.id, staff_channel.name
            )
            request_id = await self.repository.create_promotion_request(
                guild.id,
                user_id,
                target_config.role_id,
                request_type='auto',
                current_role_id=current_role_id,
                reason="Atende todos os requisitos",
                message_id=None
            )
            return {
                "action": "approval_request",
                "request_id": request_id,
                "user_id": user_id,
                "target_role_id": target_config.role_id
            }
        
        # Cria pedido no banco (sem message_id ainda)
        request_id = await self.repository.create_promotion_request(
            guild.id,
            user_id,
            target_config.role_id,
            request_type='auto',
            current_role_id=current_role_id,
            reason="Atende todos os requisitos",
            message_id=None
        )
        
        LOGGER.debug("Pedido de aprovação criado no banco com ID: %d", request_id)
        
        # Busca pedido criado (com retry em caso de timing)
        request = None
        for attempt in range(3):  # Tenta até 3 vezes
            pending_requests = await self.repository.get_pending_requests(guild.id, user_id)
            for req in pending_requests:
                if req.id == request_id:
                    request = req
                    break
            
            if request:
                break
            
            # Pequeno delay antes de tentar novamente
            if attempt < 2:
                await asyncio.sleep(0.1)
                LOGGER.debug("Tentativa %d de buscar pedido criado...", attempt + 2)
        
        # Se ainda não encontrou, cria objeto manualmente
        if not request:
            LOGGER.warning(
                "Pedido %d não encontrado após criação, criando objeto manualmente",
                request_id
            )
            from .models import PromotionRequest
            from datetime import datetime
            request = PromotionRequest(
                id=request_id,
                guild_id=guild.id,
                user_id=user_id,
                current_role_id=current_role_id,
                target_role_id=target_config.role_id,
                request_type='auto',
                requested_by=None,
                reason="Atende todos os requisitos",
                status='pending',
                message_id=None,
                created_at=datetime.utcnow(),
                resolved_at=None,
                resolved_by=None
            )
        
        # Cria embed e view de aprovação
        from .approval_view import PromotionApprovalView, build_approval_embed
        
        embed = build_approval_embed(guild, request, detailed_reason)
        view = PromotionApprovalView(self.bot, self.db, request, detailed_reason)
        
        # Registra view no bot para persistência (custom_id único permite processar cliques após reinício)
        if request.id:
            self.bot.add_view(view)
        
        # Envia mensagem no canal de staff
        try:
            LOGGER.info(
                "📤 Enviando pedido de aprovação para canal: %s (ID: %s)",
                staff_channel.name, staff_channel.id
            )
            message = await staff_channel.send(embed=embed, view=view)
            
            # Atualiza pedido com message_id (atualiza diretamente no banco)
            async with self.db._conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE promotion_requests
                    SET message_id = ?
                    WHERE id = ?
                    """,
                    (str(message.id), request_id)
                )
            await self.db._conn.commit()
            
            LOGGER.info(
                "✅ Pedido de promoção enviado com sucesso para aprovação: request_id=%d, message_id=%d, canal=%s",
                request_id, message.id, staff_channel.name
            )
            
        except Exception as e:
            LOGGER.error(
                "❌ Erro ao enviar pedido de aprovação no canal %s: %s",
                staff_channel.name if staff_channel else "desconhecido", e, exc_info=True
            )
        
        return {
            "action": "approval_request",
            "request_id": request_id,
            "user_id": user_id,
            "target_role_id": target_config.role_id
        }
    
    async def _promote_user(
        self,
        guild: discord.Guild,
        user_id: int,
        current_role_id: Optional[int],
        target_config: HierarchyConfig,
        detailed_reason: str,
        performed_by: str
    ) -> Dict[str, Any]:
        """
        Promove usuário diretamente (transação atômica).
        
        Args:
            guild: Servidor Discord
            user_id: ID do usuário
            current_role_id: ID do cargo atual (opcional)
            target_config: Configuração do cargo alvo
            detailed_reason: Razão detalhada da promoção
            performed_by: Quem executou ('system' ou user_id)
        """
        member = guild.get_member(user_id)
        if not member:
            return {"error": "Membro não encontrado"}
        
        target_role = guild.get_role(target_config.role_id)
        if not target_role:
            return {"error": "Cargo alvo não encontrado"}
        
        # CRÍTICO: Verifica hierarquia do bot antes de promover (evita loop infinito)
        can_manage, error_msg = check_bot_hierarchy(guild, target_role)
        if not can_manage:
            LOGGER.error(
                "Bot não pode gerenciar cargo %s (ID: %d) no servidor %s: %s. "
                "Marcando usuário para skip por 24 horas.",
                target_config.role_name, target_config.role_id, guild.id, error_msg
            )
            
            # Marca usuário para "pular" por 24 horas (evita loop infinito)
            skip_until = (datetime.utcnow() + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
            await self.repository.update_user_status(
                guild.id,
                user_id,
                ignore_auto_promote_until=skip_until
            )
            
            # Envia aviso no canal de logs se configurado
            settings = await self.db.get_settings(guild.id)
            log_channel_id = settings.get("rank_log_channel")
            if log_channel_id:
                log_channel = guild.get_channel(int(log_channel_id))
                if log_channel and isinstance(log_channel, discord.TextChannel):
                    try:
                        embed = discord.Embed(
                            title="⚠️ Erro Crítico: Bot Sem Hierarquia para Promover",
                            description=(
                                f"Tentativa de promoção de {member.mention} para {target_role.mention} falhou.\n\n"
                                f"**Erro:** {error_msg}\n\n"
                                f"**Solução:** Mova o cargo do Bot para cima do cargo `{target_config.role_name}` na hierarquia do servidor.\n\n"
                                f"O usuário foi marcado para pular promoções automáticas por 24 horas."
                            ),
                            color=discord.Color.red(),
                            timestamp=discord.utils.utcnow()
                        )
                        await log_channel.send(embed=embed)
                    except Exception:
                        pass
            
            return {"error": f"Bot não tem hierarquia suficiente: {error_msg}"}
        
        try:
            # Remove cargo anterior se existir
            if current_role_id:
                old_role = guild.get_role(current_role_id)
                if old_role:
                    try:
                        await member.remove_roles(old_role, reason="Promoção automática")
                    except discord.Forbidden:
                        LOGGER.warning(
                            "Sem permissão para remover cargo %s do usuário %s",
                            current_role_id, user_id
                        )
            
            # Adiciona novo cargo (com verificação de hierarquia já feita)
            await member.add_roles(target_role, reason="Promoção automática")
            
            # Atualiza status no banco (transação atômica)
            now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            cooldown_until = (datetime.utcnow() + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
            
            await self.repository.update_user_status(
                guild.id,
                user_id,
                current_role_id=target_config.role_id,
                promoted_at=now_str,
                last_promotion_check=now_str,
                promotion_cooldown_until=cooldown_until
            )
            
            # Adiciona ao histórico
            await self.repository.add_history(
                guild.id,
                user_id,
                "promotion",
                target_config.role_id,
                from_role_id=current_role_id,
                reason="Promoção automática",
                performed_by=int(performed_by) if performed_by != "system" else None,
                detailed_reason=detailed_reason
            )
            
            # Invalida cache
            self.repository.cache.invalidate_user_status(guild.id, user_id)
            
            LOGGER.info(
                "Usuário %s promovido de %s para %s",
                user_id, current_role_id, target_config.role_id
            )
            
            # Envia DM de parabéns
            try:
                embed_congrats = discord.Embed(
                    title="🎉 Parabéns! Você foi promovido!",
                    description=f"Você foi promovido para **{target_role.name}** no servidor **{guild.name}**!",
                    color=discord.Color.gold()
                )
                embed_congrats.add_field(
                    name="📈 Progresso",
                    value=detailed_reason,
                    inline=False
                )
                embed_congrats.set_footer(text="Continue se esforçando para subir ainda mais!")
                
                await member.send(embed=embed_congrats)
            except discord.Forbidden:
                LOGGER.debug("Não foi possível enviar DM para usuário %s (privacidade)", user_id)
            except Exception as e:
                LOGGER.warning("Erro ao enviar DM de parabéns: %s", e)
            
            # Envia log para canal de hierarquia
            await self._send_promotion_log(
                guild, member, current_role_id, target_config.role_id,
                detailed_reason, performed_by
            )
            
            return {
                "action": "promoted",
                "user_id": user_id,
                "from_role_id": current_role_id,
                "to_role_id": target_config.role_id
            }
            
        except Exception as e:
            LOGGER.error(
                "Erro ao promover usuário %s: %s",
                user_id, e, exc_info=True
            )
            return {"error": str(e)}
    
    async def _send_promotion_log(
        self,
        guild: discord.Guild,
        member: discord.Member,
        from_role_id: Optional[int],
        to_role_id: int,
        detailed_reason: str,
        performed_by: str
    ) -> None:
        """Envia log de promoção para o canal configurado."""
        try:
            settings = await self.db.get_settings(guild.id)
            log_channel_id = settings.get("rank_log_channel")
            
            if not log_channel_id:
                LOGGER.debug("Canal de log de hierarquia não configurado para servidor %s", guild.id)
                return
            
            log_channel = guild.get_channel(int(log_channel_id))
            if not log_channel or not isinstance(log_channel, discord.TextChannel):
                LOGGER.warning("Canal de log de hierarquia não encontrado: %s", log_channel_id)
                return
            
            # Verifica permissão
            if not log_channel.permissions_for(guild.me).send_messages:
                LOGGER.warning("Sem permissão para enviar no canal de log de hierarquia")
                return
            
            # Busca nomes dos cargos
            from_role = guild.get_role(from_role_id) if from_role_id else None
            to_role = guild.get_role(to_role_id)
            
            from_role_name = from_role.name if from_role else "Sem cargo"
            to_role_name = to_role.name if to_role else f"Cargo ID: {to_role_id}"
            
            # Determina quem executou
            if performed_by == "system":
                performed_by_text = "Sistema Automático"
            else:
                performer = guild.get_member(int(performed_by)) if performed_by.isdigit() else None
                performed_by_text = performer.mention if performer else f"ID: {performed_by}"
            
            # Cria embed
            embed = discord.Embed(
                title="🎖️ Promoção Realizada",
                description=f"{member.mention} foi promovido!",
                color=discord.Color.gold(),
                timestamp=discord.utils.utcnow()
            )
            
            embed.add_field(
                name="📊 Progressão",
                value=f"**{from_role_name}** → **{to_role_name}**",
                inline=False
            )
            
            embed.add_field(
                name="📋 Requisitos Atendidos",
                value=detailed_reason[:1024],  # Limite do Discord
                inline=False
            )
            
            embed.add_field(
                name="👤 Executado por",
                value=performed_by_text,
                inline=True
            )
            
            embed.set_footer(text=f"ID do Usuário: {member.id}")
            
            await log_channel.send(embed=embed)
            LOGGER.info("Log de promoção enviado para canal %s", log_channel_id)
            
        except Exception as e:
            LOGGER.error("Erro ao enviar log de promoção: %s", e, exc_info=True)


async def setup(bot: commands.Bot):
    """Função de setup para carregar o cog."""
    db = bot.db
    await bot.add_cog(HierarchyPromotionCog(bot, db))

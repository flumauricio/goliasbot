"""Funções utilitárias para o sistema de hierarquia."""

import logging
from typing import Tuple, Optional

import discord

LOGGER = logging.getLogger(__name__)


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """
    Converte cor hexadecimal para RGB.
    
    Args:
        hex_color: Cor em formato hex (#RRGGBB ou RRGGBB)
        
    Returns:
        Tupla (R, G, B)
    """
    hex_color = hex_color.lstrip('#')
    if len(hex_color) != 6:
        raise ValueError("Cor hex deve ter 6 caracteres")
    
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    
    return (r, g, b)


def rgb_to_hex(r: int, g: int, b: int) -> str:
    """
    Converte RGB para hexadecimal.
    
    Args:
        r: Componente vermelho (0-255)
        g: Componente verde (0-255)
        b: Componente azul (0-255)
        
    Returns:
        Cor em formato hex (#RRGGBB)
    """
    return f"#{r:02x}{g:02x}{b:02x}"


def generate_color_gradient(
    start_hex: str,
    end_hex: str,
    steps: int
) -> list[str]:
    """
    Gera gradiente hexadecimal profissional entre duas cores.
    
    Args:
        start_hex: Cor inicial em hex (#RRGGBB)
        end_hex: Cor final em hex (#RRGGBB)
        steps: Número de cores no gradiente
        
    Returns:
        Lista de cores hex (#RRGGBB)
    """
    if steps < 2:
        return [start_hex, end_hex]
    
    start_rgb = hex_to_rgb(start_hex)
    end_rgb = hex_to_rgb(end_hex)
    
    gradient = []
    for i in range(steps):
        # Interpolação linear
        ratio = i / (steps - 1)
        
        r = int(start_rgb[0] + (end_rgb[0] - start_rgb[0]) * ratio)
        g = int(start_rgb[1] + (end_rgb[1] - start_rgb[1]) * ratio)
        b = int(start_rgb[2] + (end_rgb[2] - start_rgb[2]) * ratio)
        
        # Garante que os valores estão no range válido
        r = max(0, min(255, r))
        g = max(0, min(255, g))
        b = max(0, min(255, b))
        
        gradient.append(rgb_to_hex(r, g, b))
    
    return gradient


async def apply_admin_permissions(guild: discord.Guild, role: discord.Role) -> bool:
    """
    Aplica permissões de administrador a um cargo.
    
    Args:
        guild: Servidor Discord
        role: Cargo a ser configurado como admin
        
    Returns:
        True se sucesso, False caso contrário
    """
    try:
        # Cria permissões de administrador
        permissions = discord.Permissions(administrator=True)
        
        # Aplica as permissões
        await role.edit(permissions=permissions)
        return True
    except discord.Forbidden:
        LOGGER.warning("Sem permissão para editar cargo %s como admin", role.name)
        return False
    except Exception as e:
        LOGGER.error("Erro ao aplicar permissões de admin: %s", e, exc_info=True)
        return False


async def position_role_hierarchically(
    guild: discord.Guild,
    role: discord.Role,
    level_order: int,
    hierarchy_configs: list
) -> bool:
    """
    Posiciona um cargo hierarquicamente no servidor baseado no level_order.
    Nível 1 = mais alto, nível 2 = abaixo do nível 1, etc.
    
    Args:
        guild: Servidor Discord
        role: Cargo a ser posicionado
        level_order: Nível do cargo (1 = mais alto)
        hierarchy_configs: Lista de todos os HierarchyConfig do servidor
        
    Returns:
        True se sucesso, False caso contrário
    """
    try:
        # Filtra apenas cargos da hierarquia que existem no Discord
        existing_hierarchy_roles = []
        for config in hierarchy_configs:
            if config.role_id == role.id:
                continue  # Pula o próprio cargo
            hierarchy_role = guild.get_role(config.role_id)
            if hierarchy_role:
                existing_hierarchy_roles.append((hierarchy_role, config.level_order))
        
        # Se não há outros cargos da hierarquia, posiciona logo abaixo do bot
        if not existing_hierarchy_roles:
            bot_member = guild.me
            if bot_member and bot_member.top_role:
                # Posiciona logo abaixo do top role do bot
                target_position = bot_member.top_role.position - 1
                if target_position < 0:
                    target_position = 0
                await role.edit(position=target_position)
                return True
            return False
        
        # Encontra o cargo com o próximo nível mais alto (menor level_order)
        # que seja menor que o level_order atual
        # Ex: Se level_order=3, procura nível 2 ou 1 (mais altos)
        next_higher = None
        for hr, hr_level in existing_hierarchy_roles:
            if hr_level < level_order:  # Nível mais alto (menor número = mais alto)
                if next_higher is None or hr_level > next_higher[1]:  # Pega o mais próximo (maior hr_level mas ainda < level_order)
                    next_higher = (hr, hr_level)
        
        # Encontra o cargo com o próximo nível mais baixo (maior level_order)
        # que seja maior que o level_order atual
        # Ex: Se level_order=2, procura nível 3 ou 4 (mais baixos)
        next_lower = None
        for hr, hr_level in existing_hierarchy_roles:
            if hr_level > level_order:  # Nível mais baixo (maior número = mais baixo)
                if next_lower is None or hr_level < next_lower[1]:  # Pega o mais próximo (menor hr_level mas ainda > level_order)
                    next_lower = (hr, hr_level)
        
        # Determina posição alvo
        # No Discord, position maior = mais alto na hierarquia
        # Nível 1 (mais alto) deve ter position maior que nível 2
        if next_higher:
            # Posiciona logo abaixo do cargo de nível mais alto (menor position)
            target_position = next_higher[0].position - 1
        elif next_lower:
            # Posiciona logo acima do cargo de nível mais baixo (maior position)
            target_position = next_lower[0].position + 1
        else:
            # Se não há referência, posiciona logo abaixo do bot
            bot_member = guild.me
            if bot_member and bot_member.top_role:
                target_position = bot_member.top_role.position - 1
                if target_position < 0:
                    target_position = 0
            else:
                return False
        
        # Garante que a posição seja válida
        if target_position < 0:
            target_position = 0
        
        # Aplica a posição
        await role.edit(position=target_position)
        return True
        
    except discord.Forbidden:
        LOGGER.warning("Sem permissão para reposicionar cargo %s", role.name)
        return False
    except Exception as e:
        LOGGER.error("Erro ao posicionar cargo hierarquicamente: %s", e, exc_info=True)
        return False


def check_bot_hierarchy(guild, role) -> Tuple[bool, Optional[str]]:
    """
    Verifica se o bot pode gerenciar o cargo (hierarquia).
    
    Args:
        guild: Servidor Discord
        role: Cargo a verificar
        
    Returns:
        Tupla (pode_gerenciar, mensagem_erro)
    """
    bot_member = guild.get_member(guild.me.id)
    if not bot_member:
        return False, "Bot member não encontrado"
    
    if not bot_member.guild_permissions.manage_roles:
        return False, "Bot não tem permissão 'Gerenciar Cargos'"
    
    if bot_member.top_role:
        if role.position >= bot_member.top_role.position:
            return False, f"O cargo '{role.name}' está acima do cargo do bot na hierarquia"
    
    return True, None

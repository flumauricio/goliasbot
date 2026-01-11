"""Utilitários para o sistema de pontos por voz."""


def format_time(seconds: int) -> str:
    """Formata segundos em formato legível: Xh Ymin Zseg.
    
    Args:
        seconds: Tempo em segundos
        
    Returns:
        String formatada como "Xh Ymin Zseg"
        
    Examples:
        >>> format_time(45020)
        '12h 30min 20seg'
        >>> format_time(3661)
        '1h 1min 1seg'
        >>> format_time(0)
        '0h 0min 0seg'
    """
    if seconds < 0:
        seconds = 0
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    return f"{hours}h {minutes}min {secs}seg"

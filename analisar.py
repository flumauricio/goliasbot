#!/usr/bin/env python3
"""
Script Analisar - Consolidar Código do Projeto

Consolida todos os arquivos de código do projeto em um único arquivo .txt
com timestamp, incluindo o caminho completo de cada arquivo.

Uso: python analisar.py
"""

import os
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Set, Tuple


# Extensões de arquivos de código a serem incluídos
CODE_EXTENSIONS = {
    # Python
    '.py', '.pyw', '.pyx', '.pyi',
    # JavaScript/TypeScript
    '.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs',
    # Java
    '.java', '.kt', '.scala', '.groovy',
    # C/C++
    '.c', '.cpp', '.cc', '.cxx', '.h', '.hpp', '.hxx', '.hh',
    # C#
    '.cs', '.csx',
    # Go
    '.go',
    # Rust
    '.rs',
    # Ruby
    '.rb', '.rake',
    # PHP
    '.php', '.phtml',
    # Swift
    '.swift',
    # Shell scripts
    '.sh', '.bash', '.zsh', '.fish',
    # Windows scripts
    '.bat', '.cmd', '.ps1',
    # Outros
    '.sql', '.r', '.m', '.pl', '.pm', '.lua', '.vim', '.el',
    # Configuração como código
    '.yaml', '.yml', '.json', '.toml', '.ini', '.cfg', '.conf',
    # Web
    '.html', '.htm', '.css', '.sass', '.scss', '.less',
    # Markdown e documentação
    '.md', '.rst', '.txt',
    # Outros
    '.xml', '.xsd', '.xsl', '.xslt'
}

# Padrões de pastas/arquivos a ignorar
IGNORE_PATTERNS = {
    # Python
    '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache',
    'venv', '.venv', 'env', '.env', 'virtualenv',
    '*.pyc', '*.pyo', '*.pyd', '__init__.pyc',
    # Node.js
    'node_modules', '.npm', '.yarn',
    # Build/Dist
    'build', 'dist', '.build', '.dist',
    # Git
    '.git', '.gitignore', '.gitattributes',
    # IDEs
    '.vscode', '.idea', '.vs', '.settings',
    # OS
    '.DS_Store', 'Thumbs.db', '.DS_Store',
    # Outros
    '.coverage', '.pytest_cache', '.tox',
    '*.egg-info', '.eggs',
    # Específicos deste projeto
    'codigo_completo*.txt', 'CODIGO_COMPLETO.txt'
}


def should_ignore(path: Path, root: Path) -> bool:
    """
    Verifica se um caminho deve ser ignorado
    
    Args:
        path: Caminho do arquivo/pasta
        root: Diretório raiz do projeto
        
    Returns:
        True se deve ser ignorado, False caso contrário
    """
    # Converter para caminho relativo
    try:
        rel_path = path.relative_to(root)
    except ValueError:
        return True
    
    parts = rel_path.parts
    
    # Verificar cada parte do caminho
    for part in parts:
        # Ignorar se alguma parte do caminho corresponder a um padrão
        if part in IGNORE_PATTERNS:
            return True
        
        # Ignorar se começar com ponto (exceto arquivos na raiz)
        if part.startswith('.') and len(parts) > 1:
            # Verificar se é um padrão conhecido
            if part in IGNORE_PATTERNS:
                return True
    
    # Verificar extensão do arquivo
    if path.is_file():
        if path.suffix.lower() not in CODE_EXTENSIONS:
            return False  # Não ignorar se não for código (mas não incluir)
        # Verificar padrões de nome de arquivo
        if path.name in IGNORE_PATTERNS:
            return True
    
    return False


def is_text_file(file_path: Path) -> bool:
    """
    Verifica se um arquivo é texto (não binário)
    
    Args:
        file_path: Caminho do arquivo
        
    Returns:
        True se for texto, False se for binário
    """
    try:
        # Tentar ler os primeiros bytes
        with open(file_path, 'rb') as f:
            chunk = f.read(512)
            # Verificar se contém bytes nulos (indicativo de binário)
            if b'\x00' in chunk:
                return False
            # Tentar decodificar como UTF-8
            chunk.decode('utf-8', errors='strict')
            return True
    except (UnicodeDecodeError, PermissionError, IOError):
        return False


def read_file_content(file_path: Path) -> Tuple[str, bool]:
    """
    Lê o conteúdo de um arquivo
    
    Args:
        file_path: Caminho do arquivo
        
    Returns:
        Tupla (conteúdo, sucesso)
    """
    encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
    
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding, errors='replace') as f:
                content = f.read()
                return content, True
        except (UnicodeDecodeError, PermissionError, IOError) as e:
            continue
    
    return f"[ERRO: Não foi possível ler o arquivo]", False


def find_code_files(root_dir: Path) -> List[Path]:
    """
    Encontra todos os arquivos de código no projeto
    
    Args:
        root_dir: Diretório raiz do projeto
        
    Returns:
        Lista de caminhos de arquivos de código
    """
    code_files = []
    
    # Percorrer recursivamente
    for root, dirs, files in os.walk(root_dir):
        root_path = Path(root)
        
        # Filtrar diretórios a ignorar
        dirs[:] = [d for d in dirs if not should_ignore(root_path / d, root_dir)]
        
        # Processar arquivos
        for file in files:
            file_path = root_path / file
            
            # Verificar se deve ignorar
            if should_ignore(file_path, root_dir):
                continue
            
            # Verificar se é arquivo de código
            if file_path.suffix.lower() in CODE_EXTENSIONS:
                # Verificar se é texto
                if is_text_file(file_path):
                    code_files.append(file_path)
    
    # Ordenar por caminho
    code_files.sort()
    
    return code_files


def generate_output_file(root_dir: Path, code_files: List[Path]) -> Tuple[str, dict]:
    """
    Gera o arquivo consolidado com todo o código
    
    Args:
        root_dir: Diretório raiz do projeto
        code_files: Lista de arquivos de código
        
    Returns:
        Tupla (nome_arquivo, estatísticas)
    """
    # Gerar nome do arquivo com timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"codigo_completo_{timestamp}.txt"
    output_path = root_dir / output_filename
    
    # Estatísticas
    stats = {
        'total_files': 0,
        'total_lines': 0,
        'total_size': 0,
        'errors': 0,
        'files_by_extension': {}
    }
    
    # Abrir arquivo de saída
    with open(output_path, 'w', encoding='utf-8') as out_file:
        # Escrever cabeçalho
        out_file.write("=" * 80 + "\n")
        out_file.write("CONSOLIDAÇÃO DE CÓDIGO DO PROJETO\n")
        out_file.write(f"Gerado em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        out_file.write(f"Diretório raiz: {root_dir}\n")
        out_file.write("=" * 80 + "\n\n")
        
        # Processar cada arquivo
        for file_path in code_files:
            try:
                # Obter caminho relativo
                rel_path = file_path.relative_to(root_dir)
                rel_path_str = str(rel_path).replace('\\', '/')  # Normalizar separadores
                
                # Ler conteúdo
                content, success = read_file_content(file_path)
                
                if not success:
                    stats['errors'] += 1
                
                # Escrever cabeçalho do arquivo
                out_file.write("=" * 80 + "\n")
                out_file.write(f"CAMINHO: {rel_path_str}\n")
                out_file.write("=" * 80 + "\n\n")
                
                # Escrever conteúdo
                out_file.write(content)
                
                # Adicionar linha em branco no final
                if not content.endswith('\n'):
                    out_file.write('\n')
                out_file.write('\n')
                
                # Atualizar estatísticas
                stats['total_files'] += 1
                stats['total_lines'] += content.count('\n')
                stats['total_size'] += len(content.encode('utf-8'))
                
                # Contar por extensão
                ext = file_path.suffix.lower()
                stats['files_by_extension'][ext] = stats['files_by_extension'].get(ext, 0) + 1
                
            except Exception as e:
                stats['errors'] += 1
                out_file.write(f"[ERRO ao processar arquivo: {e}]\n\n")
        
        # Escrever rodapé com estatísticas
        out_file.write("\n" + "=" * 80 + "\n")
        out_file.write("ESTATÍSTICAS\n")
        out_file.write("=" * 80 + "\n")
        out_file.write(f"Total de arquivos processados: {stats['total_files']}\n")
        out_file.write(f"Total de linhas: {stats['total_lines']:,}\n")
        out_file.write(f"Tamanho total: {stats['total_size']:,} bytes ({stats['total_size'] / 1024:.2f} KB)\n")
        out_file.write(f"Erros encontrados: {stats['errors']}\n")
        out_file.write("\nArquivos por extensão:\n")
        for ext, count in sorted(stats['files_by_extension'].items()):
            out_file.write(f"  {ext or '(sem extensão)':15} : {count:4} arquivo(s)\n")
        out_file.write("=" * 80 + "\n")
    
    return output_filename, stats


def main():
    """Função principal"""
    # Obter diretório raiz (onde o script está)
    root_dir = Path(__file__).parent.resolve()
    
    print("=" * 80)
    print("Script Analisar - Consolidar Código do Projeto")
    print("=" * 80)
    print(f"\nDiretório raiz: {root_dir}")
    print("\nProcurando arquivos de código...")
    
    # Encontrar arquivos de código
    code_files = find_code_files(root_dir)
    
    if not code_files:
        print("\nNenhum arquivo de código encontrado!")
        return
    
    print(f"Encontrados {len(code_files)} arquivo(s) de código.\n")
    
    # Gerar arquivo consolidado
    print("Gerando arquivo consolidado...")
    output_filename, stats = generate_output_file(root_dir, code_files)
    
    # Exibir estatísticas
    print("\n" + "=" * 80)
    print("CONCLUÍDO!")
    print("=" * 80)
    print(f"\nArquivo gerado: {output_filename}")
    print(f"Total de arquivos: {stats['total_files']}")
    print(f"Total de linhas: {stats['total_lines']:,}")
    print(f"Tamanho: {stats['total_size']:,} bytes ({stats['total_size'] / 1024:.2f} KB)")
    
    if stats['errors'] > 0:
        print(f"\n⚠ Aviso: {stats['errors']} erro(s) encontrado(s) durante o processamento.")
    
    print("\nArquivos por extensão:")
    for ext, count in sorted(stats['files_by_extension'].items()):
        print(f"  {ext or '(sem extensão)':15} : {count:4} arquivo(s)")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nOperação cancelada pelo usuário.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nErro fatal: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

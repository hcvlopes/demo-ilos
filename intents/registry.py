"""Registry de intenções — única porta de entrada.

O registry mapeia nomes de intenção às suas classes. Usado pelo orquestrador
(F6) para resolver intenção classificada pelo LLM e pelos testes para
iterar e validar envelope.
"""

from intents.capacidade.ativos_em_risco import AtivosEmRiscoPorProcesso
from intents.transversais.acoes_permitidas import AcoesPermitidas
from intents.transversais.explicar_defeito import ExplicarDefeito
from intents.transversais.historico_equipamento import HistoricoEquipamento

REGISTRY: dict[str, type] = {
    "explicar_defeito": ExplicarDefeito,
    "acoes_permitidas": AcoesPermitidas,
    "historico_equipamento": HistoricoEquipamento,
    "ativos_em_risco_por_processo": AtivosEmRiscoPorProcesso,
}


def get_intencao(nome: str):
    """Retorna instância da intenção pelo nome."""
    cls = REGISTRY.get(nome)
    if cls is None:
        raise KeyError(f"Intencao '{nome}' nao registrada. Disponiveis: {list(REGISTRY.keys())}")
    return cls()

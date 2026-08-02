"""Registry de intenções — única porta de entrada.

O registry mapeia nomes de intenção às suas classes. Usado pelo orquestrador
(F6) para resolver intenção classificada pelo LLM e pelos testes para
iterar e validar envelope.
"""

from intents.capacidade.ativos_em_risco import AtivosEmRiscoPorProcesso
from intents.capacidade.impacto_parada import ImpactoParada
from intents.capacidade.plano_manutencao_ativo import PlanoManutencaoAtivo
from intents.navegacao.dependencias_ativo import DependenciasAtivo
from intents.navegacao.explicar_processo import ExplicarProcesso
from intents.navegacao.listar_equipamentos_ativo import ListarEquipamentosAtivo
from intents.navegacao.resumo_edificacao import ResumoEdificacao
from intents.navegacao.resumo_sistema import ResumoSistema
from intents.transversais.acoes_permitidas import AcoesPermitidas
from intents.transversais.cadeia_falha import CadeiaFalha
from intents.transversais.defeitos_abertos import DefeitosAbertos
from intents.transversais.estatisticas_classe import EstatisticasClasse
from intents.transversais.explicar_defeito import ExplicarDefeito
from intents.transversais.historico_equipamento import HistoricoEquipamento
from intents.transversais.monitoramento_equipamento import MonitoramentoEquipamento
from intents.transversais.normas_aplicaveis import NormasAplicaveis
from intents.transversais.ordens_manutencao import OrdensManutencao

REGISTRY: dict[str, type] = {
    "explicar_defeito": ExplicarDefeito,
    "acoes_permitidas": AcoesPermitidas,
    "historico_equipamento": HistoricoEquipamento,
    "ativos_em_risco_por_processo": AtivosEmRiscoPorProcesso,
    "explicar_processo": ExplicarProcesso,
    "listar_equipamentos_ativo": ListarEquipamentosAtivo,
    "resumo_sistema": ResumoSistema,
    "resumo_edificacao": ResumoEdificacao,
    "dependencias_ativo": DependenciasAtivo,
    "defeitos_abertos": DefeitosAbertos,
    "ordens_manutencao": OrdensManutencao,
    "normas_aplicaveis": NormasAplicaveis,
    "monitoramento_equipamento": MonitoramentoEquipamento,
    "cadeia_falha": CadeiaFalha,
    "estatisticas_classe": EstatisticasClasse,
    "impacto_parada": ImpactoParada,
    "plano_manutencao_ativo": PlanoManutencaoAtivo,
}


def get_intencao(nome: str):
    """Retorna instância da intenção pelo nome."""
    cls = REGISTRY.get(nome)
    if cls is None:
        raise KeyError(f"Intencao '{nome}' nao registrada. Disponiveis: {list(REGISTRY.keys())}")
    return cls()

"""Registry de intenções — única porta de entrada.

O registry mapeia nomes de intenção às suas classes. Usado pelo orquestrador
(F6) para resolver intenção classificada pelo LLM e pelos testes para
iterar e validar envelope.
"""

from intents.capacidade.ativos_em_risco import AtivosEmRiscoPorProcesso
from intents.capacidade.impacto_parada import ImpactoParada
from intents.capacidade.plano_manutencao_ativo import PlanoManutencaoAtivo
from intents.capacidade.ranking_sistemas import RankingSistemas
from intents.conformidade.conformidade_normativa import ConformidadeNormativa
from intents.conformidade.requisitos_equipamento import RequisitosEquipamento
from intents.navegacao.carga_centro_trabalho import CargaCentroTrabalho
from intents.navegacao.dependencias_ativo import DependenciasAtivo
from intents.navegacao.escopo_grupo_planejamento import EscopoGrupoPlanejamento
from intents.navegacao.explicar_processo import ExplicarProcesso
from intents.navegacao.listar_equipamentos_ativo import ListarEquipamentosAtivo
from intents.navegacao.resumo_edificacao import ResumoEdificacao
from intents.navegacao.resumo_sistema import ResumoSistema
from intents.transversais.acoes_permitidas import AcoesPermitidas
from intents.transversais.acoes_por_papel import AcoesPorPapel
from intents.transversais.cadeia_falha import CadeiaFalha
from intents.transversais.consequencia_notas import ConsequenciaNotas
from intents.transversais.defeitos_abertos import DefeitosAbertos
from intents.transversais.defeitos_resolvidos import DefeitosResolvidos
from intents.transversais.estatisticas_classe import EstatisticasClasse
from intents.transversais.etapas_ordem import EtapasOrdem
from intents.transversais.explicar_defeito import ExplicarDefeito
from intents.transversais.historico_equipamento import HistoricoEquipamento
from intents.transversais.localizacao_defeito import LocalizacaoDefeito
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
    "conformidade_normativa": ConformidadeNormativa,
    "requisitos_equipamento": RequisitosEquipamento,
    "localizacao_defeito": LocalizacaoDefeito,
    "consequencia_notas": ConsequenciaNotas,
    "etapas_ordem": EtapasOrdem,
    "acoes_por_papel": AcoesPorPapel,
    "defeitos_resolvidos": DefeitosResolvidos,
    "carga_centro_trabalho": CargaCentroTrabalho,
    "escopo_grupo_planejamento": EscopoGrupoPlanejamento,
    "ranking_sistemas": RankingSistemas,
}


def get_intencao(nome: str):
    """Retorna instância da intenção pelo nome."""
    cls = REGISTRY.get(nome)
    if cls is None:
        raise KeyError(f"Intencao '{nome}' nao registrada. Disponiveis: {list(REGISTRY.keys())}")
    return cls()

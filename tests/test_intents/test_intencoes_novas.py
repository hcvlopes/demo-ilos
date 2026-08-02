"""Testes de comportamento das intencoes adicionadas.

Sao offline: uma sessao falsa devolve registros canonizados por consulta, e
o que se verifica e a logica que NAO esta no Cypher — como o envelope conta,
pondera e declara lacuna. Cobertura estrutural (seis campos, tipagem dos
parametros, ausencia de query livre) ja vem de test_envelope.py, que itera o
registry inteiro.
"""

import pytest

from intents.capacidade.ranking_sistemas import RankingSistemas, RankingSistemasParams
from intents.conformidade.conformidade_normativa import (
    ConformidadeNormativa,
    ConformidadeNormativaParams,
)
from intents.conformidade.requisitos_equipamento import (
    RequisitosEquipamento,
    RequisitosEquipamentoParams,
)
from intents.navegacao.carga_centro_trabalho import (
    CargaCentroTrabalho,
    CargaCentroTrabalhoParams,
)
from intents.navegacao.escopo_grupo_planejamento import (
    EscopoGrupoPlanejamento,
    EscopoGrupoPlanejamentoParams,
)
from intents.transversais.acoes_por_papel import AcoesPorPapel, AcoesPorPapelParams
from intents.transversais.consequencia_notas import (
    ConsequenciaNotas,
    ConsequenciaNotasParams,
)
from intents.transversais.defeitos_resolvidos import (
    DefeitosResolvidos,
    DefeitosResolvidosParams,
)
from intents.transversais.etapas_ordem import EtapasOrdem, EtapasOrdemParams
from intents.transversais.localizacao_defeito import (
    LocalizacaoDefeito,
    LocalizacaoDefeitoParams,
)


class No(dict):
    """Nó do grafo — mesma interface que o adapter expoe."""

    def get(self, chave, padrao=None):
        return super().get(chave, padrao)


class Registro(dict):
    def get(self, chave, padrao=None):
        return super().get(chave, padrao)


class Resultado:
    def __init__(self, registros):
        self._registros = [Registro(r) for r in registros]

    def single(self):
        return self._registros[0] if self._registros else None

    def __iter__(self):
        return iter(self._registros)


class SessaoFalsa:
    """Devolve registros conforme trechos presentes na consulta.

    As regras sao pares (marcador, registros): a primeira cuja marca aparece
    na consulta responde. Consulta sem regra devolve vazio, o que exercita
    justamente os caminhos de lacuna.
    """

    def __init__(self, regras):
        self.regras = regras
        self.consultas = []

    def run(self, query, parameters=None):
        self.consultas.append(query)
        for marcador, registros in self.regras:
            if marcador in query:
                return Resultado(registros)
        return Resultado([])


class TestConformidadeNormativa:
    def _sessao(self, diretos=0, por_classe=0, requisitos=2, criticos=1):
        reqs = [
            {"rq": No({
                "id": f"REQ-{i}", "descricao": f"requisito {i}",
                "criticidade": "alta" if i < criticos else "media",
            })}
            for i in range(requisitos)
        ]
        return SessaoFalsa([
            ("(n:Norma) WHERE", [{"n": No({"id": "NORMA-X", "codigo": "NX", "descricao": "norma X"})}]),
            ("TEM_REQUISITO", reqs),
            ("(eq:Equipamento)-[:REGULADO_POR]", [
                {"eq": No({"id": f"EQ-D{i}", "descricao": "d"})} for i in range(diretos)
            ]),
            ("CLASSIFICADO_COMO", [
                {"eq": No({"id": f"EQ-C{i}", "descricao": "c"}), "ct": No({"id": "CT-1", "descricao": "classe"})}
                for i in range(por_classe)
            ]),
            ("count(eq) AS c", [{"c": 10}]),
        ])

    def test_soma_das_duas_vias_sem_duplicar(self):
        env = ConformidadeNormativa().executar(
            self._sessao(diretos=2, por_classe=3),
            ConformidadeNormativaParams(norma_id="NORMA-X"),
        )
        alcancados = next(c for c in env.calculos if c.nome == "equipamentos_sujeitos")
        assert alcancados.valor == 5

    def test_cobertura_do_parque_e_fracao(self):
        env = ConformidadeNormativa().executar(
            self._sessao(diretos=0, por_classe=5),
            ConformidadeNormativaParams(norma_id="NORMA-X"),
        )
        cob = next(c for c in env.calculos if c.nome == "cobertura_do_parque")
        assert cob.valor == pytest.approx(0.5)

    def test_lacuna_quando_nenhum_equipamento_alcancado(self):
        env = ConformidadeNormativa().executar(
            self._sessao(diretos=0, por_classe=0),
            ConformidadeNormativaParams(norma_id="NORMA-X"),
        )
        assert any("Nenhum equipamento" in x for x in env.lacunas)

    def test_norma_inexistente_levanta(self):
        with pytest.raises(KeyError):
            ConformidadeNormativa().executar(
                SessaoFalsa([]), ConformidadeNormativaParams(norma_id="XX"),
            )


class TestRequisitosEquipamento:
    def _sessao(self, direta=False, via_classe=True):
        regras = [
            ("{id: $eid}) RETURN eq", [{"eq": No({"id": "EQ-1", "descricao": "equip"})}]),
            ("TEM_REQUISITO", [
                {"rq": No({"id": "REQ-A", "descricao": "r", "criticidade": "alta"})},
            ]),
        ]
        regras.append((
            "$eid})-[:REGULADO_POR]->(n:Norma) RETURN n",
            [{"n": No({"id": "N-D", "codigo": "ND", "descricao": "direta"})}] if direta else [],
        ))
        regras.append((
            "CLASSIFICADO_COMO",
            [{
                "ct": No({"id": "CT-1", "descricao": "classe"}),
                "n": No({"id": "N-C", "codigo": "NC", "descricao": "via classe"}),
            }] if via_classe else [],
        ))
        return SessaoFalsa(regras)

    def test_lacuna_quando_so_vem_da_classe(self):
        env = RequisitosEquipamento().executar(
            self._sessao(direta=False, via_classe=True),
            RequisitosEquipamentoParams(equipamento_id="EQ-1"),
        )
        assert any("apenas da classe" in x for x in env.lacunas)

    def test_sem_lacuna_de_procedencia_quando_ha_regulacao_direta(self):
        env = RequisitosEquipamento().executar(
            self._sessao(direta=True, via_classe=True),
            RequisitosEquipamentoParams(equipamento_id="EQ-1"),
        )
        assert not any("apenas da classe" in x for x in env.lacunas)

    def test_lacuna_quando_nenhuma_norma(self):
        env = RequisitosEquipamento().executar(
            self._sessao(direta=False, via_classe=False),
            RequisitosEquipamentoParams(equipamento_id="EQ-1"),
        )
        assert any("Nenhuma norma" in x for x in env.lacunas)


class TestLocalizacaoDefeito:
    def _sessao(self, com_parte=True, reincidentes=0):
        return SessaoFalsa([
            ("RETURN d, eq, mf", [{
                "d": No({"id": "DEF-1", "descricao": "def", "status": "aberto"}),
                "eq": No({"id": "EQ-1", "descricao": "equip"}),
                "mf": No({"id": "VIB", "descricao": "vibracao"}),
            }]),
            ("IDENTIFICADO_EM]->(p:ParteObjeto)", [
                {"p": No({"id": "PO-1", "descricao": "Rolamento"})},
            ] if com_parte else []),
            ("WHERE outro.id", [
                {"outro": No({"id": f"DEF-{9 - i}", "descricao": "o", "status": "resolvido"})}
                for i in range(reincidentes)
            ]),
        ])

    def test_conta_reincidencia_na_mesma_parte(self):
        env = LocalizacaoDefeito().executar(
            self._sessao(reincidentes=3), LocalizacaoDefeitoParams(defeito_id="DEF-1"),
        )
        c = next(c for c in env.calculos if c.nome == "outros_defeitos_na_mesma_parte")
        assert c.valor == 3

    def test_lacuna_quando_modo_nao_localiza_parte(self):
        env = LocalizacaoDefeito().executar(
            self._sessao(com_parte=False), LocalizacaoDefeitoParams(defeito_id="DEF-1"),
        )
        assert any("sem parte identificada" in x for x in env.lacunas)


class TestConsequenciaNotas:
    def _sessao(self, grupos, total):
        return SessaoFalsa([
            ("(eq:Equipamento {id: $eid}) RETURN eq", [{"eq": No({"id": "EQ-1", "descricao": "equip"})}]),
            ("AS quantas", [
                {"c": No({"id": cid, "descricao": cid, "severidade": sev}), "quantas": n}
                for cid, sev, n in grupos
            ]),
            ("RETURN count(nm) AS c", [{"c": total}]),
        ])

    def test_fracao_de_severidade_alta(self):
        env = ConsequenciaNotas().executar(
            self._sessao([("CNS-PAR", "alta", 3), ("CNS-DEG", "media", 7)], total=10),
            ConsequenciaNotasParams(equipamento_id="EQ-1"),
        )
        f = next(c for c in env.calculos if c.nome == "fracao_severidade_alta")
        assert f.valor == pytest.approx(0.3)

    def test_lacuna_para_notas_sem_consequencia(self):
        env = ConsequenciaNotas().executar(
            self._sessao([("CNS-PAR", "alta", 3)], total=10),
            ConsequenciaNotasParams(equipamento_id="EQ-1"),
        )
        assert any("7 nota(s) sem consequencia" in x for x in env.lacunas)

    def test_sem_divisao_por_zero_quando_nao_ha_nota(self):
        env = ConsequenciaNotas().executar(
            self._sessao([], total=0), ConsequenciaNotasParams(equipamento_id="EQ-1"),
        )
        f = next(c for c in env.calculos if c.nome == "fracao_severidade_alta")
        assert f.valor == 0.0


class TestEtapasOrdem:
    def _sessao(self, etapas):
        return SessaoFalsa([
            ("(om:OrdemManutencao {id: $oid}) RETURN om", [{"om": No({"id": "OM-1", "descricao": "ordem", "tipo": "corretiva"})}]),
            ("TEM_ETAPA", [
                {
                    "et": No({"id": f"ETP-{i}", "descricao": d, "ordem": i + 1}),
                    "eqp": No({"id": "EQP-1", "descricao": "equipe"}),
                }
                for i, d in enumerate(etapas)
            ]),
        ])

    def test_alerta_quando_primeira_etapa_nao_e_bloqueio(self):
        env = EtapasOrdem().executar(
            self._sessao(["Desmontagem", "Bloqueio de energia"]),
            EtapasOrdemParams(ordem_id="OM-1"),
        )
        assert any("primeira etapa nao e bloqueio" in x for x in env.lacunas)

    def test_sem_alerta_quando_bloqueio_vem_primeiro(self):
        env = EtapasOrdem().executar(
            self._sessao(["Bloqueio e sinalizacao de energia", "Desmontagem"]),
            EtapasOrdemParams(ordem_id="OM-1"),
        )
        assert not any("primeira etapa" in x for x in env.lacunas)

    def test_lacuna_quando_ordem_sem_etapa(self):
        env = EtapasOrdem().executar(
            self._sessao([]), EtapasOrdemParams(ordem_id="OM-1"),
        )
        assert any("sem etapas" in x for x in env.lacunas)


class TestAcoesPorPapel:
    def _sessao(self, n_acoes=2, n_modos=3, total_acoes=10, total_modos=16):
        return SessaoFalsa([
            ("WHERE x.id = $v", [{"x": No({"id": "PAPEL-1", "descricao": "tecnico", "nivel": "operacional"})}]),
            ("AUTORIZA", [
                {
                    "ap": No({"id": f"AP-{i}", "descricao": "acao", "tipo": "corretiva", "complexidade": "baixa"}),
                    "modos": [No({"id": f"M{j}", "descricao": "modo"}) for j in range(n_modos)],
                }
                for i in range(n_acoes)
            ]),
            ("count(ap) AS c", [{"c": total_acoes}]),
            ("count(mf) AS c", [{"c": total_modos}]),
        ])

    def test_fracao_do_catalogo(self):
        env = AcoesPorPapel().executar(
            self._sessao(n_acoes=2, total_acoes=10), AcoesPorPapelParams(papel_id="PAPEL-1"),
        )
        f = next(c for c in env.calculos if c.nome == "fracao_do_catalogo")
        assert f.valor == pytest.approx(0.2)

    def test_lacuna_de_modos_sem_acao_autorizada(self):
        env = AcoesPorPapel().executar(
            self._sessao(n_modos=3, total_modos=16), AcoesPorPapelParams(papel_id="PAPEL-1"),
        )
        assert any("13 modo(s) de falha sem acao" in x for x in env.lacunas)

    def test_lacuna_quando_papel_sem_autorizacao(self):
        env = AcoesPorPapel().executar(
            self._sessao(n_acoes=0), AcoesPorPapelParams(papel_id="PAPEL-1"),
        )
        assert any("sem nenhuma acao autorizada" in x for x in env.lacunas)


class TestDefeitosResolvidos:
    def _sessao(self, itens):
        return SessaoFalsa([("status = 'resolvido'", itens)])

    def test_tempo_medio_ate_encerramento(self):
        s = self._sessao([
            {
                "d": No({"id": "D1", "descricao": "d", "status": "resolvido",
                         "data_deteccao_horas": 100, "data_encerramento_horas": 200}),
                "eq": None, "at": None, "mf": None,
            },
            {
                "d": No({"id": "D2", "descricao": "d", "status": "resolvido",
                         "data_deteccao_horas": 100, "data_encerramento_horas": 400}),
                "eq": None, "at": None, "mf": None,
            },
        ])
        env = DefeitosResolvidos().executar(s, DefeitosResolvidosParams())
        m = next(c for c in env.calculos if c.nome == "tempo_medio_ate_encerramento")
        assert m.valor == pytest.approx(200.0)

    def test_lacuna_para_resolvido_sem_acao(self):
        s = self._sessao([{
            "d": No({"id": "D1", "descricao": "d", "status": "resolvido"}),
            "eq": None, "at": None, "mf": None,
        }])
        env = DefeitosResolvidos().executar(s, DefeitosResolvidosParams())
        assert any("sem acao tomada" in x for x in env.lacunas)

    def test_lista_vazia_nao_quebra(self):
        env = DefeitosResolvidos().executar(self._sessao([]), DefeitosResolvidosParams())
        assert any("Nenhum defeito encerrado" in x for x in env.lacunas)


class TestCargaCentroTrabalho:
    def _sessao(self, n_equip=4, n_def=2):
        return SessaoFalsa([
            ("WHERE x.id = $v", [{"x": No({"id": "CT-1", "descricao": "centro"})}]),
            ("RETURN eq\n            ORDER BY eq.id", [
                {"eq": No({"id": f"EQ-{i}", "descricao": "e"})} for i in range(n_equip)
            ]),
            ("d.status = 'aberto'", [
                {"d": No({"id": f"D-{i}", "descricao": "d", "status": "aberto"}),
                 "eq": No({"id": f"EQ-{i}", "descricao": "e"})}
                for i in range(n_def)
            ]),
            ("count(DISTINCT eq) AS n", [{"sid": "SIS-1", "sdesc": "sistema", "n": n_equip}]),
        ])

    def test_defeitos_por_equipamento(self):
        env = CargaCentroTrabalho().executar(
            self._sessao(n_equip=4, n_def=2), CargaCentroTrabalhoParams(centro_id="CT-1"),
        )
        c = next(c for c in env.calculos if c.nome == "defeitos_por_equipamento")
        assert c.valor == pytest.approx(0.5)

    def test_sem_divisao_por_zero_sem_equipamento(self):
        env = CargaCentroTrabalho().executar(
            self._sessao(n_equip=0, n_def=0), CargaCentroTrabalhoParams(centro_id="CT-1"),
        )
        c = next(c for c in env.calculos if c.nome == "defeitos_por_equipamento")
        assert c.valor == 0.0
        assert any("Nenhum equipamento" in x for x in env.lacunas)


class TestEscopoGrupoPlanejamento:
    def test_lacuna_de_cobertura_parcial(self):
        s = SessaoFalsa([
            ("WHERE x.id = $v", [{"x": No({"id": "GPJ-1", "descricao": "grupo"})}]),
            ("PLANEJADO_POR", [{"x": No({"id": "X-1", "descricao": "x"})}]),
            ("RETURN count(x) AS c", [{"c": 5}]),
        ])
        env = EscopoGrupoPlanejamento().executar(
            s, EscopoGrupoPlanejamentoParams(grupo_id="GPJ-1"),
        )
        assert any("Cobertura parcial" in x for x in env.lacunas)

    def test_percorre_os_quatro_niveis(self):
        s = SessaoFalsa([
            ("WHERE x.id = $v", [{"x": No({"id": "GPJ-1", "descricao": "grupo"})}]),
        ])
        env = EscopoGrupoPlanejamento().executar(
            s, EscopoGrupoPlanejamentoParams(grupo_id="GPJ-1"),
        )
        nomes = {c.nome for c in env.calculos}
        for label in ["edificacao", "sistema", "ativo", "equipamento"]:
            assert f"{label}_planejados" in nomes


class TestRankingSistemas:
    def _sessao(self, sistemas):
        return SessaoFalsa([
            ("ORDER BY lambda_total DESC", [
                {
                    "sis": No({"id": sid, "descricao": sid}),
                    "n_equip": 3, "lambda_total": lam,
                    "ic_inf": lam * 0.7, "ic_sup": lam * 1.4, "sem_metrica": 0,
                }
                for sid, lam in sistemas
            ]),
        ])

    def test_todo_lambda_vem_com_intervalo(self):
        """Regra 8: metrica de confiabilidade sem IC nao e exibivel."""
        env = RankingSistemas().executar(
            self._sessao([("S1", 0.01), ("S2", 0.002)]), RankingSistemasParams(),
        )
        lambdas = [c for c in env.calculos if c.nome.startswith("lambda_agregado_")]
        assert lambdas
        for c in lambdas:
            assert c.ic_inferior is not None
            assert c.ic_superior is not None
            assert c.ic_inferior <= c.valor <= c.ic_superior

    def test_declara_que_o_intervalo_nao_e_ic_exato(self):
        env = RankingSistemas().executar(
            self._sessao([("S1", 0.01)]), RankingSistemasParams(),
        )
        assert any("nao um IC exato" in x for x in env.lacunas)

    def test_razao_pior_sobre_melhor(self):
        env = RankingSistemas().executar(
            self._sessao([("S1", 0.01), ("S2", 0.002)]), RankingSistemasParams(),
        )
        r = next(c for c in env.calculos if c.nome == "razao_pior_sobre_melhor")
        assert r.valor == pytest.approx(5.0)

    def test_sem_sistema_avaliavel_nao_quebra(self):
        env = RankingSistemas().executar(SessaoFalsa([]), RankingSistemasParams())
        assert any("Nenhum sistema" in x for x in env.lacunas)


class TestResolverNo:
    """Referencia ausente nao pode virar 404 mudo."""

    def _sessao(self, nos):
        return SessaoFalsa([
            ("WHERE x.id = $v", [{"x": No(n)} for n in nos[:1]]),
            ("RETURN x ORDER BY x.id", [{"x": No(n)} for n in nos]),
        ])

    def test_resolve_por_id(self):
        from intents.base import resolver_no
        s = self._sessao([{"id": "A-1", "descricao": "um"}])
        assert resolver_no(s, "Papel", "A-1")["id"] == "A-1"

    def test_referencia_vazia_com_candidato_unico_resolve(self):
        """Um so no daquele rotulo: a leitura obvia e esse."""
        from intents.base import resolver_no
        s = self._sessao([{"id": "A-1", "descricao": "unico"}])
        assert resolver_no(s, "GrupoPlanejamento", "")["id"] == "A-1"

    def test_referencia_vazia_ambigua_lista_as_opcoes(self):
        from intents.base import resolver_no
        s = self._sessao([
            {"id": "A-1", "descricao": "um"},
            {"id": "A-2", "descricao": "dois"},
        ])
        with pytest.raises(KeyError) as exc:
            resolver_no(s, "Papel", "")
        mensagem = str(exc.value)
        assert "informe qual" in mensagem
        assert "A-1" in mensagem and "A-2" in mensagem

    def test_rotulo_sem_nenhum_no(self):
        from intents.base import resolver_no
        with pytest.raises(KeyError, match="Nenhum"):
            resolver_no(SessaoFalsa([]), "Papel", "")

    def test_id_inexistente_levanta_com_o_valor(self):
        from intents.base import resolver_no
        s = SessaoFalsa([("RETURN x ORDER BY x.id", [])])
        with pytest.raises(KeyError, match="XX-9"):
            resolver_no(s, "Papel", "XX-9")

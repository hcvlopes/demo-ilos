"""Adapter FalkorDB → interface compativel com neo4j-driver.

Permite que intents, seeders e migrations usem a mesma API
(session.run / result.single / record["campo"] / dict(node))
independente do backend de grafo.
"""

from __future__ import annotations

import os

from falkordb import FalkorDB, Node


class NodeWrapper:
    """Envolve falkordb.Node para suportar acesso dict-like."""

    def __init__(self, node: Node):
        self._props = dict(node.properties) if node.properties else {}

    def __getitem__(self, key):
        return self._props[key]

    def get(self, key, default=None):
        return self._props.get(key, default)

    def __contains__(self, key):
        return key in self._props

    def __iter__(self):
        return iter(self._props)

    def __len__(self):
        return len(self._props)

    def keys(self):
        return self._props.keys()

    def values(self):
        return self._props.values()

    def items(self):
        return self._props.items()

    def __eq__(self, other):
        if isinstance(other, NodeWrapper):
            return self._props == other._props
        return NotImplemented

    def __hash__(self):
        return hash(tuple(sorted(self._props.items())))

    def __repr__(self):
        return f"NodeWrapper({self._props!r})"


def _wrap_value(val):
    if val is None:
        return None
    if isinstance(val, Node):
        return NodeWrapper(val)
    if isinstance(val, list):
        return [_wrap_value(v) for v in val]
    return val


class RecordWrapper:
    """Linha de resultado com acesso por nome de coluna."""

    def __init__(self, row: list, columns: list[str]):
        self._data = {}
        for i, col in enumerate(columns):
            self._data[col] = _wrap_value(row[i]) if i < len(row) else None

    def __getitem__(self, key):
        return self._data[key]

    def get(self, key, default=None):
        return self._data.get(key, default)

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def items(self):
        return self._data.items()


class ResultWrapper:
    """Resultado de query com .single() e iteracao por records."""

    def __init__(self, query_result):
        raw_header = list(query_result.header) if query_result.header else []
        self._columns = [
            col[1] if isinstance(col, (list, tuple)) else col
            for col in raw_header
        ]
        self._rows = list(query_result.result_set) if query_result.result_set else []

    def single(self):
        if not self._rows:
            return None
        return RecordWrapper(self._rows[0], self._columns)

    def __iter__(self):
        for row in self._rows:
            yield RecordWrapper(row, self._columns)


class SessionWrapper:
    """Envolve falkordb.Graph para imitar neo4j.Session."""

    def __init__(self, graph):
        self._graph = graph

    def run(self, query: str, parameters: dict | None = None):
        result = self._graph.query(query, params=parameters or {})
        return ResultWrapper(result)

    def run_somente_leitura(self, travessia: str, parameters: dict | None = None):
        """Executa via GRAPH.RO_QUERY: o servidor recusa qualquer escrita.

        Usado no caminho de consulta livre, onde o Cypher vem do LLM. A
        diferenca em relacao a uma checagem sintatica no cliente e que aqui
        quem recusa e o proprio FalkorDB — nao ha regex a burlar. Uma escrita
        que chegue aqui morre com "graph.RO_QUERY is to be executed only on
        read-only queries", independente de como tenha sido escrita.
        """
        result = self._graph.ro_query(travessia, params=parameters or {})
        return ResultWrapper(result)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class DriverWrapper:
    """Envolve FalkorDB para imitar neo4j.Driver."""

    def __init__(self, db: FalkorDB, graph_name: str):
        self._db = db
        self._graph_name = graph_name

    def session(self):
        graph = self._db.select_graph(self._graph_name)
        return SessionWrapper(graph)

    def close(self):
        pass


def create_driver(
    host: str | None = None,
    port: int | None = None,
    password: str | None = None,
    graph_name: str | None = None,
) -> DriverWrapper:
    """Cria driver FalkorDB a partir de parametros ou variaveis de ambiente."""
    host = host or os.environ.get("FALKORDB_HOST", "localhost")
    port = port or int(os.environ.get("FALKORDB_PORT", "6379"))
    password = password or os.environ.get("FALKORDB_PASSWORD", "") or None
    graph_name = graph_name or os.environ.get("FALKORDB_GRAPH", "demo_ilos")

    kwargs = {"host": host, "port": port}
    if password:
        kwargs["password"] = password

    db = FalkorDB(**kwargs)
    return DriverWrapper(db, graph_name)
